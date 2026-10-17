"""Prepare a bounded-error browser base from the full-footprint measured mesh.

Fine detail remains a separate progressive layer. This base keeps vertex colour;
raw photographic projection has not been approved by the registration checks.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import time

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT.parent
spec=importlib.util.spec_from_file_location('baking',PROJECT/'scripts/bake-dense.py')
baking=importlib.util.module_from_spec(spec);spec.loader.exec_module(baking)
module=baking.module;np,o3d=module.np,module.o3d
spec=importlib.util.spec_from_file_location('locks',PROJECT/'scripts/preparation-lock.py')
locks=importlib.util.module_from_spec(spec);spec.loader.exec_module(locks)


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
    return digest.hexdigest()


def simplify_only(path,output,triangles):
    with locks.exclusive_worker(output.parent/(output.name+'.worker')):
        return simplify_locked(path,output,triangles)


def simplify_locked(path,output,triangles):
    # The native simplifier owns substantial scratch storage. Running this phase
    # in a separate process guarantees release before the audit and RGB tree.
    import fast_simplification
    mesh=o3d.io.read_triangle_mesh(str(path.with_suffix('.glb')))
    print('Native quadric reduction',len(mesh.triangles),'target',triangles,flush=True)
    vertices,faces=fast_simplification.simplify(np.asarray(mesh.vertices),np.asarray(mesh.triangles),
        target_count=triangles,agg=5.,preserve_border=False)
    stamp={'parentSHA256':file_hash(path.with_suffix('.glb')),'targetTriangles':triangles,
           'simplifier':'fast-simplification 0.2.0','aggressiveness':5.,'preserveBorder':False}
    np.savez(output,vertices=vertices.astype('f4'),faces=faces.astype('i4'),stamp=json.dumps(stamp))
    print('Native reduction saved',len(faces),'triangles',flush=True)


def reduce(path,output,cache,triangles=1500000):
    path,output=Path(path),Path(output)
    if path.with_suffix('.glb').resolve()==output.with_suffix('.glb').resolve():
        raise ValueError('Reduced output must preserve the full-resolution parent')
    with locks.exclusive_worker(output.parent/(output.name+'.worker')):
        return reduce_locked(path,output,cache,triangles)


def reduce_locked(path,output,cache,triangles=1500000):
    path,output,cache=Path(path),Path(output),Path(cache);started=time.monotonic()
    if path.with_suffix('.glb').resolve()==output.with_suffix('.glb').resolve():
        raise ValueError('Reduced output must preserve the full-resolution parent')
    meta=json.loads(path.with_suffix('.json').read_text())
    prepared=output.with_name(output.name+'-simplified.npz')
    stamp={'parentSHA256':file_hash(path.with_suffix('.glb')),'targetTriangles':triangles,
           'simplifier':'fast-simplification 0.2.0','aggressiveness':5.,'preserveBorder':False}
    valid=False
    if prepared.exists():
        with np.load(prepared) as saved:valid=json.loads(str(saved['stamp']))==stamp
    if not valid:
        subprocess.run([sys.executable,__file__,str(path),'--output',str(output),
                        '--triangles',str(triangles),'--simplify-only'],check=True)
    with np.load(prepared) as saved:
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(saved['vertices'].astype(float)),
                                       o3d.utility.Vector3iVector(saved['faces']))
    parent=o3d.io.read_triangle_mesh(str(path.with_suffix('.glb')))
    parent_scene=o3d.t.geometry.RaycastingScene()
    parent_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(parent));del parent
    print('Checking continuous parent support',len(mesh.triangles),flush=True)
    keep,adaptive=baking.adaptive_face_support(mesh,parent_scene)
    mesh.remove_triangles_by_mask(~keep);mesh.remove_unreferenced_vertices();del parent_scene
    print('Checking measured support and assigning measured RGB',flush=True)
    records=module.dense.load_region(cache,meta['boundsLocal'],meta['haloMetres'])
    xyz=records['xyz'].copy();rgb=records['rgb'].copy();del records
    tree=module.cKDTree(xyz)
    mesh=module.supported_mesh(mesh,tree,meta['boundsLocal'],edge=float('inf'))
    mesh.compute_vertex_normals()
    vertices=np.asarray(mesh.vertices).astype('<f4');faces=np.asarray(mesh.triangles).astype('<u4')
    colours,distance=module.measured_colours(vertices,tree,rgb)
    module.write_glb(output.with_suffix('.glb'),vertices,faces,colours,np.asarray(mesh.vertex_normals).astype('<f4'))
    report={**meta,'parentMesh':path.with_suffix('.glb').name,
        'method':meta['method']+'; quadric browser base reduction',
        'reduction':stamp,'reductionCachePath':str(cache.resolve()),
        'reductionCacheManifestSHA256':file_hash(cache/'manifest.json'),
        'targetTriangles':triangles,'vertices':len(vertices),'triangles':len(faces),
        'adaptiveParentSupport':adaptive,'vertexSupportMetres':module.summary(distance),
        'maximumEdgeMetres':None,'maximumEdgeLimitReason':'Adaptive entire-face parent support replaces the fine mesh edge-length cap',
        'browserRole':'Full-footprint base; detailed local meshes remain separate',
        'fileBytes':output.with_suffix('.glb').stat().st_size,
        'reductionSeconds':round(time.monotonic()-started,2),
        'limits':meta['limits']+' Browser base is simplified; separate raw-record coverage audit is required.'}
    # Parent audits cannot describe the reduced output.
    for key in ['heightStratifiedAudit','sourceToMeshDistanceMetres','coverageWithin5cm','coverageWithin10cm','auditRecords',
                'baselineSourceToMeshDistanceMetres','baselineCoverageWithin5cm','baselineCoverageWithin10cm']:
        report.pop(key,None)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'triangles':len(faces),'fileBytes':report['fileBytes'],
                      'reductionSeconds':report['reductionSeconds']},indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,default=ROOT/'analysis/dense-las-voxel080')
    parser.add_argument('--triangles',type=int,default=1500000)
    parser.add_argument('--simplify-only',action='store_true')
    args=parser.parse_args()
    if args.simplify_only:
        simplify_only(args.mesh,args.output.with_name(args.output.name+'-simplified.npz'),args.triangles)
    else:reduce(args.mesh,args.output,args.cache,args.triangles)
