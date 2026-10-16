---
name: UoD 3D measured campus
description: Independent local campus inspection app with a scan-derived building
colors:
  ink: "#111"
  muted: "#555"
  line: "#d8d8d8"
  surface: "#fff"
  dark-ink: "#f5f5f5"
  dark-muted: "#b8b8b8"
  dark-line: "#383838"
  dark-surface: "#171717"
  dark-background: "#101010"
  dark-overlay: "#111"
  light-overlay-text: "#111"
  dark-overlay-text: "#fff"
typography:
  title:
    fontFamily: "Manrope Variable, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.45
    letterSpacing: "-.03em"
  body:
    fontFamily: "Manrope Variable, sans-serif"
    fontSize: "13px"
  section:
    fontFamily: "Manrope Variable, sans-serif"
    fontSize: "12px"
    fontWeight: 750
  label:
    fontFamily: "Manrope Variable, sans-serif"
    fontSize: "11px"
  annotation:
    fontFamily: "Manrope Variable, sans-serif"
    fontSize: "10px"
rounded:
  small: "4px"
  control: "5px"
  group: "6px"
  scene: "7px"
  notice: "10px"
spacing:
  control-gap: "8px"
  scene-gap: "10px"
  panel-inset: "22px"
  scene-inset: "24px"
components:
  button-appearance:
    backgroundColor: "color-mix(in srgb,var(--ink) 7%,var(--surface))"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  button-appearance-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
  button-capture:
    backgroundColor: "color-mix(in srgb,var(--ink) 7%,var(--surface))"
    textColor: "{colors.muted}"
    rounded: "{rounded.group}"
    height: "59px"
    padding: "7px 3px"
  button-capture-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
  button-outdoor:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.scene}"
    height: "38px"
    padding: "0 11px"
  location-bookmark:
    textColor: "{colors.ink}"
    rounded: "{rounded.group}"
    padding: "11px 9px"
  select:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    width: "148px"
    padding: "4px 6px"
  switch:
    backgroundColor: "#777"
    rounded: "{rounded.notice}"
    height: "17px"
    width: "29px"
---

# Design System: UoD 3D measured campus

## Overview

**Creative North Star: "Campus visitor-directory precision"**

The measured campus leads. Compact Manrope, a monochrome header, quiet controls and fine dividers carry forward the survey viewer's layout and type system. Sunlit terrain and source imagery provide the scene's character; outdoor overlays stay quiet and readable. This independent React app runs on port 5174; the progressive COPC survey remains independently available on port 5173.

The owner explicitly requested a white-and-black interface with persistent light/dark switching. This approved colour-system change is scoped to this app; the original blue survey viewer retains its own system.

This document records the shipped implementation in `src/App.jsx`, `src/replica.css`, `src/style.css` and `src/scene.js`. It preserves the inherited typography, structure and component shapes while documenting the approved monochrome palette. The compound was approved; the fitted building was rejected. This record does not imply user approval of a final visual comp or calibrated geometric accuracy.

**Key Characteristics:**

- Measured building geometry remains the visual reference.
- Pale continuous controls frame an available-height spatial scene.
- Inverted pressed states and explicit labels make inspection modes legible.
- Source distinctions remain visible alongside the reconstructed context.

## Colors

The interface uses black, white and neutral grays in both themes. Frontmatter records real theme values; `ink`, `muted`, `line` and `surface` are the light defaults, and their `dark-` counterparts describe the dark overrides. Captured RGB, terrain and thermal imagery retain their natural source colours.

### Primary

- **Ink** (`ink`, `dark-ink`): primary text, checked controls, focus outlines and progress.
- **Inverted selection**: appearance and capture selections use the current ink as fill and the current surface as text.

### Neutral

- **Supporting gray** (`muted`, `dark-muted`): secondary labels and explanatory copy.
- **Divider gray** (`line`, `dark-line`): fieldsets, control strokes and shell separation.
- **Control surface** (`surface`, `dark-surface`): header, sidebar, status bar and native fields.
- **Dark backing** (`dark-background`): root dark canvas behind app surfaces.
- **Scene overlays**: white with near-black text in light mode; near-black with white text in dark mode. Thermal badges use a blacker dark surface while the thermal image remains unchanged.

**The Theme Boundary Rule.** Theme changes affect interface chrome only. Keep the measured building, terrain imagery and recorded thermal palette unchanged.

**The Measured Content Rule.** Keep the scan-derived building and Original points comparison available. Display colour corrections must remain reversible and must not edit source RGB.

Natural daylight is the default display treatment: green-cast reduction, midtone lift, saturation 1.05 and brightness 1.10. Captured RGB restores the captured colour display at unit saturation and brightness. These are appearance settings, not calibration or new source measurements.

## Typography

**UI font:** locally bundled Manrope Variable with a sans-serif fallback. The inherited title/body/section/label/annotation roles remain normative in frontmatter. There is no hero display face.

Titles anchor the sidebar; small, strong section labels distinguish control groups. Body copy and annotations use comfortable line heights (1.7 for recurring explanatory copy). Numeric outputs and status metadata use tabular numerals. Location titles use the label role with a stronger weight; small source descriptions remain secondary. W/T/Z are text labels for capture modes, not decorative glyph icons. Interface icons render as stroke SVGs.

The brand uses larger compact type (21px desktop, 18px mobile). The sidebar title follows inherited responsive sizing: 17px at up to 1000px, 18px in the mobile drawer and 19px from 1600px. Small tertiary labels and attribution are descriptive incumbent values, not a target size for new essential information.

## Layout

The application fills the viewport without page scrolling. A 64px header and 34px status bar leave an available-height workspace (`calc(100dvh - 98px)`). The continuous sidebar scrolls independently and is 292px wide, 270px at up to 1100px and 310px from 1600px. Thin fieldset separators organise controls; avoid converting this column into decorative cards.

The scene occupies the remaining width. Camera presets sit upper left, reset/fullscreen upper right, location and navigation hints near the bottom, attribution along the bottom edge. Location bookmarks align icon, title and source detail. Four equal capture buttons form one inspection group; representation and colour choices each use two equal buttons.

At up to 700px the header becomes 58px and the workspace becomes `calc(100dvh - 92px)`. Controls move into a fixed, scrollable drawer below the header and above the status bar, with width `min(310px, 88vw)` and a dim backdrop. The labelled opener remains reachable. Fullscreen and navigation hints disappear while source attribution and named controls remain available. The full-compound starting view covers the university, parking and both solar clusters.

## Elevation & Depth

Permanent UI uses pale surfaces and fine borders. Outdoor controls have a faint ambient shadow (`0 3px 12px #273c3c14`); the location plate uses `0 3px 16px #273c3c15`; capture badges use `0 3px 15px #273c3c1a`. Help and loading/error states use stronger transient elevation. There is no backdrop blur. Scene lighting and material shading provide physical depth independently of UI elevation.

**The Quiet Depth Rule.** Use tone and separators for permanent structure; reserve stronger cast shadows for temporary help and feedback.

## Shapes

The shell is unrounded. Controls use compact rounded rectangles: small segments, modest field and bookmark corners, and slightly softer scene overlays. Switch tracks are pills with circular thumbs; status indicators are circles. Borders are generally 1px. Keyboard focus uses a visible 3px outline, inset on the scene region. Preserve these inherited shapes rather than adding a new card vocabulary.

## Components

### Location bookmarks

Quiet full-width rows with a 60px minimum height. Hover adds a pale surface; selection uses pale blue with stronger blue text and `aria-pressed`. Keep the source/helper line aligned with its title. Selecting a place changes the inspection framing.

### Capture and appearance groups

Capture buttons form a four-column grid with a 5px gap and clearly visible selected state. Appearance groups use a 6px gap, a 32px minimum button height and explicit `aria-pressed`. Merged surface and Original points share the same camera. Captured RGB and Natural daylight change appearance without changing geometry. Point coverage is disabled for the merged surface.

**The Registered Capture Rule.** W/T/Z must keep the same eastern-array geometry, camera and target. Normal uses modelled photovoltaic materials; W/T/Z uses supplied recorded imagery. The southern array has no supplied camera captures.

### Persistent theme toggle

The header offers an explicitly labelled Dark or Light action with inline SVG. Light is the initial fallback. The choice persists under `uod-campus-replica-theme` in localStorage; if storage is unavailable the toggle still works for the current visit. The root `data-theme` and native `color-scheme` change together. Hover uses a subtle current-ink tint; focus remains a visible 3px current-ink outline. The same control is available on mobile.

### Fields and switches

Native lighting select, labelled ranges with adjacent numeric outputs, and labelled switches keep the compact inherited form language. Ranges use current-theme ink; selects have pale fill, a thin border and a 32px minimum height. Switch tracks are 29px by 17px with an 11px white thumb. Preserve visible keyboard focus, associated labels and disabled-state meaning.

### Scene tools and reference furniture

Theme-aware rounded camera and utility groups stay legible over terrain. Selected camera presets invert the current overlay colours. Textless actions retain accessible names. North, location, capture date and imagery attribution remain reference furniture. Thermal mode adds a monochrome identifying badge and explicitly states that recorded thermal colours do not provide calibrated temperatures.

### Loading, errors, help and source disclosure

Loading reports asset preparation, with progress animated through `transform: scaleX(...)`; errors expose retry and the survey link. Status/alert semantics remain intact. Help explains orbit, pan, zoom and shortcuts. About this replica discloses the estimated building surface, retained scan gaps, modelled context, image-traced perimeter and uncalibrated thermal imagery.

Buttons and switches transition over .15s; the drawer uses .22s ease-out; progress uses .3s ease-out. The spinner turns linearly over 1.1s. Reduced-motion preferences remove transitions and set animation duration to 2s, following the inherited stylesheet.

The default merged building is a trimmed, oriented-normal Poisson estimate derived from the scan: 0.16m preparation, depth 10, and maximum nearest-point distance 0.32m; 602,236 vertices and 1,030,357 triangles. It smooths fine detail and retains residual gaps. Original points restores 6,659,157 measured XYZ/RGB records. Neither representation certifies accuracy of occluded surfaces. Parking canopies, landscape and the southern array contain modelled context; the perimeter is image-traced, not cadastral. Original LAS, COPC, KML, PosL and processed photogrammetry remain unchanged; binary data stays outside Git.

The measured-building review before the subsequent roof investigation reported SHIP with no material fixes. Its ten valid captures are in `../.impeccable/review/measured-react/`: desktop, building, building-captured, building-points, wide, thermal, zoom, south, mobile and mobile-controls. Reported validation: replica browser checks pass with zero errors; four unit tests pass including the 256-record LAS audit and mesh validity; production build passes; original viewer nine unit tests and browser checks pass; detector run once and clear; four shipping raster provenance entries with zero missing. The monochrome change has additional desktop-light, desktop-dark, mobile-light and mobile-dark captures in `../.impeccable/review/monochrome/`; reported checks cover persistence, storage fallback, mobile operation and production build. The refreshed full-scene browser suite passes with zero errors. This is a factual review audit, not a new accuracy or aesthetic approval claim. A subsequent owner report of missing roof coverage is under investigation; this audit does not resolve that issue.

## Do's and Don'ts

### Do:

- Do preserve the inherited Manrope, monochrome theme roles, component shapes and visible keyboard focus.
- Do keep Original points and Captured RGB available for comparison with display treatments.
- Do preserve full-compound coverage, parking and both solar clusters.
- Do preserve camera, target and geometry when switching registered eastern-array captures.
- Do disclose scan-derived approximation, source gaps, modelled context and thermal limits.
- Do retain labelled mobile controls and scrollable drawer access.

### Don't:

- Don't replace the measured university with guessed architectural shapes.
- Don't treat interpolated surface detail, image-traced extent or thermal colours as calibrated measurement.
- Don't use source data colours as a general UI action palette.
- Don't multiply permanent cards or strong shadows where the system uses separators.
