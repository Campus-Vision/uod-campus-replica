# University of Dubai — measured campus

Audience: the owner and visitors exploring the university compound and inspecting
solar imagery in a local browser. This is an independent React and Three.js app.

The owner praised the full compound but rejected the fitted architectural model
because its building did not match the LiDAR. The building must now be rendered
from original scan coordinates and captured RGB. Colour improvements are display
adjustments, not source edits. The owner's follow-up requests brighter natural daylight and removal of the mouldy green/sea-like cast. Avoid amplified saturation as the default. Keep the real courtyard, roofs and facades as
captured, including source occlusions; do not invent missing building surfaces.

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
