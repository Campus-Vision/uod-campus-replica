# University of Dubai — measured campus

Audience: the owner and visitors exploring the university compound and inspecting
solar imagery in a local browser. This is an independent React and Three.js app.

The owner praised the full compound but rejected the fitted architectural model
because its building did not match the LiDAR. The building must now be rendered
from original scan coordinates and captured RGB. Colour improvements are display
adjustments, not source edits. The owner's follow-up requests brighter natural daylight and removal of the mouldy green/sea-like cast. Avoid amplified saturation as the default. Keep the real courtyard, roofs and facades as
captured. Source occlusions must remain distinguishable from estimated repairs.
The owner later explicitly authorized repairing the highlighted missing western
roof using the map. This permits an aerial-constrained roof infill supported by
measured rim elevations, with its unobserved interior clearly identified as an
estimate; it does not authorize a guessed replacement building.

The owner subsequently requested merging points for a more solid realistic view.
Provide a scan-derived continuous surface as an option, with unsupported regions
trimmed and Original points preserved for comparison. Clearly distinguish the
estimated surface from the unchanged measured points. Make local Git commits
for each completed logical change.

Retain the full perimeter, parking lots, covered parking, roads, entrances,
landscape and both solar clusters. The processed Wide/Thermal/Zoom captures belong
to the larger eastern array. Switch imagery on one shared, registered surface
without moving its geometry or camera. The southern array is reconstructed from
aerial imagery and has no supplied inspection captures.

Preserve the existing Impeccable interface style: Manrope, ink-blue navigation,
pale controls, labelled accessible buttons, orbit/pan/zoom, named bookmarks,
mobile drawer, loading/retry states and explicit source limitations. The owner
approved building directly in code. The measured scene leads; UI supports it.

The original progressive COPC survey remains a separate app at port 5173. This
project runs independently at port 5174 and contains all prepared runtime assets.

## Interface theme

The owner subsequently requested a white-and-black interface with a persistent
light/dark theme toggle, implemented by one small agent. Keep the campus model,
imagery and thermal palette in natural recorded colours; the monochrome treatment
applies to interface controls, panels and navigation. Preserve the existing
layout, Manrope typography, accessibility and all inspection behavior.

## Current reconstruction refinement

The western roof now uses the aerial outline/texture and measured upper-rim
heights, with estimated transverse shape. Original points hides that infill.
Three parking contexts use finer independent measured surfaces, and six parking
and tree-row contexts use small oriented patches at unchanged source positions
and RGB. Coarse non-ground faces are replaced only in those bounded contexts.
These improvements preserve captured form and reduce coarse facets; remaining
scan holes, occluded car sides and sparse foliage are not claimed as recovered.
