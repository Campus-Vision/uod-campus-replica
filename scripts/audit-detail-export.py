"""Review exported detail geometry against fresh, uniform original LAS records.

Writes PREFIX-review.json only. Agreement is internal source-to-surface distance,
not independent survey accuracy, semantic classification, or texture quality.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
spec = importlib.util.spec_from_file_location('dense_las', PROJECT/'scripts/dense-las.py')
dense = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dense)
np = dense.np
SEED = 2026101709  # Separate from the earlier 20261017/evenly indexed audits.
Z_EDGES = [-8, 0, 3, 12, 25, 45]
CHUNK = 500000


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_identity(path):
    path = Path(path)
    before = path.stat()
    digest = file_hash(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f'File changed during hashing: {path}')
    return {'path': str(path.resolve()), 'sha256': digest, 'bytes': after.st_size,
            'modifiedNs': after.st_mtime_ns}


def check_original(meta):
    original = Path(meta['source'])
    stat = original.stat()
    if stat.st_size != meta['sourceBytes'] or stat.st_mtime_ns != meta['sourceModifiedNs']:
        raise ValueError('Original LAS changed since extraction; provenance audit required')
    return {'path': str(original.resolve()), 'bytes': stat.st_size,
            'modifiedNs': stat.st_mtime_ns, 'matchesSourceManifest': True}


def validate_cache(cache):
    cache = Path(cache)
    meta = json.loads((cache/'manifest.json').read_text())
    if (meta.get('voxelMetres') is not None or 'parentManifestSHA256' in meta
            or 'inputRecordsRetained' in meta
            or meta.get('sampling') != 'Every LAS record; no temporal or voxel sampling'):
        raise ValueError('Review requires the original every-record cache, never a voxel/subset cache')
    check_original(meta)
    if (meta['recordsRead'] != meta['header']['count']
            or sum(meta['bins'].values()) != meta['recordsRetained']
            or meta['recordBytes'] != dense.DTYPE.itemsize or meta['tileSizeMetres'] <= 0):
        raise ValueError('Invalid every-record cache manifest counts or record layout')
    for name, count in meta['bins'].items():
        if not re.fullmatch(r'tile-(-?\d+)-(-?\d+)\.bin', name):
            raise ValueError('Invalid every-record spatial bin name')
        if count < 0 or (cache/name).stat().st_size != count * dense.DTYPE.itemsize:
            raise ValueError(f'Cache bin length differs from manifest: {name}')
    return meta


def region_bounds(bounds, cache_bounds):
    bounds = list(bounds)
    if len(bounds) == 4:
        bounds += list(cache_bounds[4:6])
    if (len(bounds) != 6 or not np.isfinite(bounds).all()
            or any(bounds[i] >= bounds[i+1] for i in (0, 2, 4))
            or any(bounds[i] < cache_bounds[i] or bounds[i+1] > cache_bounds[i+1] for i in (0, 2, 4))):
        raise ValueError('Exact review bounds must fit inside the original cache bounds')
    return bounds


def region_chunks(cache, meta, bounds):
    """Read-only bounded chunks, XY half-open and local Z upper-inclusive."""
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    size = meta['tileSizeMetres']
    for name in sorted(meta['bins']):
        x, y = map(int, re.fullmatch(r'tile-(-?\d+)-(-?\d+)\.bin', name).groups())
        if (x+1)*size <= xmin or x*size >= xmax or (y+1)*size <= ymin or y*size >= ymax:
            continue
        records = np.memmap(Path(cache)/name, dtype=dense.DTYPE, mode='r')
        for begin in range(0, len(records), CHUNK):
            chunk = records[begin:begin+CHUNK]
            p = chunk['xyz']
            keep = ((p[:, 0] >= xmin) & (p[:, 0] < xmax) & (p[:, 1] >= ymin)
                    & (p[:, 1] < ymax) & (p[:, 2] >= zmin) & (p[:, 2] <= zmax))
            yield chunk[keep]
        del records


def height_mask(points, band):
    low, high = Z_EDGES[band:band+2]
    return (points[:, 2] >= low) & ((points[:, 2] <= high) if band == 4 else (points[:, 2] < high))


def sample_region(cache, bounds, count=100000, seed=SEED):
    """Count exact raw records, then uniformly sample region record IDs."""
    if not 1 <= count <= 100000:
        raise ValueError('Sample count must be between 1 and 100000')
    meta = validate_cache(cache)
    bounds = region_bounds(bounds, meta['boundsLocal'])
    total = 0
    bands = [0] * 5
    for chunk in region_chunks(cache, meta, bounds):
        total += len(chunk)
        for band in range(5):
            bands[band] += int(height_mask(chunk['xyz'], band).sum())
    rng = np.random.default_rng(seed)
    chosen = np.sort(rng.choice(total, min(count, total), replace=False, shuffle=False))
    sample = np.empty(len(chosen), dtype=dense.DTYPE)
    offset = 0
    for chunk in region_chunks(cache, meta, bounds):
        begin, end = np.searchsorted(chosen, [offset, offset+len(chunk)])
        sample[begin:end] = chunk[chosen[begin:end]-offset]
        offset += len(chunk)
    if offset != total:
        raise ValueError('Source regional count changed while sampling')
    check_original(meta)
    return sample, total, bands


def metrics(distance):
    if not np.isfinite(distance).all():
        raise ValueError('Mesh distances must be finite')
    if not len(distance):
        return {key: None for key in ['within5cm', 'within10cm', 'within20cm', 'median', 'p95', 'max']}
    return {'within5cm': float(np.mean(distance <= .05)),
            'within10cm': float(np.mean(distance <= .10)),
            'within20cm': float(np.mean(distance <= .20)),
            'median': float(np.median(distance)), 'p95': float(np.quantile(distance, .95)),
            'max': float(distance.max())}


def mesh_distances(path, points):
    import open3d as o3d
    mesh = o3d.io.read_triangle_mesh(str(path), enable_post_processing=False)
    if not mesh.has_triangles():
        raise ValueError(f'Export requires a triangle mesh: {path}')
    triangles = len(mesh.triangles)
    vertices = np.asarray(mesh.vertices)
    if not np.isfinite(vertices).all():
        raise ValueError('Mesh vertices must be finite')
    mesh_bounds = [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()]
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    distance = scene.compute_distance(o3d.core.Tensor(points)).numpy()
    return distance, triangles, mesh_bounds


def audit(prefix, cache=ROOT/'analysis/dense-las', base=ROOT/'analysis/dense-reconstruction/campus-base-browser-v2.glb',
          count=100000, seed=SEED):
    started = time.monotonic()
    prefix = Path(prefix)
    if prefix.suffix in ('.glb', '.json'):
        prefix = prefix.with_suffix('')
    path, metadata_path = prefix.with_suffix('.glb'), prefix.with_suffix('.json')
    output = prefix.with_name(prefix.name+'-review.json')
    cache, base = Path(cache), Path(base)
    meta = validate_cache(cache)
    original_before = check_original(meta)
    manifest_before = file_identity(cache/'manifest.json')
    metadata_before = file_identity(metadata_path)
    metadata = json.loads(metadata_path.read_text())
    if metadata['origin'] != meta['origin']:
        raise ValueError('Export and raw source cache origins differ')
    bounds = region_bounds(metadata['boundsLocal'], meta['boundsLocal'])
    exported_before, base_before = file_identity(path), file_identity(base)
    sample, total, band_counts = sample_region(cache, bounds, count, seed)
    if not total:
        raise ValueError('Exact export bounds contain no original source records')
    points = sample['xyz'].copy()
    distances, triangles, mesh_bounds = mesh_distances(path, points)
    base_distances, base_triangles, base_bounds = mesh_distances(base, points)
    bands = []
    for band in range(5):
        chosen = height_mask(points, band)
        bands.append({'localZMetres': Z_EDGES[band:band+2],
                      'upperInclusive': band == 4, 'sourceRecords': band_counts[band],
                      'sampledRecords': int(chosen.sum()),
                      'exportDistanceMetres': metrics(distances[chosen]),
                      'baseDistanceMetres': metrics(base_distances[chosen])})
    exported_after, base_after = file_identity(path), file_identity(base)
    manifest_after, metadata_after = file_identity(cache/'manifest.json'), file_identity(metadata_path)
    original_after = check_original(meta)
    if (exported_before != exported_after or base_before != base_after
            or manifest_before != manifest_after or metadata_before != metadata_after
            or original_before != original_after):
        raise ValueError('Audit input changed during review; no report written')
    report = {'exportedGLB': {'before': exported_before, 'after': exported_after,
                              'triangles': triangles, 'vertexBoundsLocalXYZ': mesh_bounds},
              'baseGLB': {'before': base_before, 'after': base_after,
                          'triangles': base_triangles, 'vertexBoundsLocalXYZ': base_bounds},
              'metadataSHA256': metadata_before['sha256'],
              'sourceManifestSHA256': manifest_before['sha256'],
              'sourceCache': str(cache.resolve()), 'sourceCacheSampling': meta['sampling'],
              'sourceCacheRecords': meta['recordsRetained'], 'originalLASRecordsRead': meta['recordsRead'],
              'originalLASIdentity': {'before': original_before, 'after': original_after},
              'origin': meta['origin'], 'metadataBoundsLocal': metadata['boundsLocal'],
              'boundsLocalXYZ': bounds, 'boundsConvention': 'XY lower-inclusive upper-exclusive; Z both-inclusive',
              'sourceRecords': total, 'sampledRecords': len(sample),
              'sampling': {'method': 'Uniform raw regional record IDs without replacement; independently seeded',
                           'seed': seed, 'maximumRecords': count},
              'exportDistanceMetres': metrics(distances), 'baseDistanceMetres': metrics(base_distances),
              'localHeightBands': bands, 'elapsedSeconds': round(time.monotonic()-started, 2),
              'limits': 'Internal sampled original-source-to-exported-surface agreement only; not independent survey accuracy, semantic labels, texture quality, or proof of unseen surfaces. Dense source areas receive proportionate weight. Empty or unsampled height bands have null distance metrics.'}
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'review': str(output), 'sourceRecords': total, 'sampledRecords': len(sample),
                      'exportDistanceMetres': report['exportDistanceMetres'],
                      'baseDistanceMetres': report['baseDistanceMetres'],
                      'elapsedSeconds': report['elapsedSeconds']}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix', type=Path, nargs='+')
    parser.add_argument('--cache', type=Path, default=ROOT/'analysis/dense-las')
    parser.add_argument('--base', type=Path, default=ROOT/'analysis/dense-reconstruction/campus-base-browser-v2.glb')
    parser.add_argument('--count', type=int, default=100000)
    parser.add_argument('--seed', type=int, default=SEED)
    args = parser.parse_args()
    for prefix in args.prefix:
        audit(prefix, args.cache, args.base, args.count, args.seed)
