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
import hashlib

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


def compact(cache,directory,voxel=.04):
    """Consider every cached return, retaining an actual representative per voxel.

    Spatial bins must align with the voxel grid so no voxel crosses two bins.
    This is an offline reconstruction cache, not a replacement for raw auditing.
    """
    cache,directory=Path(cache),Path(directory)
    meta=json.loads((cache/'manifest.json').read_text())
    if voxel<=0 or not np.isclose(meta['tileSizeMetres']/voxel,round(meta['tileSizeMetres']/voxel),rtol=0,atol=1e-9):
        raise ValueError('Voxel must be positive and divide the source spatial bin size')
    directory.mkdir(parents=True,exist_ok=True)
    if (directory/'manifest.json').exists() or any(directory.glob('tile-*.bin')):
        raise ValueError('Choose an empty compaction output directory')
    counts={};considered=0;started=time.monotonic()
    for index,(name,count) in enumerate(meta['bins'].items()):
        records=np.fromfile(cache/name,DTYPE)
        if len(records)!=count:raise ValueError(f'Incomplete source spatial bin: {name}')
        cells=np.floor(records['xyz'].astype('f8')/voxel).astype('i4')
        _,chosen=np.unique(cells,axis=0,return_index=True)
        # Source order makes repeated runs and original-record audits stable.
        chosen.sort();records[chosen].tofile(directory/name)
        counts[name]=len(chosen);considered+=count
        if index%5==0 or index==len(meta['bins'])-1:
            print(json.dumps({'bins':index+1,'totalBins':len(meta['bins']),
                'recordsConsidered':considered,'representatives':sum(counts.values()),
                'elapsedSeconds':round(time.monotonic()-started,1)}),flush=True)
        del records,cells,chosen
    if considered!=meta['recordsRetained']:raise ValueError('Source cache count mismatch')
    result={**meta,'inputRecordsRetained':considered,'recordsRetained':sum(counts.values()),
            'sampling':f'One unchanged measured representative per occupied {voxel} metre voxel; every input cache record considered',
            'voxelMetres':voxel,'bins':counts,
            'parentManifestSHA256':hashlib.sha256((cache/'manifest.json').read_bytes()).hexdigest(),
            'elapsedSeconds':round(time.monotonic()-started,2),
            'limits':'Physical preparation subset. Original every-record cache retained separately; full-source coverage must be audited against that cache.'}
    (directory/'manifest.json').write_text(json.dumps(result,indent=2));return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'20261008121946091.las')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compact-cache',type=Path,help='Prepare physical-voxel representatives from an existing every-record cache')
    parser.add_argument('--voxel',type=float,default=.04)
    args=parser.parse_args()
    if args.compact_cache:
        output=args.output or ROOT/'analysis/dense-las-voxel040'
        result=compact(args.compact_cache,output,args.voxel)
    else:
        output=args.output or ROOT/'analysis/dense-las'
        result=extract(args.source,output,[340150,2777800,50],[-250,200,-320,60,-8,45])
    print(json.dumps({k:v for k,v in result.items() if k!='bins'},indent=2))
