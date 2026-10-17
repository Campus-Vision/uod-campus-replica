"""Infill only the aerial-confirmed western reflective roof, preserving the scan.

Run with the bundled Python. NumPy, SciPy and Open3D are loaded from the existing
isolated analysis/python-packages directory. No source or measured asset is edited.
Height follows robust measured upper-rim stations; unobserved transverse roof
shape is explicitly an interpolation, not surveyed architecture.
"""
import json
import struct
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(ROOT / 'analysis/python-packages'))
import numpy as np
from scipy.spatial import Delaunay, cKDTree
from scipy.interpolate import PchipInterpolator
import open3d as o3d

OUT = PROJECT / 'public/replica'
ORIGIN = np.array([340150., 2777800., 50.])
# Traced after inspecting building-reference.png, roof-support.png and the full
# georeferenced aerial. The west/south edges coincide with measured rim traces;
# the east edge follows the visible roof/courtyard transition, not the courtyard.
OUTER_PIXELS = np.array([
    [555,1086], [554,1097], [554,1108], [556,1121], [559,1134],
    [564,1147], [571,1159], [580,1171], [591,1183], [604,1195],
    [618,1207], [638,1220]], dtype=float)
INNER_PIXELS = np.array([
    [593,1089], [594,1100], [598,1113], [604,1125], [612,1137],
    [622,1149], [634,1160], [646,1168], [659,1175]], dtype=float)
SPACING = .65
OVERLAP_OFFSET = .035


def reference_to_world(pixels):
    pixels = np.asarray(pixels)
    return np.column_stack((339750 + pixels[:,0] / 1497 * 900,
                            2778350.09765625 - pixels[:,1] / 1664 * 1000.1953125))


def inside(points, polygon):
    """Even-odd polygon membership, with tiny boundary tolerance handled by callers."""
    result = np.zeros(len(points), dtype=bool)
    x, y = points.T
    for a,b in zip(polygon, np.roll(polygon,-1,axis=0)):
        if abs(b[1]-a[1]) < 1e-10:
            continue
        result ^= ((a[1]>y)!=(b[1]>y)) & (x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
    return result


def resample(path, spacing):
    length = np.linalg.norm(np.diff(path,axis=0),axis=1)
    cumulative = np.r_[0.,np.cumsum(length)]
    t = np.linspace(0,cumulative[-1],int(np.ceil(cumulative[-1]/spacing))+1)
    return np.column_stack([np.interp(t,cumulative,path[:,k]) for k in range(2)]),t


def read_glb_geometry(path):
    """Read only the POSITION/index accessors from the existing local GLB."""
    blob = path.read_bytes()
    json_length = struct.unpack_from('<I',blob,12)[0]
    doc = json.loads(blob[20:20+json_length])
    binary = memoryview(blob)[28+json_length:]
    primitive = doc['meshes'][0]['primitives'][0]
    def read(index, width, dtype):
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        start = view.get('byteOffset',0)+accessor.get('byteOffset',0)
        return np.frombuffer(binary,dtype=dtype,count=accessor['count']*width,offset=start).reshape(-1,width).copy()
    return read(primitive['attributes']['POSITION'],3,'<f4'),read(primitive['indices'],1,'<u4').reshape(-1,3)


def prepare():
    outer = reference_to_world(OUTER_PIXELS)
    inner = reference_to_world(INNER_PIXELS)
    polygon = np.concatenate([outer, inner[::-1]])
    points = np.fromfile(OUT/'building.positions.bin',dtype='<f4').reshape(-1,3).astype(float)+ORIGIN
    # Limit support to the actual western rim. Full-height wall returns do not
    # get averaged into the roof: estimate a robust upper 95th percentile instead.
    stations, station_s = resample(outer,2.5)
    crop_min,crop_max = polygon.min(axis=0)-4,polygon.max(axis=0)+4
    keep = ((points[:,:2]>=crop_min)&(points[:,:2]<=crop_max)).all(axis=1)&(points[:,2]>65)
    local = points[keep]
    tree = cKDTree(local[:,:2])
    samples = tree.query_ball_point(stations,2.4)
    counts = np.array([len(s) for s in samples])
    if counts.min()<30:
        raise ValueError('Roof rim lacks enough measured supports; inspect before extrapolating')
    upper = np.array([np.quantile(local[s,2],.95) for s in samples])
    # A short running median rejects isolated parapet clutter, retaining the
    # measured longitudinal profile. No arbitrary absolute roof height is used.
    profile = np.array([np.median(upper[max(0,j-1):min(len(upper),j+2)]) for j in range(len(upper))])
    interpolator = PchipInterpolator(station_s,profile)
    fine_rim,fine_s = resample(outer,.15)
    rim_tree = cKDTree(fine_rim)
    def height(xy):
        distance,nearest = rim_tree.query(xy)
        return interpolator(fine_s[nearest]),distance

    boundary,_ = resample(np.vstack([polygon,polygon[0]]),SPACING)
    x = np.arange(crop_min[0]+4,crop_max[0]-4,SPACING)
    y = np.arange(crop_min[1]+4,crop_max[1]-4,SPACING)
    grid = np.stack(np.meshgrid(x,y),axis=-1).reshape(-1,2)
    grid = grid[inside(grid,polygon)]
    xy = np.unique(np.round(np.vstack([grid,boundary[:-1]]),5),axis=0)
    faces = Delaunay(xy).simplices
    triangles = xy[faces]
    # Clip Delaunay triangles to the traced concave footprint. Centres and all
    # edge midpoints prevent triangles bridging the courtyard-side concavity.
    valid = inside(triangles.mean(axis=1),polygon)
    for a,b in [(0,1),(1,2),(2,0)]:
        midpoint=(triangles[:,a]+triangles[:,b])/2
        # A midpoint on the measured outline is also valid.
        rim_distance = cKDTree(boundary).query(midpoint)[0]
        valid &= inside(midpoint,polygon)|(rim_distance<SPACING*.51)
    faces = faces[valid]
    triangle_xy=xy[faces]
    edge_b = triangle_xy[:,1]-triangle_xy[:,0]
    edge_c = triangle_xy[:,2]-triangle_xy[:,0]
    signed = edge_b[:,0]*edge_c[:,1]-edge_b[:,1]*edge_c[:,0]
    faces[signed<0] = faces[signed<0][:,[0,2,1]]
    faces = faces[np.abs(signed)>1e-6]
    z,distance = height(xy)
    vertices = np.column_stack([xy,z+OVERLAP_OFFSET])-ORIGIN

    # Probe the actual pre-existing measured mesh at every patch triangle centre.
    # Rays start above the whole building; comparison requires nearby elevation,
    # so courtyard/ground faces cannot masquerade as roof coverage.
    measured_vertices,measured_faces = read_glb_geometry(OUT/'building-surface.glb')
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(measured_vertices),o3d.core.Tensor(measured_faces))
    centres = vertices[faces].mean(axis=1)
    rays = np.column_stack([centres[:,:2],np.full(len(centres),60.),np.zeros((len(centres),2)),np.full(len(centres),-1.)]).astype('float32')
    hits = scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy()
    existing_z = 60.-hits
    supported = np.isfinite(hits)&(np.abs(existing_z-centres[:,2])<.35)
    missing_fraction = float((~supported).mean())
    # Preserve existing roof tiles at matching height; 3.5 cm display clearance
    # covers only the narrow joins where the patch meets measured geometry.
    faces = faces[~supported]
    used,remap = np.unique(faces,return_inverse=True)
    faces=remap.reshape(-1,3)
    vertices=vertices[used]
    xy=xy[used]
    uv=np.column_stack([(xy[:,0]-339600)/1050,(2778350-xy[:,1])/1000])
    assert missing_fraction>.8, 'Repair is not primarily a missing roof; inspect footprint'
    assert np.isfinite(vertices).all() and len(faces)>100
    source_ids=np.unique(np.concatenate(samples))
    metadata={
        'schema':1,'origin':ORIGIN.tolist(),'coordinateSystem':'EPSG:32640; metres, Z up',
        'footprintWorld':polygon.tolist(),'footprintReferencePixels':np.vstack([OUTER_PIXELS,INNER_PIXELS[::-1]]).tolist(),
        'source':{'geometry':'Unchanged building.positions.bin original measured points; western upper rim only',
                  'footprint':'Manual image trace checked against analysis/building-reference.png and analysis/roof-support.png',
                  'appearance':'Esri World Imagery, campus-aerial.jpg; analysis/aerial-georef.json',
                  'sourceCapture':'20261008121946091.las'},
        'method':'Constrained aerial footprint; robust 95th-percentile rim height stations, 3-station median, PCHIP along measured rim; constant transverse extrapolation at each closest rim station',
        'supportProfile':{'pointCount':int(len(source_ids)),'stationCount':len(stations),'stationRadiusMetres':2.4,
                          'minimumStationPointCount':int(counts.min()),'upperQuantile':.95,
                          'elevationMin':float(profile.min()),'elevationMax':float(profile.max()),
                          'rawStationElevationMin':float(upper.min()),'rawStationElevationMax':float(upper.max()),
                          'maximumDistanceFromMeasuredRimMetres':float(distance.max()),
                          'stations':[{'worldXY':p.tolist(),'upperElevation':float(u),'filteredElevation':float(h),'count':int(n)} for p,u,h,n in zip(stations,upper,profile,counts)]},
        'baselineCoverage':{'method':'Vertical ray intersections with unchanged building-surface.glb within 0.35 m of rim-estimated roof',
                            'probeCount':len(supported),'coveredFraction':float(supported.mean()),'missingFraction':missing_fraction,
                            'matchingMeasuredTrianglesOmitted':int(supported.sum())},
        'gridSpacingMetres':SPACING,'overlapClearanceMetres':OVERLAP_OFFSET,'vertices':len(vertices),'triangles':len(faces),
        'aerialExtent':{'xmin':339600,'ymin':2777350,'xmax':340650,'ymax':2778350},
        'uvConvention':'u=(E-xmin)/(xmax-xmin), v=(ymax-N)/(ymax-ymin); image top is v=0',
        'confidence':{'footprint':'Image-constrained, manually traced; not a surveyed outline','height':'Measured upper-rim constrained longitudinally; transverse roof shape unobserved'},
        'limits':'Estimated aerial-informed infill. Roof interior and transverse curvature are not measured; closest-rim height is interpolated across the reflective gap. Upper-wall/parapet returns may bias roof height. Aerial has finite resolution and may predate the scan. This patch has no 0.32 m surface-to-scan accuracy claim; no hidden facade is inferred. Original points and measured surface remain unchanged.'}
    result={'positions':np.round(vertices,5).reshape(-1).tolist(),'uv':np.round(uv,9).reshape(-1).tolist(),'indices':faces.reshape(-1).tolist(),'metadata':metadata}
    (OUT/'roof-repair.json').write_text(json.dumps(result,separators=(',',':')))
    (OUT/'roof-provenance.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps({k:metadata[k] for k in ['vertices','triangles','baselineCoverage','supportProfile']},indent=2),flush=True)


if __name__=='__main__':
    prepare()

