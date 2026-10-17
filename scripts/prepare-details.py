"""Add bounded, source-centred patches in aerial-traced parking/tree contexts.

Run with bundled Python from any directory. Uses the existing isolated NumPy /
SciPy environment. Does not mutate the LAS, measured point buffers or global
Poisson surface. Region names describe aerial context, not point classification.
"""
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent / 'analysis/python-packages'))
import numpy as np
from scipy.ndimage import minimum_filter
from scipy.spatial import cKDTree

OUT = PROJECT / 'public/replica'
# Old reference-pixel coordinates in analysis/building-reference.png. The image
# establishes context only: cars/foliage are reconstructed solely from the scan.
REGIONS = [
    ('west-parking', False, [(516,1092),(530,1092),(570,1193),(557,1203)]),
    ('south-parking', False, [(570,1247),(639,1268),(700,1290),
                            (714,1314),(633,1300),(561,1277)]),
    ('southeast-parking', False, [(807,1255),(848,1245),(873,1265),(828,1290)]),
    ('west-tree-row', True, [(416,1133),(435,1130),(524,1270),(500,1288)]),
    ('south-tree-row', True, [(509,1302),(640,1347),(705,1357),(755,1355),
                            (810,1337),(860,1310),(870,1323),(810,1352),
                            (755,1370),(705,1375),(640,1360),(500,1320)]),
    ('east-tree-row', True, [(938,1170),(954,1175),(936,1220),(920,1254),
                           (895,1286),(881,1276),(904,1245),(923,1208)]),
]


def inside_polygon(xy, polygon):
    """Ray crossing, with vertices in the same units as xy."""
    inside = np.zeros(len(xy), dtype=bool)
    previous = polygon[-1]
    for current in polygon:
        x0, y0 = previous
        x1, y1 = current
        if y1 != y0:
            cross = ((y1 > xy[:, 1]) != (y0 > xy[:, 1]))
            inside ^= cross & (xy[:, 0] < (x0-x1)*(xy[:, 1]-y1)/(y0-y1)+x1)
        previous = current
    return inside


def local_floor(points):
    """Conservative 4m-cell 10th percentile, minimum over adjacent cells."""
    cell = np.floor((points[:, :2] - points[:, :2].min(axis=0)) / 4).astype(int)
    shape = cell.max(axis=0) + 1
    keys = np.ravel_multi_index(cell.T, shape)
    floor = np.full(shape, np.inf)
    order = np.argsort(keys, kind='stable')
    cuts = np.r_[0, np.flatnonzero(np.diff(keys[order]))+1, len(keys)]
    for start, end in zip(cuts[:-1], cuts[1:]):
        indices = order[start:end]
        floor[tuple(cell[indices[0]])] = np.quantile(points[indices, 2], .1)
    floor = minimum_filter(floor, size=3, mode='nearest')
    return floor[tuple(cell.T)]


def patches(points):
    """Local PCA discs; weakly supported, linear and volumetric sets omitted."""
    tree = cKDTree(points)
    distances, neighbors = tree.query(points, k=16, distance_upper_bound=.30, workers=8)
    valid = np.sum(np.isfinite(distances), axis=1) >= 8
    ids = np.flatnonzero(valid)
    normals, radii, accepted, stats = [], [], [], []
    for start in range(0, len(ids), 12000):
        batch = ids[start:start+12000]
        # First 8 neighbors are guaranteed to be finite. Limiting their extent
        # prevents a normal spanning unrelated objects or an occluded gap.
        near = neighbors[batch, :8]
        centered = points[near].astype('float64')
        centered -= centered.mean(axis=1, keepdims=True)
        values, vectors = np.linalg.eigh(np.einsum('nki,nkj->nij', centered, centered))
        good = ((values[:, 0] / np.maximum(values.sum(axis=1), 1e-12) < .12) &
                (values[:, 1] / np.maximum(values[:, 2], 1e-12) > .12) &
                (distances[batch, 7] <= .22))
        normal = vectors[good, :, 0]
        normal[normal[:, 2] < 0] *= -1
        accepted.extend(batch[good])
        normals.extend(normal)
        # Median of 2nd..4th neighbors captures spacing without crossing a void.
        spacing = np.median(distances[batch[good], 1:4], axis=1)
        radii.extend(np.clip(spacing * .8, .035, .12))
        stats.extend(spacing)
    return (np.asarray(accepted, dtype=int), np.asarray(normals, dtype='<f4'),
            np.asarray(radii, dtype='<f4'), np.asarray(stats))


def main():
    source = np.fromfile(OUT / 'building.positions.bin', dtype='<f4').reshape(-1, 3)
    colors = np.fromfile(OUT / 'building.colors.bin', dtype='uint8').reshape(-1, 3)
    origin = np.array(json.loads((OUT / 'building.json').read_text())['origin'])
    world_xy = source[:, :2].astype('float64') + origin[:2]
    pixels = np.column_stack(((world_xy[:, 0]-339750)/900*1497,
                             (2778350.09765625-world_xy[:, 1])/1000.1953125*1664))
    taken = np.zeros(len(source), dtype=bool)
    arrays = {key: [] for key in ['positions', 'colors', 'normals', 'radii']}
    regions = []
    offset = 0
    for name, landscape, polygon in REGIONS:
        candidates = np.flatnonzero(inside_polygon(pixels, polygon) & ~taken)
        measured = source[candidates]
        height = measured[:, 2] - local_floor(measured)
        # Parking height cap excludes the covered parking canopy roofs; tree-row
        # polygons avoid the building and allow measured branches/crowns.
        nonground = (height >= (.5 if landscape else .30)) & (height <= (12 if landscape else 2.8))
        chosen = candidates[nonground]
        voxel = np.floor(source[chosen] / .09).astype('int64')
        _, unique = np.unique(voxel, axis=0, return_index=True)
        chosen = chosen[np.sort(unique)]
        accepted, normals, radii, spacing = patches(source[chosen])
        chosen = chosen[accepted]
        taken[chosen] = True
        count = len(chosen)
        assert count, f'No locally supported data in {name}'
        for key, value in [('positions', source[chosen]), ('colors', colors[chosen]),
                           ('normals', normals), ('radii', radii)]:
            arrays[key].append(value)
        regions.append({'id': name, 'start': offset, 'count': count,
                        'landscape': landscape, 'referencePixelPolygon': polygon,
                        'context': 'aerial tree-row context' if landscape else 'aerial parking context',
                        'sourceRegionPoints': len(candidates), 'heightFilteredPoints': int(nonground.sum()),
                        'normalCandidatePoints': len(unique),
                        'boundsLocal': {'min': source[chosen].min(axis=0).tolist(),
                                        'max': source[chosen].max(axis=0).tolist()},
                        'neighborSpacingMetres': {'median': float(np.median(spacing)),
                                                  'p95': float(np.quantile(spacing, .95))},
                        'radiusMetres': {'min': float(radii.min()), 'median': float(np.median(radii)),
                                         'max': float(radii.max())}})
        offset += count
        print(name, count, flush=True)
    # Audit against actual triangles, rather than nearest mesh vertices (which
    # would overstate gaps on large triangles). This measures local missing
    # detail; it cannot prove visibility from every camera or certify a repair.
    import open3d as o3d
    base = o3d.io.read_triangle_mesh(str(OUT / 'building-surface.glb'))
    raycast = o3d.t.geometry.RaycastingScene()
    raycast.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(base))
    all_positions = np.concatenate(arrays['positions'])
    all_radii = np.concatenate(arrays['radii'])
    base_distance = raycast.compute_distance(o3d.core.Tensor(all_positions)).numpy()
    for region in regions:
        start = region['start']
        end = start + region['count']
        distance = base_distance[start:end]
        region['distanceToBaseMeshMetres'] = {
            'median': float(np.median(distance)), 'p95': float(np.quantile(distance, .95)),
            'max': float(distance.max()),
            'fractionBeyond3cm': float(np.mean(distance > .03)),
            'fractionBeyondDiscRadius': float(np.mean(distance > all_radii[start:end])),
        }
        # Eight neighbours within .22m does not imply a continuous observed
        # surface. This explicitly reports centre spacing vs finite disc radius.
        points = all_positions[start:end]
        nearest, _ = cKDTree(points).query(points, k=2, workers=8)
        region['fractionNearestCentersWithinDiameter'] = float(
            np.mean(nearest[:, 1] <= 2 * all_radii[start:end]))
    byte_count = 0
    for key, parts in arrays.items():
        merged = np.concatenate(parts)
        assert np.isfinite(merged).all()
        byte_count += merged.nbytes
        (OUT / f'detail.{key}.bin').write_bytes(merged.tobytes())
    assert byte_count < 20_000_000
    metadata = {
        'source': 'building.positions.bin and building.colors.bin; unchanged original LAS selection',
        'origin': origin.tolist(), 'coordinateFrame': 'local XYZ metres, Z up; shared building origin',
        'method': 'Measured-centre oriented discs; deterministic 0.09m thinning; local 8-neighbor PCA normals',
        'regions': regions, 'count': offset, 'binaryBytes': byte_count,
        'positionsUnchanged': True, 'colorsUnchanged': True, 'maximumRadiusMetres': .12,
        'normalSupportRadiusMetres': .22, 'groundEstimate': '4m-cell q10 minimum over adjacent cells',
        'reference': 'analysis/building-reference.png aerial context; no image-generated object geometry',
        'referencePixelTransform': {'easting': '339750 + x / 1497 * 900',
                                    'northing': '2778350.09765625 - y / 1664 * 1000.1953125'},
        'normalAcceptance': '8 source neighbors within 0.22m; lambda0/sum <0.12; lambda1/lambda2 >0.12',
        'limits': 'Local visible-surface approximation, not watertight cars or botanical models. Region names '
                  'are contextual, not semantic classification. Source gaps, sparse crowns, occluded vehicles '
                  'and missing undersides remain. Discs do not connect separate objects. Scan and aerial '
                  'capture dates may differ. Existing global Poisson mesh remains unchanged; these patches '
                  'cannot remove distortions already present in that mesh. Original points hides this layer.'}
    meta = {'count': offset, **{key: f'detail.{key}.bin' for key in arrays}, 'metadata': metadata}
    (OUT / 'details.json').write_text(json.dumps(meta, indent=2)+'\n')
    (OUT / 'details-metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps({'count': offset, 'binaryBytes': byte_count}, indent=2))


if __name__ == '__main__':
    main()
