"""Select original measured points; never fit, smooth, recolour or move geometry.

Input cache is the deterministic every-20th-record sample of the owner's LAS.
Spatial thinning retains an actual source point in each occupied 6 cm voxel.
Coordinates are stored relative to site.origin for browser floating-point precision.
Run using the bundled Python from the campus-replica project directory.
"""
import json
from pathlib import Path
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
OUT = PROJECT / 'public/replica'
source = np.load(ROOT / 'analysis/lidar-sample.npz')
xyz, rgb = source['xyz'], source['rgb']
site = json.loads((OUT / 'site.json').read_text())
origin = np.array(site['origin'])
bounds = [339905., 340335., 2777500., 2777830., 43., 90.]
keep = ((xyz[:, 0] >= bounds[0]) & (xyz[:, 0] <= bounds[1]) &
        (xyz[:, 1] >= bounds[2]) & (xyz[:, 1] <= bounds[3]) &
        (xyz[:, 2] >= bounds[4]) & (xyz[:, 2] <= bounds[5]))
source_indices = np.flatnonzero(keep)
points = xyz[source_indices]
voxel = np.floor((points - np.array([bounds[0], bounds[2], bounds[4]])) / .06).astype(np.int64)
keys = voxel[:, 0] + voxel[:, 1] * 8192 + voxel[:, 2] * 8192 * 8192
_, unique = np.unique(keys, return_index=True)
# Deterministically interleave records for a spatially distributed overview LOD.
chosen = source_indices[unique]
rng = np.random.default_rng(20261008)
rng.shuffle(chosen)
positions = (xyz[chosen] - origin).astype('<f4')
colours = rgb[chosen].astype('uint8')
(OUT / 'building.positions.bin').write_bytes(positions.tobytes())
(OUT / 'building.colors.bin').write_bytes(colours.tobytes())
meta = {
    'source': '20261008121946091.las',
    'sourcePointCount': 200700295,
    'inputSampling': 'Every 20th LAS record, preserving its original XYZ and RGB',
    'selection': 'One original source point per occupied 0.06 metre voxel; no averaging or surface fitting',
    'count': len(chosen), 'voxelMetres': .06,
    'origin': origin.tolist(), 'cropBounds': bounds,
    'boundsLocal': {'min': positions.min(axis=0).tolist(), 'max': positions.max(axis=0).tolist()},
    'positions': 'building.positions.bin', 'colors': 'building.colors.bin',
    'positionFormat': 'float32 little endian XYZ', 'colorFormat': 'uint8 RGB sRGB',
    'geometry': 'Measured points only. No inferred roof, wall, window or courtyard geometry.',
    'colour': 'Original captured RGB; reversible display grading is applied in the browser.',
    'limits': 'The scan contains occlusions and gaps. Unobserved surfaces are not reconstructed.'
}
(OUT / 'building.json').write_text(json.dumps(meta, indent=2))
audit_indices = np.linspace(0, len(chosen) - 1, 256, dtype=int)
(PROJECT / 'tests/building-audit.json').write_text(json.dumps([
    {'outputIndex': int(i), 'lasRecordIndex': int(chosen[i]) * 20}
    for i in audit_indices
], indent=2))
site['notes']['building'] = meta['geometry'] + ' ' + meta['limits']
site['buildingCapture'] = 'building.json'
(OUT / 'site.json').write_text(json.dumps(site, indent=2))
provenance = json.loads((OUT / 'provenance.json').read_text())
for name in ['campus-surfaces.glb', 'campus-facades.glb', 'lidar-surfaces-reference.glb']:
    provenance.pop(name, None)
provenance['building.positions.bin'] = meta
(OUT / 'provenance.json').write_text(json.dumps(provenance, indent=2))
# Verify emitted local coordinates recover the selected measured points to <0.1 mm.
max_error = float(np.abs(positions.astype(np.float64) + origin - xyz[chosen]).max())
assert max_error < .0001
assert np.array_equal(colours, rgb[chosen])
print(json.dumps({'points': len(chosen), 'maxCoordinateErrorMetres': max_error,
                  'positionBytes': positions.nbytes, 'colourBytes': colours.nbytes}, indent=2))
