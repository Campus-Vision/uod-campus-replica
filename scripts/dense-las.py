"""Read every original LAS record into bounded spatial bins for offline meshing.

No source modifications. Bins preserve actual source XYZ/RGB and record IDs;
load_region adds overlap from neighbouring bins without duplicating points.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'analysis/python-packages'))
import numpy as np

DTYPE = np.dtype([('xyz', '<f4', (3,)), ('rgb', 'u1', (3,)), ('record', '<u8')])


def read_header(path):
    with Path(path).open('rb') as stream:
        header = stream.read(375)
    if len(header) < 227 or header[:4] != b'LASF':
        raise ValueError('Expected a complete uncompressed LAS header')
    offset = struct.unpack_from('<I', header, 96)[0]
    fmt, stride = header[104], struct.unpack_from('<H', header, 105)[0]
    if fmt != 3 or stride < 34:
        raise ValueError('This source reader requires uncompressed LAS point format 3')
    count = struct.unpack_from('<I', header, 107)[0]
    if header[25] >= 4 and len(header) >= 255:
        count = struct.unpack_from('<Q', header, 247)[0] or count
    if offset < 227 or not count or Path(path).stat().st_size < offset+count*stride:
        raise ValueError('Invalid LAS offset/count or truncated point records')
    return {'count': count, 'offset': offset, 'stride': stride, 'format': fmt,
            'scale': list(struct.unpack_from('<3d', header, 131)),
            'offsetXYZ': list(struct.unpack_from('<3d', header, 155))}


def extract(path, directory, origin, bounds, tile_size=40., chunk_size=500000):
    path, directory = Path(path), Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory/'manifest.json').exists() or any(directory.glob('tile-*.bin')):
        raise ValueError('Choose an empty output directory; existing data is never overwritten')
    header = read_header(path)
    record_type = np.dtype({'names':['xyz','rgb'], 'formats':[('<i4',3),('<u2',3)],
                            'offsets':[0,28], 'itemsize':header['stride']})
    source = np.memmap(path, dtype=record_type, mode='r', offset=header['offset'], shape=(header['count'],))
    origin, bounds = np.asarray(origin, float), np.asarray(bounds, float)
    if tile_size <= 0 or chunk_size <= 0 or bounds.shape != (6,):
        raise ValueError('Positive tile/chunk sizes and six bounds required')
    counts = {}; total = 0; started = time.monotonic()
    for start in range(0, len(source), chunk_size):
        records = source[start:start+chunk_size]
        xyz = records['xyz'].astype(float)*header['scale']+header['offsetXYZ']-origin
        keep = ((xyz[:,0]>=bounds[0]) & (xyz[:,0]<bounds[1]) &
                (xyz[:,1]>=bounds[2]) & (xyz[:,1]<bounds[3]) &
                (xyz[:,2]>=bounds[4]) & (xyz[:,2]<=bounds[5]))
        ids = np.flatnonzero(keep)
        selected = np.empty(len(ids), DTYPE)
        selected['xyz'] = xyz[ids]
        rgb = records['rgb'][ids]
        selected['rgb'] = np.where(rgb<=255, rgb, np.rint(rgb/257)).astype('u1')
        selected['record'] = start+ids
        tile = np.floor(selected['xyz'][:,:2]/tile_size).astype('i4')
        # Group once per chunk so each spatial output receives contiguous writes.
        if len(tile):
            keys = tile[:,0].astype('i8')*100000+tile[:,1]+50000
            order = np.argsort(keys, kind='stable')
            cuts = np.r_[0, np.flatnonzero(np.diff(keys[order]))+1, len(order)]
            for a,b in zip(cuts[:-1],cuts[1:]):
                indices = order[a:b]; x,y = tile[indices[0]]
                name = f'tile-{x}-{y}.bin'
                with (directory/name).open('ab') as stream: selected[indices].tofile(stream)
                counts[name] = counts.get(name,0)+len(indices)
        total += len(ids)
        if start//chunk_size % 10 == 0 or start+chunk_size >= len(source):
            print(json.dumps({'read':min(start+chunk_size,len(source)), 'retained':total,
                              'seconds':round(time.monotonic()-started,1)}),flush=True)
    meta = {'source':str(path.resolve()), 'sourceBytes':path.stat().st_size,
            'sourceModifiedNs':path.stat().st_mtime_ns, 'header':header,
            'recordsRead':len(source), 'recordsRetained':total,
            'sampling':'Every LAS record; no temporal or voxel sampling',
            'origin':origin.tolist(), 'boundsLocal':bounds.tolist(),
            'tileSizeMetres':tile_size, 'recordBytes':DTYPE.itemsize,
            'bins':counts, 'elapsedSeconds':round(time.monotonic()-started,2)}
    (directory/'manifest.json').write_text(json.dumps(meta,indent=2))
    return meta


def load_region(directory, bounds, halo=0.):
    directory = Path(directory)
    meta = json.loads((directory/'manifest.json').read_text())
    xmin,xmax,ymin,ymax = bounds
    xmin-=halo; xmax+=halo; ymin-=halo; ymax+=halo
    size = meta['tileSizeMetres']; parts=[]
    for name in meta['bins']:
        # Coordinates can be negative, so parse the stored name via its regex.
        import re
        x,y=map(int,re.fullmatch(r'tile-(-?\d+)-(-?\d+)\.bin', name).groups())
        if (x+1)*size<xmin or x*size>xmax or (y+1)*size<ymin or y*size>ymax: continue
        data=np.fromfile(directory/name, DTYPE); p=data['xyz']
        keep=(p[:,0]>=xmin)&(p[:,0]<xmax)&(p[:,1]>=ymin)&(p[:,1]<ymax)
        parts.append(data[keep])
    return np.concatenate(parts) if parts else np.empty(0,DTYPE)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'20261008121946091.las')
    parser.add_argument('--output', type=Path, default=ROOT/'analysis/dense-las')
    args=parser.parse_args()
    result=extract(args.source,args.output,[340150,2777800,50],[-250,200,-320,60,-8,45])
    print(json.dumps({k:v for k,v in result.items() if k!='bins'},indent=2))
