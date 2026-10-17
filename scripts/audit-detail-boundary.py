"""Measure two independently fitted detail tiles at their common boundary.

This is a fit comparison, not topological stitching. Missing support is reported,
not hidden by filtering the denominator or treating nearby surfaces as welded.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT.parent
spec=importlib.util.spec_from_file_location('reconstruct',PROJECT/'scripts/reconstruct-dense.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np,o3d=module.np,module.o3d


def audit(left,right,output):
    left,right,output=Path(left),Path(right),Path(output)
    a,b=[json.loads(path.with_suffix('.json').read_text()) for path in [left,right]]
    x=a['boundsLocal'][1]
    if x!=b['boundsLocal'][0]:raise ValueError('This audit requires adjacent X cells, left then right')
    y0=max(a['boundsLocal'][2],b['boundsLocal'][2])+1
    y1=min(a['boundsLocal'][3],b['boundsLocal'][3])-1
    source=module.dense.load_region(ROOT/'analysis/dense-las',[x-.2,x+.2,y0,y1])['xyz'].copy()
    if not len(source):raise ValueError('No original returns in boundary strip')
    ids=np.linspace(0,len(source)-1,min(len(source),150000),dtype=int);query=source[ids]
    scenes=[];counts=[]
    for path in [left,right,ROOT/'analysis/dense-reconstruction/campus-base-browser-v2']:
        mesh=o3d.io.read_triangle_mesh(str(path.with_suffix('.glb')));counts.append(len(mesh.triangles))
        scene=o3d.t.geometry.RaycastingScene()
        scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh));scenes.append(scene);del mesh
    distance=[scene.compute_distance(o3d.core.Tensor(query)).numpy() for scene in scenes]
    union=np.minimum(distance[0],distance[1]);base=distance[2]
    near=source[np.abs(source[:,0]-x)<=.05].copy();near[:,0]=x
    near=near[np.linspace(0,len(near)-1,min(len(near),50000),dtype=int)]
    closest=[scene.compute_closest_points(o3d.core.Tensor(near))['points'].numpy() for scene in scenes[:2]]
    difference=np.linalg.norm(closest[0]-closest[1],axis=1)
    supported=(np.linalg.norm(closest[0]-near,axis=1)<=.20)&(np.linalg.norm(closest[1]-near,axis=1)<=.20)
    def coverage(values):return {**module.summary(values),'within5cm':float(np.mean(values<=.05)),
                                 'within10cm':float(np.mean(values<=.10))}
    result={'left':left.name,'right':right.name,'triangleCounts':counts,
            'source':'Original every-record LAS cache; internal agreement, not independent survey control',
            'sourceStripBoundsLocal':[x-.2,x+.2,y0,y1],'sourceStripRecords':len(source),
            'auditedRecords':len(query),'unionDistanceMetres':coverage(union),'baseDistanceMetres':coverage(base),
            'sharedPlaneQueryRecords':len(near),'closestSurfaceDifferenceMetres':module.summary(difference),
            'bothSurfacesWithin20cmFraction':float(np.mean(supported)),
            'conditionalSupportedDifferenceMetres':module.summary(difference[supported]) if supported.any() else None,
            'topologicallyStitched':False,
            'limits':'Projected boundary queries move original returns by at most5cm in X. Conditional metrics exclude unsupported regions explicitly; they cannot prove a closed seam. Keep global base support and inspect the LOD transition visually before assembly.'}
    output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--left',type=Path,default=ROOT/'analysis/campus-detail-meshes-v1/cell-0--6')
    parser.add_argument('--right',type=Path,default=ROOT/'analysis/campus-detail-meshes-v1/cell-1--6')
    parser.add_argument('--output',type=Path,default=ROOT/'analysis/campus-detail-meshes-v1/boundary-0-1--6.json')
    args=parser.parse_args();audit(args.left,args.right,args.output)
