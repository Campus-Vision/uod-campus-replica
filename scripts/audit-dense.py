"""Independent height-stratified dense mesh audit; ground cannot hide detail gaps."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reconstruct',PROJECT/'scripts/reconstruct-dense.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np,o3d=module.np,module.o3d
spec=importlib.util.spec_from_file_location('details',PROJECT/'scripts/prepare-details.py')
details=importlib.util.module_from_spec(spec);spec.loader.exec_module(details)


def audit(path,cache):
    path=Path(path);meta=json.loads(path.with_suffix('.json').read_text());bounds=meta['boundsLocal']
    records=module.dense.load_region(cache,bounds,halo=0)
    source=records['xyz'].copy()
    height=source[:,2]-details.local_floor(source)
    scenes=[]
    for meshpath in [PROJECT/'public/replica/building-surface.glb',path.with_suffix('.glb')]:
        mesh=o3d.io.read_triangle_mesh(str(meshpath))
        scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh));scenes.append(scene)
    results=[]
    for name,low,high in [('ground',-.5,.35),('low-objects',.35,3),('higher-objects',3,12),('upper-building',12,50)]:
        ids=np.flatnonzero((height>=low)&(height<high))
        if not len(ids): continue
        chosen=ids[np.linspace(0,len(ids)-1,min(50000,len(ids)),dtype=int)]
        query=o3d.core.Tensor(source[chosen]);old,new=[s.compute_distance(query).numpy() for s in scenes]
        results.append({'stratum':name,'heightAboveApproximateFloorMetres':[low,high],
            'sourceRecords':len(ids),'auditRecords':len(chosen),
            'baselineDistanceMetres':module.summary(old),'denseDistanceMetres':module.summary(new),
            'baselineWithin5cm':float(np.mean(old<=.05)),'denseWithin5cm':float(np.mean(new<=.05)),
            'baselineWithin10cm':float(np.mean(old<=.10)),'denseWithin10cm':float(np.mean(new<=.10))})
    meta['heightStratifiedAudit']={'classification':'Approximate local-floor heights; NOT semantic car/tree/building labels',
        'regions':results}
    path.with_suffix('.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta['heightStratifiedAudit'],indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mesh',type=Path)
    p.add_argument('--cache',type=Path,default=PROJECT.parent/'analysis/dense-las')
    args=p.parse_args();audit(args.mesh,args.cache)
