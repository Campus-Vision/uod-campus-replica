"""Connected triangle reconstruction from every-record LAS spatial bins.

Offline outputs remain separate from the approved browser assets until reviewed.
Uses real measurements, overlapping crops and source-supported triangle trimming.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT.parent
sys.path.insert(0,str(ROOT/'analysis/python-packages'))
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
spec=importlib.util.spec_from_file_location('dense_las',PROJECT/'scripts/dense-las.py')
dense=importlib.util.module_from_spec(spec);spec.loader.exec_module(dense)


def supported_mesh(mesh, tree, bounds, support=.10, face_support=.12, edge=.40):
    """Check vertices, centres and all edge midpoints, including after smoothing."""
    distances,_=tree.query(np.asarray(mesh.vertices),workers=8)
    mesh.remove_vertices_by_mask(distances>support)
    v=np.asarray(mesh.vertices);f=np.asarray(mesh.triangles)
    if not len(f): return mesh
    p=v[f];centres=p.mean(axis=1)
    xmin,xmax,ymin,ymax=bounds
    bad=((centres[:,0]<xmin)|(centres[:,0]>=xmax)|
         (centres[:,1]<ymin)|(centres[:,1]>=ymax))
    distance,_=tree.query(centres,workers=8);bad|=distance>face_support
    for a,b in [(0,1),(1,2),(2,0)]:
        distance,_=tree.query((p[:,a]+p[:,b])/2,workers=8)
        bad|=(distance>face_support)|(np.linalg.norm(p[:,a]-p[:,b],axis=1)>edge)
    mesh.remove_triangles_by_mask(bad)
    mesh.remove_degenerate_triangles();mesh.remove_duplicated_triangles();mesh.remove_unreferenced_vertices()
    return mesh


def write_glb(path,vertices,faces,colours,normals,uv=None,texture=None):
    payload=bytearray();views=[];accessors=[]
    def add(array,kind,component,bounds=False,normalized=False):
        while len(payload)%4: payload.append(0)
        views.append({'buffer':0,'byteOffset':len(payload),'byteLength':array.nbytes})
        payload.extend(array.tobytes())
        a={'bufferView':len(views)-1,'componentType':component,'count':len(array),'type':kind}
        if bounds: a.update(min=array.min(axis=0).tolist(),max=array.max(axis=0).tolist())
        if normalized:a['normalized']=True
        accessors.append(a);return len(accessors)-1
    attributes={'POSITION':add(vertices,'VEC3',5126,True),
                'NORMAL':add(normals,'VEC3',5126),
                'COLOR_0':add(colours,'VEC3',5121,normalized=True)}
    if uv is not None: attributes['TEXCOORD_0']=add(uv,'VEC2',5126)
    index=add(faces.reshape(-1),'SCALAR',5125)
    doc={'asset':{'version':'2.0','generator':'Dense original LAS connected reconstruction'},
         'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0,'name':path.stem}],
         'meshes':[{'primitives':[{'attributes':attributes,'indices':index}]}],
         'buffers':[{'byteLength':len(payload)}],'bufferViews':views,'accessors':accessors}
    if texture is not None:
        if uv is None: raise ValueError('Texture requires UV coordinates')
        while len(payload)%4:payload.append(0)
        views.append({'buffer':0,'byteOffset':len(payload),'byteLength':len(texture)})
        payload.extend(texture)
        doc['buffers'][0]['byteLength']=len(payload)
        doc['images']=[{'bufferView':len(views)-1,'mimeType':'image/jpeg'}]
        doc['samplers']=[{'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071}]
        doc['textures']=[{'source':0,'sampler':0}]
        doc['materials']=[{'doubleSided':True,'pbrMetallicRoughness':{
            'baseColorTexture':{'index':0},'roughnessFactor':1,'metallicFactor':0}}]
        doc['meshes'][0]['primitives'][0]['material']=0
    header=json.dumps(doc,separators=(',',':')).encode();header+=b' '*(-len(header)%4)
    payload+=b'\0'*(-len(payload)%4)
    path.write_bytes(struct.pack('<III',0x46546c67,2,28+len(header)+len(payload))+
                     struct.pack('<II',len(header),0x4e4f534a)+header+
                     struct.pack('<II',len(payload),0x004e4942)+payload)


def summary(x):
    finite=np.isfinite(x)
    return {'median':float(np.median(x[finite])),'p95':float(np.quantile(x[finite],.95)),
            'max':float(x[finite].max()),'nonfinite':int((~finite).sum())}


def reconstruct(cache,output,bounds,voxel=.04,depth=10,method='poisson',halo=2.):
    started=time.monotonic();output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    print('Loading every-record region with overlap',bounds,flush=True)
    records=dense.load_region(cache,bounds,halo)
    source=records['xyz'].copy();colors=records['rgb'].copy()
    if len(source)<1000: raise ValueError('Insufficient original measurements in region')
    # Preserve an actual measured representative in each occupied physical voxel.
    cells=np.floor(source/voxel).astype('i4')
    _,chosen=np.unique(cells,axis=0,return_index=True);del cells
    print('Original measurements',len(source),'normal samples',len(chosen),flush=True)
    cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(source[chosen].astype(float)))
    cloud,accepted=cloud.remove_statistical_outlier(nb_neighbors=20,std_ratio=2.5)
    cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=max(voxel*6,.18),max_nn=32))
    print('Orienting normals',len(cloud.points),flush=True)
    cloud.orient_normals_consistent_tangent_plane(12)
    print('Reconstructing connected',method,'surface',flush=True)
    if method=='poisson':
        mesh,density=o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(cloud,depth=depth,scale=1.03,n_threads=8)
        mesh.remove_vertices_by_mask(np.asarray(density)<np.quantile(density,.01))
        mesh=mesh.filter_smooth_taubin(number_of_iterations=2)
    else:
        mesh=o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            cloud,o3d.utility.DoubleVector([voxel*1.1,voxel*2,voxel*3.5]))
    tree=cKDTree(source)
    mesh=supported_mesh(mesh,tree,bounds)
    if len(mesh.triangles)<100: raise ValueError('Insufficient supported triangles')
    mesh.compute_vertex_normals()
    vertices=np.asarray(mesh.vertices).astype('<f4');faces=np.asarray(mesh.triangles).astype('<u4')
    normals=np.asarray(mesh.vertex_normals).astype('<f4')
    distances,nearest=tree.query(vertices,k=4,workers=8)
    weights=1/np.maximum(distances,.004)**2
    weights[distances>np.maximum(distances[:,:1]+.015,.04)]=0
    rgb=np.rint((colors[nearest]*weights[:,:,None]).sum(axis=1)/weights.sum(axis=1)[:,None]).astype('u1')
    write_glb(output.with_suffix('.glb'),vertices,faces,rgb,normals)
    # OBJ is an editable interchange copy; the GLB preserves the same triangles.
    mesh.vertex_colors=o3d.utility.Vector3dVector(rgb.astype(float)/255)
    o3d.io.write_triangle_mesh(str(output.with_suffix('.obj')),mesh,write_triangle_uvs=False)
    # Independent dense-source -> triangle distance, including unsampled records.
    core=((source[:,0]>=bounds[0])&(source[:,0]<bounds[1])&
          (source[:,1]>=bounds[2])&(source[:,1]<bounds[3]))
    core_ids=np.flatnonzero(core)
    audit_ids=core_ids[np.linspace(0,len(core_ids)-1,min(len(core_ids),150000),dtype=int)]
    scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    coverage=scene.compute_distance(o3d.core.Tensor(source[audit_ids])).numpy()
    # The old global surface is the comparison, not a claim about unseen truth.
    baseline=o3d.io.read_triangle_mesh(str(PROJECT/'public/replica/building-surface.glb'))
    old_scene=o3d.t.geometry.RaycastingScene();old_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(baseline))
    old=old_scene.compute_distance(o3d.core.Tensor(source[audit_ids])).numpy()
    meta={'source':'20261008121946091.las; every-record spatial cache',
          'origin':json.loads((Path(cache)/'manifest.json').read_text())['origin'],
          'boundsLocal':bounds,'haloMetres':halo,'originalRegionRecords':len(source),
          'coreRecords':len(core_ids),'voxelMetres':voxel,'normalSamples':len(cloud.points),
          'outlierNormalSamplesRemoved':len(chosen)-len(accepted),
          'method':method,'depth':depth if method=='poisson' else None,
          'vertices':len(vertices),'triangles':len(faces),
          'vertexSupportMetres':summary(distances[:,0]),'supportCutoffMetres':.10,
          'faceSupportCutoffMetres':.12,'maximumEdgeMetres':.40,
          'colour':'Inverse-distance weighted four nearest original RGB samples; no source mutation',
          'auditRecords':len(audit_ids),'sourceToMeshDistanceMetres':summary(coverage),
          'baselineSourceToMeshDistanceMetres':summary(old),
          'coverageWithin5cm':float(np.mean(coverage<=.05)),
          'baselineCoverageWithin5cm':float(np.mean(old<=.05)),
          'coverageWithin10cm':float(np.mean(coverage<=.10)),
          'baselineCoverageWithin10cm':float(np.mean(old<=.10)),
          'elapsedSeconds':round(time.monotonic()-started,2),
          'limits':'Triangle surface estimated from dense measured returns. Missing capture remains missing; density alone does not prove photorealism. Colour is source-derived, not photographic texture baking.'}
    output.with_suffix('.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta,indent=2),flush=True)
    return meta


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,default=ROOT/'analysis/dense-las')
    p.add_argument('--output',type=Path,default=ROOT/'analysis/dense-reconstruction/south-pilot')
    p.add_argument('--bounds',type=float,nargs=4,default=[-40,0,-240,-200])
    p.add_argument('--voxel',type=float,default=.04)
    p.add_argument('--depth',type=int,default=10)
    p.add_argument('--method',choices=['poisson','ball-pivoting'],default='poisson')
    args=p.parse_args()
    reconstruct(args.cache,args.output,args.bounds,args.voxel,args.depth,args.method)
