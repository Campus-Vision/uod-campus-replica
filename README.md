# University of Dubai — measured campus

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
The university is rendered as 6,659,157 original measured points. There is no
fitted, smoothed or invented building mesh. The original scan's courtyard,
facades, roof curvature, captured vehicles and other visible details are retained.
Occlusions and gaps remain visible; this is a dense point representation rather
than a watertight photogrammetric model.

The deterministic LAS sample retains every twentieth source record. A six-centimetre
voxel selection retains one actual point per occupied voxel without averaging XYZ
or RGB. Local float32 coordinates use the same UTM 40N origin as the compound.
This storage introduces a measured maximum coordinate difference of 0.0000153 m.
At distant viewpoints a distributed third of the points is drawn; the building
bookmark and nearby views draw all prepared points.

**Captured RGB** shows the captured colours without grading. **Natural daylight**
reduces the source green/cyan cast, gently lifts midtones, and applies
1.05× saturation and 1.10× brightness. Both sliders and point coverage are
reversible display settings; they never modify source positions or RGB buffers.
Neutral daylight, neutral tone mapping and matching terrain white balance improve the
compound's appearance. Thermal imagery keeps its recorded palette.

## Compound and solar inspection

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
