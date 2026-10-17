# University of Dubai â€” measured campus

This is a standalone React + Three.js + Vite project. It has its own package.json,
lockfile, source, generated assets, tests and build output. It does not import the
point-cloud viewer. Copy this folder to run the prepared campus independently.

## Run

From this folder, run `npm install` followed by `npm run dev`, then open
http://127.0.0.1:5174/. Node.js 22.12 or later is required by Vite.
The parent folder's **Start campus replica.cmd** starts this project.

`npm run build` creates `dist/`. `npm run preview` serves the production build.
The optional LiDAR survey link opens the original viewer on port 5173; that
separate viewer must be started separately. No survey server is needed for this app.

## Building fidelity

The previous aerial-traced roof and facade models are **not loaded** here.
The **Original points** view renders 6,659,157 original measured points. The
default **Merged surface** view reconstructs a continuous triangular surface
from the same scan with oriented-normal Poisson reconstruction, then trims
unsupported vertices and faces. It preserves the recorded building's form
without a hand-drawn architectural replacement. Fine detail may be smoothed;
occlusions and gaps may remain. Switch to Original points to compare with the
measured courtyard, facades, roofs, captured vehicles and other details.

The deterministic LAS sample retains every twentieth source record. A six-centimetre
voxel selection retains one actual point per occupied voxel without averaging XYZ
or RGB. Local float32 coordinates use the same UTM 40N origin as the compound.
This storage introduces a measured maximum coordinate difference of 0.0000153 m.
At distant viewpoints a distributed third of the points is drawn; the building
bookmark and nearby views draw all prepared points.

`scripts/reconstruct-surface.py` uses Open3D and SciPy to generate the surface.
Preparation uses a 0.16 m sample and depth-10 reconstruction. Unsupported
vertices farther than 0.32 m from a source point and faces spanning large gaps
are removed before bounded simplification. Captured source RGB is transferred
to surface vertices. The reconstruction statistics in `building-surface.json`
describe proximity to the scan, not a certified architectural accuracy.

**Captured RGB** shows the captured colours without grading. **Natural daylight**
reduces the source green/cyan cast, gently lifts midtones, and applies
1.05Ã— saturation and 1.10Ã— brightness. Both sliders and point coverage are
reversible display settings; they never modify source positions or RGB buffers.
Neutral daylight, neutral tone mapping and matching terrain white balance improve the
compound's appearance. Thermal imagery keeps its recorded palette.

## Compound and solar inspection

### Roof and local scan-detail refinement

The western reflective roof now has an aerial-informed repair: 5,718 vertices,
11,113 triangles, and the real aerial texture. Its footprint follows the map and
keeps the courtyard open. Longitudinal height follows measured high-rim returns;
the unobserved interior is interpolated, with transverse extrapolation up to
29.53 m. This is an estimated repair, explicitly disclosed in the UI. Its height
does not inherit the base mesh's 0.32 m source-support statistic. Original points
hides the repair. Preparation and provenance: `scripts/prepare-roof.py`,
`public/replica/roof-provenance.json` and `roof-repair.json`.

Three parking contexts now use independent finer local surfaces (235,773 total
triangles), with source RGB and vertices within 14 cm of selected measured points.
Triangle centres/midpoints must remain within 16 cm of that source and edges
within 45 cm. Preparation excludes points less than 0.35 m above an approximate
local floor to reduce road debris. These are contextual scan regions, not
individually classified, complete or watertight vehicle models. See
`scripts/prepare-parking-surfaces.py` and `parking-surfaces.json` for per-region
coverage/error distributions, including unmatched source points.

Six parking/tree contexts additionally use 101,075 small oriented surface patches
at unchanged measured centres and RGB, with radii 3.5â€“12 cm. Sparse/collinear
neighbourhoods are rejected. The runtime replaces coarse non-ground faces only
inside those checked contexts and below their measured height bounds, preserving
the original on-disk GLB. Background modelled crowns are omitted in captured
tree-row contexts. Other background landscape remains illustrative. Source
occlusions, incomplete vehicle sides and sparse foliage remain visible.

`Original points` hides all added surface layers. Landscape visibility hides
the local tree-row patches while retaining parking surfaces. Preparation:
`scripts/prepare-details.py`; source audits: `tests/test-details.py` and
`tests/test-parking-surfaces.py`. Python tests use the isolated packages described
above. `node tests/reconstruction-browser.mjs` captures fixed-camera comparisons
against the original coarse GLB, plus dark-theme roof/detail views.

The full compound, roads, entrances, six parking canopies and both solar arrays
are retained. Terrain uses georeferenced aerial imagery with a LiDAR ground fit.
The perimeter is image-traced, not a certified cadastral boundary. Landscape,
parking details and southern solar modules include reconstructed geometry.

The east array uses one corrected wide-camera photogrammetric surface. Wide,
Thermal and Zoom apply the supplied registered images to that same geometry.
Once viewing east, switching modes preserves the camera and orbit centre.
Thermal colours are not calibrated temperature readings. No corresponding W/T/Z
captures were supplied for the southern array.

Image origin and processing are recorded in `public/replica/provenance.json`.
The basemap is Esri World Imagery, attributed in the interface. Original LAS,
COPC, KML and processed photogrammetry sources remain unchanged.

## Preparation and validation

The prepared app is self-contained. To regenerate the building assets from the
owner's workspace, run `scripts/prepare-building.py` with Python, NumPy and the
parent `analysis/lidar-sample.npz` cache present. The inherited compound and solar
asset preparation remains in the original `viewer/scripts/build-replica.py`.
Do not regenerate smooth architectural models into this app.

`npm test` validates 256 prepared points and RGB triples directly against their
original LAS records, project independence, perimeter coverage and registration.
This source audit requires the original LAS in the parent folder. `npm run
test:browser` exercises the running React application using Chrome, including
building fidelity, colour controls, W/T/Z geometry/camera stability, bookmarks,
landscape/perimeter settings, keyboard help and mobile layout. Review screenshots
are written to the parent's `.impeccable/review/measured-react/` folder.

React owns the interface and appearance state. The Three.js scene is mounted
through a React effect, with cancellation and disposal on unmount. Both building
geometry and captured RGB remain immutable throughout appearance changes.


## Active dense reconstruction work

The full-resolution reconstruction is a separate offline pipeline. It has read
all 200,700,295 LAS records and preserved 200,424,893 within the documented campus
bounds, without temporal sampling. The browser's current default remains the
previous reconstruction while dense sections, textures and assembly are reviewed.
Both solar clusters and registered eastern W/T/Z views remain required.

Dependencies used are recorded in `scripts/requirements-dense.txt`; they are
installed in the parent `analysis/python-packages/` directory. The calibration
test also uses the existing OpenCV installation. Run scripts from the workspace
root with the bundled Python described above:

```powershell
python campus-replica/scripts/dense-las.py
python campus-replica/scripts/reconstruct-dense.py --bounds -40 0 -240 -200 --output analysis/dense-reconstruction/south-pilot
python campus-replica/scripts/audit-dense.py analysis/dense-reconstruction/south-pilot
python campus-replica/scripts/bake-dense.py analysis/dense-reconstruction/south-pilot
python campus-replica/scripts/audit-dense.py analysis/dense-reconstruction/south-pilot-textured
python campus-replica/scripts/align-campus-photos.py
```

Extraction requires a new empty output directory; do not repeat it over the
existing cache. Region loading reads every selected original measurement, then
normal preparation retains an actual source point per 4cm voxel. This is not the
old every-twentieth-record browser sample. High-resolution trials export connected
triangle GLBs and editable OBJ copies in `analysis/dense-reconstruction/`.

The textured parking trial reduces 3,463,958 triangles / 89.5MB to 247,882
triangles / 14.5MB using an embedded 2048px source-colour texture. Adaptive checks
sample simplified faces on a grid with maximum 4cm spacing, retaining samples
within 2.5cm of the dense parent. The resulting conservative continuous distance
bound is 6.5cm to that parent, plus floating-point tolerance, not a direct accuracy
bound to the LAS. Unseen surfaces remain unsupported. This texture is baked from
captured LAS colours, not yet projected original photographs.

A native COLMAP pass reads 250 additional original Wide photographs without
modifying them. It exports sparse structure and solved cameras in an unregistered
frame; those require independent alignment to the LAS before texture projection.
Photographic coverage and processing limits are recorded in
`../tasks/photo-source-audit.md`; active progress and remaining full-campus gates
are in `../tasks/dense-reconstruction.md`.

Focused checks: `tests/test-dense-las.py`, `test-dense-mesh.py`,
`test-dense-bake.py`, `test-photo-calibration.py`. Actual geometry/texture source
audits require the local original/cache assets. From this app directory,
`node tests/dense-preview.mjs south-pilot --textured` records a fixed-camera
comparison against the prior surface and original points. Use `building-pilot`
or `vegetation-pilot` for other generated trials. Captures live in the parent's
`.impeccable/review/dense/` directory. These previews isolate one section and do
not certify full-campus completion. Source/support metadata is tracked in
`public/replica/dense-source.json`, `dense-trials.json` and
`dense-textured-trial.json`; generated binaries remain outside Git.
