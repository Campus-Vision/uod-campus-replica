"""Reconstruct a measured surface, then trim away unsupported extrapolation.

Requires Open3D, NumPy and SciPy. Originals remain read-only. This is a surface
estimate derived from the scan, not a replacement architectural design.
"""
import sys, json, struct
from pathlib import Path
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent / 'analysis/python-packages'))
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

OUT = PROJECT / 'public/replica'
points = np.fromfile(OUT / 'building.positions.bin', dtype='<f4').reshape(-1, 3)
rgb = np.fromfile(OUT / 'building.colors.bin', dtype='uint8').reshape(-1, 3)
voxel = .16
print('Preparing measured reconstruction samples', flush=True)
cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points.astype('float64')))
cloud = cloud.voxel_down_sample(voxel)
print('Estimating local surface normals', len(cloud.points), flush=True)
cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=.65, max_nn=35))
cloud.orient_normals_consistent_tangent_plane(15)
print('Reconstructing continuous measured surfaces', flush=True)
mesh, density = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(cloud, depth=10, scale=1.02, n_threads=8)
mesh.remove_vertices_by_mask(np.asarray(density) < np.quantile(density, .025))
vertices = np.asarray(mesh.vertices)
triangles = np.asarray(mesh.triangles)
print('Trimming unsupported faces', len(vertices), len(triangles), flush=True)
tree = cKDTree(points)
distance, nearest = tree.query(vertices, workers=8)
mesh.remove_vertices_by_mask(distance > .32)
vertices = np.asarray(mesh.vertices)
triangles = np.asarray(mesh.triangles)
p = vertices[triangles]
longest = np.maximum.reduce([np.linalg.norm(p[:, 0] - p[:, 1], axis=1),
                            np.linalg.norm(p[:, 1] - p[:, 2], axis=1),
                            np.linalg.norm(p[:, 2] - p[:, 0], axis=1)])
centre_distance, _ = tree.query(p.mean(axis=1), workers=8)
mesh.remove_triangles_by_mask((longest > 1.2) | (centre_distance > .35))
mesh.remove_degenerate_triangles(); mesh.remove_duplicated_triangles(); mesh.remove_unreferenced_vertices()
if len(mesh.triangles) > 1200000:
    mesh = mesh.simplify_quadric_decimation(1200000, maximum_error=.0025)
vertices = np.asarray(mesh.vertices).astype('<f4')
indices = np.asarray(mesh.triangles).astype('<u4')
distance, nearest = tree.query(vertices, workers=8)
# Reject a bad approximation rather than shipping a distorted building.
assert np.quantile(distance, .99) < .32
colours = rgb[nearest].astype('uint8')

# Minimal GLB with source sRGB bytes. The app uses a custom unlit shader so these
# bytes are not mistaken for glTF linear vertex colour and double-encoded.
binary = bytearray(); views = []; accessors = []
def add(array, typ, component, bounds=False, normalized=False):
    while len(binary) % 4: binary.append(0)
    views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': array.nbytes})
    binary.extend(array.tobytes())
    item = {'bufferView': len(views)-1, 'componentType': component, 'count': len(array), 'type': typ}
    if bounds: item.update({'min': array.min(axis=0).tolist(), 'max': array.max(axis=0).tolist()})
    if normalized: item['normalized'] = True
    accessors.append(item); return len(accessors)-1
position = add(vertices, 'VEC3', 5126, True)
colour = add(colours, 'VEC3', 5121, normalized=True)
index = add(indices.reshape(-1), 'SCALAR', 5125)
doc = {'asset': {'version': '2.0', 'generator': 'UoD measured surface reconstruction'},
       'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
       'meshes': [{'primitives': [{'attributes': {'POSITION': position, 'COLOR_0': colour}, 'indices': index}]}],
       'buffers': [{'byteLength': len(binary)}], 'bufferViews': views, 'accessors': accessors}
header = json.dumps(doc, separators=(',', ':')).encode(); header += b' ' * (-len(header) % 4)
binary += b'\0' * (-len(binary) % 4)
blob = struct.pack('<III', 0x46546c67, 2, 28 + len(header) + len(binary))
blob += struct.pack('<II', len(header), 0x4e4f534a) + header
blob += struct.pack('<II', len(binary), 0x004e4942) + binary
(OUT / 'building-surface.glb').write_bytes(blob)
metadata = {'source': 'building.positions.bin and building.colors.bin, derived from original LAS',
            'method': 'Oriented-normal Poisson reconstruction, depth 10; proximity and triangle support trimming',
            'voxelMetres': voxel, 'vertices': len(vertices), 'triangles': len(indices),
            'nearestSourceDistanceMetres': {'median': float(np.median(distance)), 'p95': float(np.quantile(distance, .95)), 'p99': float(np.quantile(distance, .99)), 'max': float(distance.max())},
            'maximumRetainedEdgeMetres': 1.2, 'supportCutoffMetres': .32,
            'colour': 'Nearest original captured RGB; reversible natural daylight display grading',
            'limits': 'Surface estimation smooths small detail. Unsupported areas are removed; source occlusions may remain. Use Original points for measured truth.'}
(OUT / 'building-surface.json').write_text(json.dumps(metadata, indent=2))
provenance = json.loads((OUT / 'provenance.json').read_text())
provenance['building-surface.glb'] = metadata
(OUT / 'provenance.json').write_text(json.dumps(provenance, indent=2))
print(json.dumps(metadata, indent=2), flush=True)
