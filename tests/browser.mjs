import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const review = new URL('../../.impeccable/review/measured-react/', import.meta.url);
await mkdir(review, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
const errors = [], badRequests = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
page.on('response', response => { if (response.status() >= 400) badRequests.push({ url: response.url(), status: response.status() }); });
const capture = async name => {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({ path: fileURLToPath(new URL(name, review)), fullPage: true });
};
try {
  await page.goto('http://127.0.0.1:5174/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.uodReplica?.state.ready || !document.querySelector('#replica-error').hidden, null, { timeout: 120000 });
  assert.ok(await page.evaluate(() => window.uodReplica?.state.ready), await page.locator('#replica-error-detail').textContent());
  await page.waitForTimeout(800);
  console.log('LOADED', JSON.stringify(await page.evaluate(() => ({ ...window.uodReplica.state, triangles: window.uodReplica.renderer.info.render.triangles, south: window.uodReplica.southArray.userData }))));
  assert.equal(await page.evaluate(() => window.uodReplica.southArray.userData.rows), 3);
  const overview = await page.evaluate(() => {
    const v = window.uodReplica;
    return v.site.boundary.map(([x, y]) => v.controls.target.clone().set(x - v.site.origin[0], y - v.site.origin[1], 0).project(v.camera).toArray());
  });
  assert.ok(overview.every(([x, y, z]) => Math.abs(x) < 1 && Math.abs(y) < 1 && z < 1), 'Entire perimeter must be framed in the initial camera');
  await capture('desktop.png');
  await page.locator('[data-place="east"]').click();
  await page.waitForFunction(() => !window.uodReplica.state.transition);
  const reference = await page.evaluate(() => ({ camera: window.uodReplica.camera.position.toArray(), target: window.uodReplica.controls.target.toArray(), geometry: window.uodReplica.state.geometries.east }));
  for (const mode of ['wide', 'thermal', 'zoom', 'normal']) {
    await page.locator(`[data-capture="${mode}"]`).click();
    await page.waitForFunction(mode => window.uodReplica.state.capture === mode && !window.uodReplica.state.pendingCapture, mode, { timeout: 60000 });
    const actual = await page.evaluate(() => ({ camera: window.uodReplica.camera.position.toArray(), target: window.uodReplica.controls.target.toArray(), geometry: window.uodReplica.state.geometries.east }));
    assert.equal(actual.geometry, reference.geometry);
    assert.ok(Math.hypot(...actual.camera.map((x,i)=>x-reference.camera[i])) < 1e-6, `Switching to ${mode} must preserve camera`);
    assert.ok(Math.hypot(...actual.target.map((x,i)=>x-reference.target[i])) < 1e-6, `Switching to ${mode} must preserve target`);
    if (mode !== 'normal') await capture(`${mode}.png`);
  }
  await page.locator('[data-place="building"]').click();
  await page.waitForFunction(() => !window.uodReplica.state.transition);
  await capture('building.png');
  const original = await page.evaluate(() => {
    const v = window.uodReplica;
    return { uuid: v.building.geometry.uuid, camera: v.camera.position.toArray(),
      first: Array.from(v.building.geometry.attributes.position.array.slice(0, 100)),
      rgb: Array.from(v.building.geometry.attributes.color.array.slice(0, 100)) };
  });
  assert.ok(await page.evaluate(() => window.uodReplica.building.isPoints));
  assert.ok(await page.evaluate(() => window.uodReplica.state.building.count > 6000000));
  assert.equal(await page.evaluate(() => window.uodReplica.state.building.fittedArchitecture), false);
  assert.equal(await page.evaluate(() => window.uodReplica.building.material.toneMapped), false);
  assert.equal(await page.evaluate(() => window.uodReplica.buildingSurface.visible), true);
  assert.equal(await page.evaluate(() => window.uodReplica.building.visible), false);
  assert.ok(await page.evaluate(() => window.uodReplica.roofRepair.geometry.index.count > 30000));
  assert.equal(await page.evaluate(() => window.uodReplica.roofRepair.userData.estimated), true);
  await page.getByRole('button', {name:'Captured RGB', exact:true}).click();
  assert.equal(await page.evaluate(() => window.uodReplica.buildingUniforms.uSaturation.value), 1);
  assert.equal(await page.evaluate(() => window.uodReplica.buildingUniforms.uBrightness.value), 1);
  await capture('building-captured.png');
  await page.locator('#building-saturation').fill('1.4');
  await page.locator('#building-brightness').fill('1.15');
  await page.getByRole('button', {name:'Original points', exact:true}).click();
  assert.equal(await page.evaluate(() => window.uodReplica.building.visible), true);
  assert.equal(await page.evaluate(() => window.uodReplica.buildingSurface.visible), false);
  assert.equal(await page.evaluate(() => window.uodReplica.roofRepair.visible), false);
  await page.locator('#building-point-size').fill('0.15');
  assert.equal(await page.evaluate(() => window.uodReplica.buildingUniforms.uSaturation.value), 1.4);
  await page.getByRole('button', {name:'Natural daylight', exact:true}).click();
  assert.equal(await page.evaluate(() => window.uodReplica.buildingUniforms.uSaturation.value), 1.05);
  assert.equal(await page.evaluate(() => window.uodReplica.buildingUniforms.uNatural.value), 1);
  const after = await page.evaluate(() => {
    const v = window.uodReplica;
    return { uuid: v.building.geometry.uuid, camera: v.camera.position.toArray(),
      first: Array.from(v.building.geometry.attributes.position.array.slice(0, 100)),
      rgb: Array.from(v.building.geometry.attributes.color.array.slice(0, 100)) };
  });
  assert.equal(after.uuid, original.uuid); assert.deepEqual(after.first, original.first); assert.deepEqual(after.rgb, original.rgb);
  assert.ok(Math.hypot(...after.camera.map((x,i)=>x-original.camera[i])) < 1e-6);
  await page.locator('#building-point-size').fill('0.12');
  await capture('building-points.png');
  await page.getByRole('button', {name:'Merged surface', exact:true}).click();
  assert.equal(await page.evaluate(() => window.uodReplica.buildingSurface.visible), true);

  await page.locator('[data-place="south"]').click();
  await page.waitForFunction(() => !window.uodReplica.state.transition);
  await capture('south.png');
  await page.locator('#perimeter-toggle').check();
  assert.equal(await page.evaluate(() => window.uodReplica.perimeter.visible), true);
  await page.locator('#landscape-toggle').uncheck();
  assert.equal(await page.evaluate(() => window.uodReplica.landscape.visible), false);
  await page.locator('#landscape-toggle').check();
  await page.locator('#lighting-select').selectOption('soft');
  await page.locator('#lighting-select').selectOption('daylight');
  await page.locator('#replica-help').click(); assert.equal(await page.locator('#replica-help-panel').isVisible(), true);
  await page.keyboard.press('Escape'); assert.equal(await page.locator('#replica-help-panel').isVisible(), false);
  await page.locator('#replica-reset').click();
  await page.locator('[data-angle="top"]').click();
  assert.equal(await page.evaluate(() => window.uodReplica.state.angle), 'top');
  await page.locator('[data-angle="perspective"]').click();
  await page.locator('#perimeter-toggle').uncheck();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => document.querySelector('#replica-sidebar').getBoundingClientRect().right < 1);
  await page.waitForTimeout(400);
  await capture('mobile.png');
  await page.getByRole('button', { name: 'Open campus controls', exact: true }).click();
  await page.waitForFunction(() => Math.abs(document.querySelector('#replica-sidebar').getBoundingClientRect().left) < 1);
  await capture('mobile-controls.png');
  await page.locator('#replica-close').click();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.deepEqual(badRequests, []);
  assert.deepEqual(errors, []);
  const result = { passed: true, tests: ['full-perimeter-framing', 'both-solar-clusters', 'shared-WTZ-geometry', 'fixed-WTZ-camera', 'wide-thermal-zoom', 'building-south-bookmarks', 'merged-surface-toggle', 'original-measured-points', 'reversible-react-colour-controls', 'unchanged-geometry-and-source-rgb', 'landscape', 'perimeter', 'lighting', 'view-presets', 'help', 'mobile-drawer'], state: await page.evaluate(() => window.uodReplica.state), errors, badRequests };
  await writeFile(new URL('browser-results.json', review), JSON.stringify(result, null, 2));
  console.log('PASS', JSON.stringify(result));
} catch (error) {
  console.log('ERRORS', JSON.stringify(errors)); console.log('BAD_REQUESTS', JSON.stringify(badRequests));
  await capture('failure.png'); throw error;
} finally { await browser.close(); }
