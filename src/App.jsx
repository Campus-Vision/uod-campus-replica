import { useEffect, useRef, useState } from 'react';
import { mountCampus } from './scene.js';
import './replica.css';

const THEME_KEY = 'uod-campus-replica-theme';

function readTheme() {
  try {
    return window.localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function BuildingAppearance({ appearance, onChange }) {
  const update = (key, value) => onChange(current => ({ ...current, [key]: value }));
  return <fieldset className="building-appearance"><legend>Building appearance</legend>
    <p className="appearance-note">Scan-derived surfaces. Original points for comparison.</p>
    {appearance.representation === 'surface' && <p className="appearance-note" id="roof-repair-note">Western roof repaired from aerial imagery; interior height is estimated from the measured rim.</p>}
    {appearance.representation === 'surface' && <p className="appearance-note">Fine parking and tree-row surfaces use small patches at measured scan positions. Occluded details may remain incomplete.</p>}
    <div className="colour-presets" role="group" aria-label="Building representation">
      <button aria-pressed={appearance.representation === 'surface'} onClick={() => update('representation', 'surface')}>Merged surface</button>
      <button aria-pressed={appearance.representation === 'points'} onClick={() => update('representation', 'points')}>Original points</button>
    </div>
    <div className="colour-presets" role="group" aria-label="Building colour">
      <button aria-pressed={!appearance.natural && appearance.saturation === 1 && appearance.brightness === 1} onClick={() => onChange(current => ({...current, natural: false, saturation: 1, brightness: 1}))}>Captured RGB</button>
      <button aria-pressed={appearance.natural && appearance.saturation === 1.05 && appearance.brightness === 1.1} onClick={() => onChange(current => ({...current, natural: true, saturation: 1.05, brightness: 1.1}))}>Natural daylight</button>
    </div>
    <label className="appearance-slider" htmlFor="building-saturation"><span>Saturation <output>{appearance.saturation.toFixed(2)}×</output></span><input id="building-saturation" type="range" min="0" max="1.8" step="0.01" value={appearance.saturation} onChange={event => update('saturation', Number(event.target.value))}/></label>
    <label className="appearance-slider" htmlFor="building-brightness"><span>Brightness <output>{appearance.brightness.toFixed(2)}×</output></span><input id="building-brightness" type="range" min="0.7" max="1.4" step="0.01" value={appearance.brightness} onChange={event => update('brightness', Number(event.target.value))}/></label>
    <label className="appearance-slider" htmlFor="building-point-size"><span>Point coverage <output>{appearance.pointSize.toFixed(2)} m</output></span><input id="building-point-size" type="range" min="0.05" max="0.22" step="0.01" disabled={appearance.representation !== 'points'} value={appearance.pointSize} onChange={event => update('pointSize', Number(event.target.value))}/></label>
  </fieldset>;
}

export default function App() {
  const engine = useRef(null);
  const [theme, setTheme] = useState(readTheme);
  const [appearance, setAppearance] = useState({ representation: 'surface', natural: true, saturation: 1.05, brightness: 1.1, pointSize: .12 });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { window.localStorage.setItem(THEME_KEY, theme); } catch { /* Theme still works for this visit. */ }
  }, [theme]);
  useEffect(() => {
    engine.current = mountCampus();
    return () => { engine.current?.dispose(); engine.current = null; };
  }, []);
  useEffect(() => { engine.current?.setAppearance(appearance); }, [appearance]);
  return <>
  <header className="app-header">
    <a className="brand" href="/" aria-label="UoD 3D campus replica"><span className="brand-mark" aria-hidden="true"><i data-lucide="scan"></i></span><span>UoD <strong>3D</strong></span></a>
    <div className="header-divider"></div>
    <nav className="product-nav" aria-label="Workspace"><a href="/" aria-current="page">Campus replica</a><a href="http://127.0.0.1:5173/">LiDAR survey<i data-lucide="arrow-up-right"></i></a></nav>
    <div className="header-actions"><span className="local-indicator"><span></span>Local workspace</span><button className="theme-toggle" type="button" onClick={() => setTheme(current => current === 'light' ? 'dark' : 'light')} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}><svg viewBox="0 0 20 20" aria-hidden="true"><path d={theme === 'light' ? 'M17.2 12.1A7.5 7.5 0 0 1 7.9 2.8a7.6 7.6 0 1 0 9.3 9.3Z' : 'M10 2v2m0 12v2M2 10h2m12 0h2M4.35 4.35l1.42 1.42m8.46 8.46 1.42 1.42m0-11.3-1.42 1.42m-8.46 8.46-1.42 1.42M14.5 10a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0Z'} /></svg><span>{theme === 'light' ? 'Dark' : 'Light'}</span></button><button className="icon-button header-button" id="replica-help" aria-label="Navigation help" aria-expanded="false"><i data-lucide="circle-help"></i></button></div>
  </header>
  <main className="workspace">
    <aside className="sidebar replica-sidebar" id="replica-sidebar" aria-label="Campus controls">
      <div className="sidebar-heading"><h1>University of Dubai</h1><button className="icon-button close-panel" id="replica-close" aria-label="Close campus controls"><i data-lucide="x"></i></button></div>
      <p className="location"><i data-lucide="map-pin"></i>Academic City, Dubai</p>
      <p className="replica-intro">The compound. The building as captured.</p>
      <fieldset className="place-controls" id="place-controls" disabled><legend>Explore campus</legend>
        <div className="place-list" role="group" aria-label="Campus locations">
          <button data-place="compound" aria-pressed="true"><span className="place-icon"><i data-lucide="land-plot"></i></span><span><strong>Entire compound</strong><small>Full perimeter & surroundings</small></span><i data-lucide="chevron-right"></i></button>
          <button data-place="building" aria-pressed="false"><span className="place-icon"><i data-lucide="building-2"></i></span><span><strong>University building</strong><small>Original LiDAR · captured geometry</small></span><i data-lucide="chevron-right"></i></button>
          <button data-place="east" aria-pressed="false"><span className="place-icon"><i data-lucide="panels-top-left"></i></span><span><strong>East solar array</strong><small>Wide · Thermal · Zoom</small></span><span className="capture-dot" title="Camera captures available"></span></button>
          <button data-place="south" aria-pressed="false"><span className="place-icon"><i data-lucide="panels-top-left"></i></span><span><strong>South solar array</strong><small>Reconstructed from aerial imagery</small></span><i data-lucide="chevron-right"></i></button>
        </div>
      </fieldset>
      <fieldset className="capture-controls" id="capture-controls" disabled><legend>East array inspection</legend>
        <div className="capture-modes" role="group" aria-label="East array capture mode">
          <button data-capture="normal" aria-pressed="true"><i data-lucide="box"></i><span>Normal</span></button><button data-capture="wide" aria-pressed="false"><strong>W</strong><span>Wide</span></button><button data-capture="thermal" aria-pressed="false"><strong>T</strong><span>Thermal</span></button><button data-capture="zoom" aria-pressed="false"><strong>Z</strong><span>Zoom</span></button>
        </div>
        <p className="capture-description" id="capture-description">The textured, three-dimensional campus.</p>
        <div className="alignment-note"><i data-lucide="crosshair"></i><span>Shared surface. Registered captures.</span></div>
        <p className="thermal-note" id="thermal-note" hidden>Recorded thermal colours. These images do not provide calibrated temperatures.</p>
      </fieldset>
      <BuildingAppearance appearance={appearance} onChange={setAppearance} />
      <fieldset id="replica-display" disabled><legend>Scene</legend>
        <label className="toggle-row" htmlFor="landscape-toggle"><span>Landscape<span className="toggle-note">Image-positioned trees & vegetation</span></span><input type="checkbox" role="switch" id="landscape-toggle" defaultChecked/></label>
        <label className="toggle-row" htmlFor="perimeter-toggle"><span>Show perimeter<span className="toggle-note">Extent traced from aerial imagery</span></span><input type="checkbox" role="switch" id="perimeter-toggle"/></label>
        <div className="select-row"><label htmlFor="lighting-select">Lighting</label><select id="lighting-select"><option value="daylight">Daylight</option><option value="afternoon">Late afternoon</option><option value="soft">Soft light</option></select></div>
      </fieldset>
      <details className="survey-details replica-source"><summary>About this replica<i data-lucide="chevron-down"></i></summary><p>The university's merged surface is reconstructed from the original LiDAR geometry and captured RGB. The western roof gap is repaired using an aerial-traced outline and texture with height estimated from measured roof-rim returns. The roof interior was not measured and its transverse shape remains approximate. Original points hides the repair and restores the scan.</p><p>Surface reconstruction smooths some fine detail; scan gaps may remain. Parking canopies, background landscape and the southern array include modelled details. The perimeter is image-traced, not cadastral.</p><p>The eastern array uses supplied photogrammetry. Normal shows modelled photovoltaic materials. W/T/Z shows recorded imagery on the same surface. Captures were made on 8 October 2026; thermal colours are not calibrated temperatures.</p><a href="http://127.0.0.1:5173/" className="reference-link">Open the measured survey<i data-lucide="arrow-up-right"></i></a></details>
      <div className="sidebar-footer"><i data-lucide="hard-drive"></i><span>Source data stays on your computer</span></div>
    </aside>
    <section className="replica-scene" id="replica-scene" aria-label="Three-dimensional campus replica">
      <div id="replica-view" tabIndex="0" role="region" aria-label="3D campus. Drag to orbit, right-drag to pan, scroll to zoom. R resets to the entire compound. T shows the top view."></div>
      <div className="replica-toolbar"><div className="view-actions"><button className="replica-tool mobile-controls" id="replica-open" aria-label="Open campus controls" aria-controls="replica-sidebar" aria-expanded="false"><i data-lucide="sliders-horizontal"></i></button><div className="replica-view-presets" role="group" aria-label="Camera angle"><button data-angle="perspective" aria-pressed="true"><i data-lucide="box"></i><span>Perspective</span></button><button data-angle="top" aria-pressed="false"><i data-lucide="layers-2"></i><span>Top</span></button></div></div><div className="scene-tools"><button className="replica-tool icon-only" id="replica-reset" aria-label="Reset entire compound view" title="Reset view (R)"><i data-lucide="rotate-ccw"></i></button><button className="replica-tool icon-only" id="replica-fullscreen" aria-label="Enter full screen" title="Full screen"><i data-lucide="expand"></i></button></div></div>
      <div className="replica-north" title="North direction"><span>N</span><svg id="replica-north-arrow" viewBox="0 0 36 36" aria-hidden="true"><path d="M18 3 27 30 18 24 9 30Z" fill="currentColor"/><path d="M18 3v21l9 6Z" fill="#777"/></svg></div>
      <div id="site-labels" className="site-labels" aria-hidden="true"></div>
      <div className="replica-loading" id="replica-loading" role="status" aria-live="polite"><span className="replica-spinner"></span><strong>Bringing the campus into view</strong><p id="replica-loading-detail">Preparing terrain and source imagery…</p><div className="load-progress"><span id="load-progress-fill"></span></div></div>
      <div className="replica-error" id="replica-error" role="alert" hidden><i data-lucide="triangle-alert"></i><h2>The campus could not load</h2><p id="replica-error-detail"></p><button id="replica-retry">Try again</button><a href="http://127.0.0.1:5173/">Return to LiDAR survey</a></div>
      <div className="capture-badge" id="capture-badge" hidden><span id="capture-badge-code">W</span><div><strong id="capture-badge-title">Wide camera</strong><small>East solar array · 8 Oct 2026</small></div><i data-lucide="crosshair"></i></div>
      <div className="replica-help-panel" id="replica-help-panel" hidden><div className="help-title"><h2>Explore the campus</h2><button className="icon-button" id="replica-help-close" aria-label="Close navigation help"><i data-lucide="x"></i></button></div><dl><div><dt>Orbit</dt><dd>Left-drag / one finger</dd></div><div><dt>Pan</dt><dd>Right-drag / two fingers</dd></div><div><dt>Zoom</dt><dd>Scroll / pinch</dd></div><div><dt>Reset compound</dt><dd><kbd>R</kbd></dd></div><div><dt>Top view</dt><dd><kbd>T</kbd></dd></div></dl><p>Use the location list to visit either solar array. W/T/Z changes imagery on the eastern array while keeping its surface and camera fixed.</p></div>
      <div className="replica-toast" id="replica-toast" role="status" hidden></div>
      <div className="replica-bottom"><div className="replica-location"><span className="location-indicator"></span><div><strong id="active-location">Entire compound</strong><span id="active-location-detail">University of Dubai</span></div></div><p className="replica-hint">Drag to orbit <span>·</span> Scroll to explore</p></div>
      <div className="imagery-attribution">Imagery © Esri, Maxar, Earthstar Geographics & the GIS User Community</div>
    </section>
  </main>
  <footer className="statusbar"><div className="status-message"><span className="status-dot" id="replica-status-dot"></span><span id="replica-status">Loading campus assets</span></div><div className="status-details"><span id="replica-mode-status">Measured building · contextual compound</span><span className="status-divider"></span><span>UTM 40N · metres</span></div></footer>
  <div className="drawer-backdrop" id="replica-backdrop" hidden></div>
  </>;
}
