import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { createBackgroundLandscape } from '../src/background-landscape.js';

const trees = [[12, -8, 999, 3], [-4, 20, -999, 5]];
const groundHeight = (x, y) => .1 * x + .2 * y;

test('illustrative trees are deterministic and independent of source ordering', () => {
  const first = createBackgroundLandscape(trees, groundHeight);
  const second = createBackgroundLandscape(trees, groundHeight);
  const reversed = createBackgroundLandscape([...trees].reverse(), groundHeight);
  first.children.forEach((mesh, i) => {
    assert.deepEqual(mesh.instanceMatrix.array, second.children[i].instanceMatrix.array);
    assert.deepEqual(mesh.instanceColor.array, second.children[i].instanceColor.array);
    const perTree = mesh.count / trees.length;
    assert.deepEqual(mesh.instanceMatrix.array.slice(0, perTree * 16),
      reversed.children[i].instanceMatrix.array.slice(perTree * 16));
  });
});

test('geometry stays inside source canopy radii and each trunk starts at local terrain', () => {
  const group = createBackgroundLandscape(trees, groundHeight);
  const matrix = new THREE.Matrix4(), point = new THREE.Vector3();
  for (const mesh of group.children) {
    const instancesPerTree = mesh.count / trees.length;
    for (let i = 0; i < mesh.count; i++) {
      const [x, y, , radius] = trees[Math.floor(i / instancesPerTree)];
      const ground = groundHeight(x, y);
      mesh.getMatrixAt(i, matrix);
      const positions = mesh.geometry.attributes.position;
      for (let j = 0; j < positions.count; j++) {
        point.fromBufferAttribute(positions, j).applyMatrix4(matrix);
        assert.ok(Math.hypot(point.x - x, point.y - y) <= radius + 1e-5);
        assert.ok(point.z >= ground - 1e-5);
        assert.ok(point.z <= ground + Math.max(3, radius * 1.55) * 1.4);
      }
      if (mesh.name === 'Illustrative trunks and branches' && i % instancesPerTree === 0) {
        point.set(0, -.5, 0).applyMatrix4(matrix);
        assert.ok(point.distanceTo(new THREE.Vector3(x, y, ground)) < 1e-5);
      }
    }
  }
});

test('uses lit mesh geometry, finite transforms, and a bounded triangle budget', () => {
  const group = createBackgroundLandscape(trees, groundHeight);
  assert.equal(group.userData.modelledTreeCount, trees.length);
  assert.equal(group.children.length, 2);
  let triangleCount = 0;
  for (const mesh of group.children) {
    assert.ok(mesh.isInstancedMesh);
    assert.ok(mesh.material.isMeshStandardMaterial);
    assert.ok(mesh.count > 0);
    assert.ok([...mesh.instanceMatrix.array].every(Number.isFinite));
    const triangles = (mesh.geometry.index?.count ?? mesh.geometry.attributes.position.count) / 3;
    triangleCount += triangles * mesh.count;
  }
  assert.ok(triangleCount / trees.length <= 1800);
  assert.equal(group.children.find(mesh => mesh.name === 'Illustrative leaves').material.side, THREE.DoubleSide);
});

test('accepts empty and sparse inputs without phantom trees', () => {
  assert.equal(createBackgroundLandscape([], groundHeight).children.length, 0);
  const sparse = [];
  sparse[2] = trees[0];
  sparse[3] = [1, 2, 3, 0];
  sparse[4] = [NaN, 0, 0, 2];
  const group = createBackgroundLandscape(sparse, groundHeight);
  assert.equal(group.userData.modelledTreeCount, 1);
  assert.equal(createBackgroundLandscape([[1, 2, 0, 3]], () => NaN).userData.modelledTreeCount, 0);
});
