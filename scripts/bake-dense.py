"""Preserve dense scan colour in a texture while reducing browser triangles.

This is measured-colour baking, not photographic multi-view reconstruction.
The original high-resolution mesh and scan are retained separately.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reconstruct',PROJECT/'scripts/reconstruct-dense.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np,o3d=module.np,module.o3d
from PIL import Image
import xatlas


def gltf_uv_from_atlas(uv):
    result=np.asarray(uv,dtype='f4').copy()
    result[:,1]=1-result[:,1]
    return result


def adaptive_face_support(mesh,parent_scene,spacing=.04,cutoff=.025):
    """Test entire faces on an adaptive barycentric grid against the dense parent.

    Every surface location is within `spacing` of a tested point. Since distance
    to the parent is 1-Lipschitz, retained faces have a conservative continuous
    distance bound of cutoff+spacing (plus floating-point tolerance).
    """
    if spacing<=0 or cutoff<=0:raise ValueError('Positive sampling bounds required')
    points=np.asarray(mesh.vertices)[np.asarray(mesh.triangles)]
    longest=np.maximum.reduce([np.linalg.norm(points[:,a]-points[:,b],axis=1)
                               for a,b in [(0,1),(1,2),(2,0)]])
    divisions=np.maximum(1,np.ceil(longest/spacing).astype(int))
    maximum=np.zeros(len(points));samples=0
    for n in np.unique(divisions):
        ids=np.flatnonzero(divisions==n)
        weights=np.array([(i/n,j/n,1-(i+j)/n) for i in range(n+1) for j in range(n+1-i)])
        batch_size=max(1,200000//len(weights))
        for start in range(0,len(ids),batch_size):
            chosen=ids[start:start+batch_size]
            grid=np.einsum('wc,fcd->fwd',weights,points[chosen]).astype('f4')
            distance=parent_scene.compute_distance(o3d.core.Tensor(grid.reshape(-1,3))).numpy()
            maximum[chosen]=distance.reshape(len(chosen),-1).max(axis=1);samples+=distance.size
    keep=maximum<=cutoff
    return keep,{'sampleCount':samples,'maximumGridSpacingMetres':spacing,
                 'sampleCutoffMetres':cutoff,'continuousParentDistanceBoundMetres':cutoff+spacing,
                 'maximumRetainedSampleDistanceMetres':float(maximum[keep].max()) if np.any(keep) else None,
                 'rejectedFaces':int((~keep).sum())}


def split_vertex_fans(mesh):
    """Duplicate only disconnected vertex fans; never move or delete a face."""
    vertices=np.asarray(mesh.vertices).tolist();faces=np.asarray(mesh.triangles).copy()
    flat=faces.reshape(-1);order=np.argsort(flat,kind='stable');sorted_ids=flat[order]
    added=0
    for vertex in mesh.get_non_manifold_vertices():
        a,b=np.searchsorted(sorted_ids,[vertex,vertex+1])
        incident=np.unique(order[a:b]//3);parent={int(i):int(i) for i in incident}
        def find(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        seen={}
        for i in incident:
            i=int(i)
            for other in faces[i]:
                if other==vertex:continue
                if other in seen:parent[find(i)]=find(seen[other])
                else:seen[other]=i
        groups={}
        for i in incident:groups.setdefault(find(int(i)),[]).append(int(i))
        for fan in list(groups.values())[1:]:
            replacement=len(vertices);vertices.append(vertices[vertex]);added+=1
            for i in fan:faces[i,faces[i]==vertex]=replacement
    result=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(faces))
    if not result.is_vertex_manifold():raise ValueError('UV input still has disconnected vertex fans')
    return result,added


def bake(path,triangles=250000,size=2048):
    path=Path(path);started=time.monotonic()
    meta=json.loads(path.with_suffix('.json').read_text())
    source_cache=PROJECT.parent/'analysis/dense-las'
    source_manifest=(source_cache/'manifest.json').read_bytes()
    source=module.dense.load_region(source_cache,meta['boundsLocal'],halo=meta['haloMetres'])
    tree=module.cKDTree(source['xyz'])
    cache=path.with_name(path.name+f'-lod-{triangles}.npz')
    stamp=[path.with_suffix('.glb').stat().st_mtime_ns,triangles,2]
    if cache.exists() and np.load(cache)['stamp'].tolist()==stamp:
        saved=np.load(cache)
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(saved['vertices']),o3d.utility.Vector3iVector(saved['faces']))
        before=int(saved['before']);split_vertices=int(saved['split'])
        adaptive=json.loads(str(saved['adaptive']))
    else:
        mesh=o3d.io.read_triangle_mesh(str(path.with_suffix('.glb')))
        print('Reducing triangles',len(mesh.triangles),'target',triangles,flush=True)
        mesh=mesh.simplify_quadric_decimation(triangles,maximum_error=.0001)
        before=len(mesh.triangles)
        # Large triangles on flat roads are valid after simplification. Recheck
        # vertex/centre/midpoint support instead of inheriting the fine edge bound.
        mesh=module.supported_mesh(mesh,tree,meta['boundsLocal'],edge=float('inf'))
        mesh.remove_non_manifold_edges();mesh.remove_degenerate_triangles();mesh.remove_unreferenced_vertices()
        parent=o3d.io.read_triangle_mesh(str(path.with_suffix('.glb')))
        parent_scene=o3d.t.geometry.RaycastingScene();parent_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(parent))
        keep,adaptive=adaptive_face_support(mesh,parent_scene)
        mesh.remove_triangles_by_mask(~keep);mesh.remove_unreferenced_vertices()
        del parent,parent_scene
        mesh,split_vertices=split_vertex_fans(mesh)
        np.savez(cache,vertices=np.asarray(mesh.vertices),faces=np.asarray(mesh.triangles),before=before,
                 split=split_vertices,stamp=stamp,adaptive=json.dumps(adaptive))
    mesh.compute_vertex_normals()
    print('UV atlas',len(mesh.triangles),'triangles',flush=True)
    atlas=xatlas.Atlas();atlas.add_mesh(np.asarray(mesh.vertices).astype('f4'),np.asarray(mesh.triangles).astype('u4'))
    pack=xatlas.PackOptions();pack.resolution=size;pack.padding=4
    atlas.generate(pack_options=pack)
    if atlas.atlas_count!=1:raise ValueError('Output requires exactly one UV atlas')
    mapping,atlas_faces,atlas_uv=atlas[0]
    old_normals=np.asarray(mesh.vertex_normals)
    mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(mesh.vertices)[mapping]),o3d.utility.Vector3iVector(atlas_faces))
    mesh.vertex_normals=o3d.utility.Vector3dVector(old_normals[mapping])
    tensor=o3d.t.geometry.TriangleMesh.from_legacy(mesh)
    tensor.triangle['texture_uvs']=o3d.core.Tensor(atlas_uv[atlas_faces].astype('f4'))
    tensor.vertex['valid']=o3d.core.Tensor(np.ones((len(mesh.vertices),1),'f4'))
    print('Baking measured-colour texture',flush=True)
    baked=tensor.bake_vertex_attr_textures(size,{'positions','valid'},margin=3,update_material=False)
    xyz=baked['positions'].numpy();valid=baked['valid'].numpy().reshape(size,size)>.5
    rgb=np.full((size,size,3),230,'u1')
    # Chunk the texture lookup to bound the temporary nearest-neighbour buffers.
    ids=np.flatnonzero(valid.reshape(-1));flat=rgb.reshape(-1,3)
    for start in range(0,len(ids),100000):
        chosen=ids[start:start+100000]
        distance,nearest=tree.query(xyz.reshape(-1,3)[chosen],k=4,workers=8)
        weight=1/np.maximum(distance,.004)**2
        weight[distance>np.maximum(distance[:,:1]+.015,.04)]=0
        flat[chosen]=np.rint((source['rgb'][nearest]*weight[:,:,None]).sum(axis=1)/weight.sum(axis=1)[:,None]).astype('u1')
    # Bake uses top-row-first images and standard bottom-origin UVs; glTF's
    # texture coordinates are top-origin, so invert v exactly once on export.
    uv=gltf_uv_from_atlas(tensor.triangle['texture_uvs'].numpy().reshape(-1,2))
    faces=np.asarray(mesh.triangles).reshape(-1)
    keys=np.column_stack([faces.astype('u4'),uv.view('u4').reshape(-1,2)])
    _,first,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    vertices=np.asarray(mesh.vertices)[faces[first]].astype('<f4')
    normals=np.asarray(mesh.vertex_normals)[faces[first]].astype('<f4')
    colours=np.full((len(vertices),3),255,'u1')
    image=io.BytesIO();Image.fromarray(rgb).save(image,format='JPEG',quality=95,subsampling=0)
    output=path.with_name(path.name+'-textured')
    module.write_glb(output.with_suffix('.glb'),vertices,inverse.reshape(-1,3).astype('<u4'),
                     colours,normals,uv[first].astype('<f4'),image.getvalue())
    # Verify simplification against dense original returns, not just source mesh.
    bounds=meta['boundsLocal'];p=source['xyz']
    core=np.flatnonzero((p[:,0]>=bounds[0])&(p[:,0]<bounds[1])&(p[:,1]>=bounds[2])&(p[:,1]<bounds[3]))
    chosen=core[np.linspace(0,len(core)-1,min(150000,len(core)),dtype=int)]
    scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    error=scene.compute_distance(o3d.core.Tensor(p[chosen].copy())).numpy()
    vertex_distance,_=tree.query(vertices,workers=8)
    corners=vertices[inverse.reshape(-1,3)]
    maximum_edge=max(float(np.linalg.norm(corners[:,a]-corners[:,b],axis=1).max()) for a,b in [(0,1),(1,2),(2,0)])
    result={**meta,'method':meta['method']+'; quadratic detail reduction and measured-colour UV baking',
            'colourSourceCachePath':str(source_cache.resolve()),
            'colourSourceCacheManifestSHA256':hashlib.sha256(source_manifest).hexdigest(),
            'colourSourceCacheSampling':json.loads(source_manifest)['sampling'],
            'colourSourceRegionRecords':len(source),
            'auditDomain':'Actual original every-record spatial-cache values within this region; at most150000 evenly indexed records for the output distance audit',
            'parentMesh':path.with_suffix('.glb').name,'vertices':len(vertices),'triangles':len(mesh.triangles),
            'targetTriangles':triangles,'postSimplificationTrianglesRemoved':before-len(mesh.triangles),
            'disconnectedVertexFansSplit':split_vertices,'maximumEdgeMetres':maximum_edge,
            'adaptiveParentSupport':adaptive,
            'vertexSupportMetres':module.summary(vertex_distance),
            'textureSize':size,'textureUVCharts':atlas.get_mesh_chart_count(0),
            'textureUVMethod':'xatlas 0.0.11; no vertex position changes',
            'textureUtilization':atlas.utilization,'textureCoveredPixels':len(ids),
            'sourceToMeshDistanceMetres':module.summary(error),'coverageWithin5cm':float(np.mean(error<=.05)),
            'coverageWithin10cm':float(np.mean(error<=.10)),
            'colour':f'{size}-pixel UV atlas sampled from four nearest original LAS RGB returns; no source mutation',
            'fileBytes':output.with_suffix('.glb').stat().st_size,'bakeSeconds':round(time.monotonic()-started,2),
            'limits':meta['limits']+' Reduced geometry and scan-colour texture are an approximation; raw-photograph texturing remains a separate stage.'}
    # High-res height audits do not describe the decimated output.
    result.pop('heightStratifiedAudit',None)
    output.with_suffix('.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mesh',type=Path,nargs='+');p.add_argument('--triangles',type=int,default=250000)
    p.add_argument('--size',type=int,default=2048)
    args=p.parse_args()
    for mesh in args.mesh:bake(mesh,args.triangles,args.size)
