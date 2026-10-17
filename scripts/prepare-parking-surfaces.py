"""Bounded local Poisson experiment for measured parking detail, never car CAD.

Each parking region is reconstructed independently at its own physical scale.
Strict source/edge support trimming retains holes rather than inventing bodies.
"""
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('details', PROJECT / 'scripts/prepare-details.py')
details = importlib.util.module_from_spec(spec)
spec.loader.exec_module(details)
np = details.np
from scipy.spatial import cKDTree
import open3d as o3d

OUT = PROJECT / 'public/replica'


def trim(mesh, tree):
    distance, _ = tree.query(np.asarray(mesh.vertices), workers=8)
    mesh.remove_vertices_by_mask(distance > .14)
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)
    p = vertices[faces]
    longest = np.maximum.reduce([np.linalg.norm(p[:,0]-p[:,1], axis=1),
                                 np.linalg.norm(p[:,1]-p[:,2], axis=1),
                                 np.linalg.norm(p[:,2]-p[:,0], axis=1)])
    centre_distance, _ = tree.query(p.mean(axis=1), workers=8)
    # Additional edge midpoint checks prevent a supported centre/endpoints from
    # hiding a narrow unsupported bridge across a hole between measured objects.
    midpoints = [(p[:,0]+p[:,1])/2, (p[:,1]+p[:,2])/2, (p[:,2]+p[:,0])/2]
    bad = (longest > .45) | (centre_distance > .16)
    for midpoint in midpoints:
        d, _ = tree.query(midpoint, workers=8)
        bad |= d > .16
    mesh.remove_triangles_by_mask(bad)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_unreferenced_vertices()
    return mesh


def stats(values):
    return {'median': float(np.median(values)), 'p95': float(np.quantile(values,.95)),
            'p99': float(np.quantile(values,.99)), 'max': float(np.max(values))}


def main():
    points = np.fromfile(OUT / 'building.positions.bin', '<f4').reshape(-1,3)
    colors = np.fromfile(OUT / 'building.colors.bin', 'uint8').reshape(-1,3)
    origin = np.array(json.loads((OUT/'building.json').read_text())['origin'])
    world = points[:,:2].astype(float)+origin[:2]
    pixels = np.column_stack(((world[:,0]-339750)/900*1497,
                             (2778350.09765625-world[:,1])/1000.1953125*1664))
    baseline = o3d.io.read_triangle_mesh(str(OUT/'building-surface.glb'))
    base_scene = o3d.t.geometry.RaycastingScene()
    base_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(baseline))
    binary=bytearray(); views=[]; accessors=[]; meshes=[]; nodes=[]; regions=[]

    def add(array, typ, component, bounds=False, normalized=False):
        while len(binary)%4: binary.append(0)
        views.append({'buffer':0,'byteOffset':len(binary),'byteLength':array.nbytes})
        binary.extend(array.tobytes())
        entry={'bufferView':len(views)-1,'componentType':component,'count':len(array),'type':typ}
        if bounds: entry.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        if normalized: entry['normalized']=True
        accessors.append(entry)
        return len(accessors)-1

    for name, landscape, polygon in details.REGIONS:
        if landscape: continue
        ids = np.flatnonzero(details.inside_polygon(pixels,polygon))
        selected = points[ids]
        height = selected[:,2]-details.local_floor(selected)
        keep = (height >= .35)&(height <= 3.)
        selected_height = height[keep]
        ids = ids[keep]
        source = points[ids]
        tree = cKDTree(source)
        cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(source.astype(float)))
        cloud=cloud.voxel_down_sample(.065)
        cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=.30,max_nn=30))
        cloud.orient_normals_consistent_tangent_plane(15)
        print(name, 'source',len(source),'samples',len(cloud.points),'reconstructing',flush=True)
        mesh,density=o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            cloud,depth=10,scale=1.02,n_threads=8)
        mesh.remove_vertices_by_mask(np.asarray(density)<np.quantile(density,.015))
        mesh=trim(mesh,tree)
        if len(mesh.triangles)>160000:
            mesh=mesh.simplify_quadric_decimation(160000,maximum_error=.0004)
            mesh=trim(mesh,tree)
        vertices=np.asarray(mesh.vertices).astype('<f4')
        faces=np.asarray(mesh.triangles).astype('<u4')
        assert len(faces)>1000, f'{name}: insufficient supported surface'
        distance,nearest=tree.query(vertices,workers=8)
        assert distance.max()<=.14001
        rgb=colors[ids[nearest]]
        local_scene=o3d.t.geometry.RaycastingScene()
        local_scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
        query=o3d.core.Tensor(source)
        base_distance=base_scene.compute_distance(query).numpy()
        new_distance=local_scene.compute_distance(query).numpy()
        # A local prototype is only accepted if source coverage improves without
        # relaxing the physical support threshold. Sparse surfaces stay sparse.
        improvement=float(np.mean(new_distance<=.10)-np.mean(base_distance<=.10))
        assert improvement > 0, f'{name}: no measured coverage improvement'
        regions.append({'id':name,'node':len(nodes),'landscape':False,
                        'sourcePoints':len(source),'normalSamples':len(cloud.points),
                        'sourceHeightAboveLocalFloorMetres': {
                            'min':float(selected_height.min()), **stats(selected_height)},
                        'vertices':len(vertices),'triangles':len(faces),
                        'referencePixelPolygon':polygon,
                        'boundsLocal':{'min':vertices.min(axis=0).tolist(),'max':vertices.max(axis=0).tolist()},
                        'vertexNearestSourceMetres':stats(distance),
                        'sourceToBaseMeshMetres':stats(base_distance),
                        'sourceToLocalMeshMetres':stats(new_distance),
                        'baseSourceFractionWithin10cm':float(np.mean(base_distance<=.10)),
                        'localSourceFractionWithin10cm':float(np.mean(new_distance<=.10)),
                        'coverageFractionImprovement':improvement})
        position=add(vertices,'VEC3',5126,True)
        colour=add(rgb,'VEC3',5121,normalized=True)
        index=add(faces.reshape(-1),'SCALAR',5125)
        meshes.append({'primitives':[{'attributes':{'POSITION':position,'COLOR_0':colour},'indices':index}]})
        nodes.append({'name':name,'mesh':len(meshes)-1})
        print(name,len(vertices),len(faces),'coverage +',improvement,flush=True)
    doc={'asset':{'version':'2.0','generator':'Local source-supported parking reconstruction'},
         'scene':0,'scenes':[{'nodes':list(range(len(nodes)))}],'nodes':nodes,'meshes':meshes,
         'buffers':[{'byteLength':len(binary)}],'bufferViews':views,'accessors':accessors}
    header=json.dumps(doc,separators=(',',':')).encode(); header+=b' '*(-len(header)%4)
    binary+=b'\0'*(-len(binary)%4)
    blob=struct.pack('<III',0x46546c67,2,28+len(header)+len(binary))
    blob+=struct.pack('<II',len(header),0x4e4f534a)+header
    blob+=struct.pack('<II',len(binary),0x004e4942)+binary
    (OUT/'parking-surfaces.glb').write_bytes(blob)
    metadata={'source':'Unchanged prepared LAS position/RGB buffers', 'origin':origin.tolist(),
              'method':'Independent parking-region local Poisson depth 10; 0.065m normal-preparation voxel',
              'normalRadiusMetres':.30,'vertexSupportCutoffMetres':.14,
              'minimumAboveLocalFloorMetres':.35,'maximumAboveLocalFloorMetres':3.,
              'floorEstimate':'4m-cell source q10 minimum over adjacent cells; approximation',
              'centreAndMidpointSupportCutoffMetres':.16,'maximumEdgeMetres':.45,
              'count':sum(r['triangles'] for r in regions),'regions':regions,
              'binaryBytes':len(blob),
              'limits':'Prototype measured-surface approximation. Source gaps/occluded cars remain. '
                       'Context polygons are not semantic car classification. No vehicle templates or '
                       'architectural geometry. Separate region meshes, strict edge/centre support '
                       'prevent broad unsupported bridging; nearby source surfaces can still merge. '
                       'Use source discs for fine holes and Original points for measured truth.'}
    (OUT/'parking-surfaces.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2),flush=True)


if __name__=='__main__': main()
