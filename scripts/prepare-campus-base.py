"""Stage the reviewed campus mesh and suppress duplicate illustrative vegetation.

Suppression is based on captured vertical volume near an aerial tree position;
it is not semantic tree classification. Original measurements stay unchanged.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT.parent
sys.path.insert(0,str(ROOT/'analysis/python-packages'))
import numpy as np
from scipy.spatial import cKDTree
spec=importlib.util.spec_from_file_location('dense',PROJECT/'scripts/dense-las.py')
dense=importlib.util.module_from_spec(spec);spec.loader.exec_module(dense)


def file_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def captured_volumes(points,trees,minimum=100):
    tree=cKDTree(points[:,:2]);excluded=[]
    for index,(x,y,_,radius) in enumerate(trees):
        ids=tree.query_ball_point([x,y],max(1.,radius*.65))
        if len(ids)<minimum:continue
        heights=points[ids,2];low=float(np.quantile(heights,.1))
        count=int(np.count_nonzero(heights>low+1.5))
        if count>=minimum:excluded.append({'treeIndex':index,'elevatedSourceRecords':count})
    return excluded


def prepare(mesh,cache,output):
    mesh,cache,output=Path(mesh),Path(cache),Path(output)
    metadata=json.loads(mesh.with_suffix('.json').read_text())
    audit_path=mesh.with_name(mesh.name+'-raw-audit').with_suffix('.json')
    audit=json.loads(audit_path.read_text())
    asset_hash=file_hash(mesh.with_suffix('.glb'))
    if audit.get('meshSHA256')!=asset_hash:raise ValueError('Coverage audit does not match the staged mesh bytes')
    cache_hash=file_hash(cache/'manifest.json')
    if metadata['reductionCacheManifestSHA256']!=cache_hash:
        raise ValueError('Captured-volume cache differs from the reviewed reduction cache')
    site=json.loads((PROJECT/'public/replica/site.json').read_text())
    records=dense.load_region(cache,metadata['boundsLocal'])
    excluded=captured_volumes(records['xyz'],site['trees']);del records
    output.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(mesh.with_suffix('.glb'),output/'campus-surface.glb')
    if file_hash(output/'campus-surface.glb')!=asset_hash:raise ValueError('Staged mesh checksum differs from audit')
    shutil.copyfile(mesh.with_suffix('.json'),output/'dense-campus-browser-base.json')
    shutil.copyfile(audit_path,output/'dense-campus-browser-base-raw-audit.json')
    result={'asset':'campus-surface.glb','assetSHA256':asset_hash,'triangles':metadata['triangles'],'vertices':metadata['vertices'],
            'boundsLocal':metadata['boundsLocal'],'origin':metadata['origin'],
            'source':'20261008121946091.las','originalRecordsRead':audit['originalRecordsRead'],
            'sourceRetainedRecords':audit['sourceCacheRecords'],'inputRegionRecords':metadata['inputRegionRecords'],
            'rawSampleRecords':audit['sampledRecords'],'rawSampleDistanceMetres':audit['distanceMetres'],
            'modelledTreeExclusions':excluded,
            'treeExclusionMethod':'At least100 captured representatives more than1.5m above local10th percentile within65% of aerial crown radius; captured volume, not semantic tree labels',
            'treeCoverageCacheManifestSHA256':hashlib.sha256((cache/'manifest.json').read_bytes()).hexdigest(),
            'geometryProvenance':'dense-campus-browser-base.json','auditProvenance':'dense-campus-browser-base-raw-audit.json',
            'photorealismComplete':False,
            'limits':'Simplified measured triangle base. Occluded surfaces can remain incomplete; additional fine meshes and photographic validation remain in progress.'}
    (output/'campus-surface.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'triangles':result['triangles'],'excludedIllustrativeTrees':len(excluded),
                      'totalIllustrativeTrees':len(site['trees'])}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh',type=Path,default=ROOT/'analysis/dense-reconstruction/campus-base-browser-v2')
    parser.add_argument('--cache',type=Path,default=ROOT/'analysis/dense-las-voxel080')
    parser.add_argument('--output',type=Path,default=PROJECT/'public/replica')
    args=parser.parse_args();prepare(args.mesh,args.cache,args.output)
