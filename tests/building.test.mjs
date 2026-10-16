import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, open, access } from 'node:fs/promises';
import { solarFrame, inverseAffine } from '../src/replica-math.js';

const asset = name => new URL(`../public/replica/${name}`, import.meta.url);
const json = async path => JSON.parse(await readFile(path, 'utf8'));

test('emitted points and RGB match original LAS records, without fitted geometry', async () => {
  const [meta, positions, colours, audit] = await Promise.all([
    json(asset('building.json')), readFile(asset('building.positions.bin')),
    readFile(asset('building.colors.bin')), json(new URL('./building-audit.json', import.meta.url)),
  ]);
  assert.equal(meta.count, 6659157);
  assert.equal(positions.byteLength, meta.count * 12);
  assert.equal(colours.byteLength, meta.count * 3);
  const las = await open(new URL('../../20261008121946091.las', import.meta.url), 'r');
  try {
    const header = Buffer.alloc(227); await las.read(header, 0, header.length, 0);
    const pointOffset = header.readUInt32LE(96), stride = header.readUInt16LE(105);
    assert.equal(header[104], 3);
    for (const {outputIndex, lasRecordIndex} of audit) {
      const point = Buffer.alloc(stride); await las.read(point, 0, stride, pointOffset + lasRecordIndex * stride);
      for (let axis = 0; axis < 3; axis++) {
        const source = point.readInt32LE(axis * 4) * header.readDoubleLE(131 + axis * 8) + header.readDoubleLE(155 + axis * 8);
        const emitted = positions.readFloatLE(outputIndex * 12 + axis * 4) + meta.origin[axis];
        assert.ok(Math.abs(source - emitted) < .0001, 'An actual source position must survive within float32 storage precision');
        const channel = point.readUInt16LE(28 + axis * 2);
        assert.equal(colours[outputIndex * 3 + axis], channel <= 255 ? channel : Math.round(channel / 257));
      }
    }
  } finally { await las.close(); }
});

test('separate React project has its own entry, dependencies and local scene assets', async () => {
  const pkg = await json(new URL('../package.json', import.meta.url));
  assert.ok(pkg.dependencies.react && pkg.dependencies['react-dom']);
  const app = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8');
  const scene = await readFile(new URL('../src/scene.js', import.meta.url), 'utf8');
  assert.ok(app.includes('useEffect') && app.includes('engine.current?.dispose()'));
  assert.ok(!scene.includes('campus-surfaces.glb') && !scene.includes('campus-facades.glb'));
  assert.ok(!scene.includes("../../viewer"));
  for (const file of ['terrain.glb', 'east-surface.glb', 'wide.jpg', 'thermal.jpg', 'zoom.jpg']) await access(asset(file));
});

test('both solar arrays and all covered parking remain within the compound', async () => {
  const site = await json(asset('site.json'));
  const inside = ([x, y]) => {
    let yes = false;
    for (let i = 0, j = site.boundary.length - 1; i < site.boundary.length; j = i++) {
      const [a, b] = site.boundary[i], [c, d] = site.boundary[j];
      if (((b > y) !== (d > y)) && x < (c - a) * (y - b) / (d - b) + a) yes = !yes;
    }
    return yes;
  };
  assert.equal(site.eastRows.length, 3); assert.equal(site.southRows.length, 3);
  assert.equal(site.coveredParking.length, 6);
  for (const row of [...site.eastRows, ...site.southRows, ...site.coveredParking.map(c => c.points)]) {
    assert.ok(row.every(inside));
    assert.ok(solarFrame(row, site.origin).length > 0);
  }
  for (const item of Object.values(site.registration)) {
    assert.equal(item.sourceToReferenceLocal.length, 3);
    const inverse = inverseAffine(item.sourceToReferenceLocal);
    const p = [165, 50, 1];
    const q = item.sourceToReferenceLocal.map(row => row.reduce((sum, value, i) => sum + value * p[i], 0));
    const restored = inverse.map(row => row.reduce((sum, value, i) => sum + value * q[i], 0));
    assert.ok(Math.hypot(...restored.map((value, i) => value - p[i])) < 1e-8);
  }
});
