"""Audit a campus mesh with uniform records from the full, unsampled LAS cache.

Sampling is over original records, not uniformly over spatial bins or prepared
voxel representatives. No full-region 200-million-point array is allocated.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT.parent
spec=importlib.util.spec_from_file_location('reconstruct',PROJECT/'scripts/reconstruct-dense.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np,o3d=module.np,module.o3d


def sample_records(cache,count=300000,seed=20261017):
    cache=Path(cache);meta=json.loads((cache/'manifest.json').read_text())
    if meta.get('voxelMetres') is not None:
        raise ValueError('Coverage audit requires the full unsampled record cache')
    bins=sorted(meta['bins'].items());total=sum(n for _,n in bins)
    if total!=meta['recordsRetained'] or total<1 or count<1:
        raise ValueError('Invalid source cache count or sample size')
    rng=np.random.default_rng(seed)
    selected=np.sort(rng.choice(total,min(count,total),replace=False,shuffle=False))
    result=np.empty(len(selected),module.dense.DTYPE);offset=0
    for name,size in bins:
        begin,end=np.searchsorted(selected,[offset,offset+size])
        if end>begin:
            records=np.memmap(cache/name,dtype=module.dense.DTYPE,mode='r')
            if len(records)!=size:raise ValueError('Cache bin length differs from manifest')
            result[begin:end]=records[selected[begin:end]-offset]
            del records
        offset+=size
    return result,meta


def metrics(distance):
    return {**module.summary(distance),'within5cm':float(np.mean(distance<=.05)),
            'within10cm':float(np.mean(distance<=.10)),
            'within20cm':float(np.mean(distance<=.20))}


def audit(path,cache,output,count=300000):
    path,cache,output=Path(path),Path(cache),Path(output)
    records,meta=sample_records(cache,count)
    original=Path(meta['source'])
    if original.stat().st_size!=meta['sourceBytes'] or original.stat().st_mtime_ns!=meta['sourceModifiedNs']:
        raise ValueError('Original LAS changed since extraction; provenance audit required')
    source=records['xyz'].copy()
    mesh=o3d.io.read_triangle_mesh(str(path))
    if not mesh.has_triangles():raise ValueError('Connected triangle mesh required')
    scene=o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh));del mesh
    distance=scene.compute_distance(o3d.core.Tensor(source)).numpy()
    spatial=[];cells=np.floor(source[:,:2]/40).astype('i4')
    for cell in np.unique(cells,axis=0):
        chosen=np.all(cells==cell,axis=1)
        spatial.append({'cell40m':cell.tolist(),'sampledRecords':int(chosen.sum()),
                        'distanceMetres':metrics(distance[chosen])})
    heights=[]
    for low,high in [(-8,0),(0,3),(3,12),(12,25),(25,45)]:
        chosen=(source[:,2]>=low)&(source[:,2]<high)
        if np.any(chosen):
            heights.append({'localZMetres':[low,high],'sampledRecords':int(chosen.sum()),
                            'distanceMetres':metrics(distance[chosen])})
    report={'mesh':path.name,'source':original.name,'sourceCacheRecords':meta['recordsRetained'],
            'originalRecordsRead':meta['recordsRead'],'sampledRecords':len(records),
            'sampling':'Uniform original retained-record IDs without replacement; seed 20261017',
            'sourceManifestSHA256':hashlib.sha256((cache/'manifest.json').read_bytes()).hexdigest(),
            'distanceMetres':metrics(distance),'spatialCells':spatial,'localHeightBands':heights,
            'limits':'Sampled source-to-surface agreement, not surveyed accuracy or proof of unseen surfaces. Local Z bands are not semantic vegetation/vehicle/building labels. Dense source areas receive proportionate weight; per-cell metrics expose spatial gaps.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['spatialCells','localHeightBands']},indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh',type=Path)
    parser.add_argument('--cache',type=Path,default=ROOT/'analysis/dense-las')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--count',type=int,default=300000)
    args=parser.parse_args();audit(args.mesh,args.cache,args.output,args.count)
