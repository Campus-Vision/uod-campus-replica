import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { makeRoofLayer, makeDetailLayers, syncReconstructionLayers } from '../src/reconstruction-layers.js';

test('roof repair retains local coordinates, imagery UVs and source disclosure', () => {
  const data = { positions: [0,0,24, 1,0,24, 0,1,24], uv: [.1,.2,.2,.2,.1,.3], indices: [0,1,2], metadata: { estimated: true } };
  const mesh = makeRoofLayer(data, new THREE.MeshBasicMaterial());
  assert.deepEqual([...mesh.geometry.attributes.position.array], data.positions);
  assert.equal(mesh.geometry.index.count, 3);
  assert.equal(mesh.userData.estimated, true);
  assert.throws(() => makeRoofLayer({...data, indices:[0,1,7]}, mesh.material), /index/i);
  assert.throws(() => makeRoofLayer({...data, uv:[2,0]}, mesh.material), /UV/i);
});

test('oriented patches keep measured centres and separate vegetation visibility', () => {
  const metadata = { count: 2, metadata: { regions: [
    {id:'parking',start:0,count:1,landscape:false}, {id:'trees',start:1,count:1,landscape:true},
  ] } };
  const arrays = { positions:new Float32Array([1,2,3,4,5,6]), colors:new Uint8Array([120,140,160,80,100,70]), normals:new Float32Array([0,0,1,0,1,0]), radii:new Float32Array([.08,.1]) };
  const group = makeDetailLayers(metadata, arrays, () => new THREE.MeshBasicMaterial());
  assert.equal(group.children.length, 2);
  assert.deepEqual([...group.children[0].geometry.attributes.patchCenter.array], [1,2,3]);
  assert.equal(group.children[0].geometry.instanceCount, 1);
  const roof = new THREE.Group();
  syncReconstructionLayers('surface', false, roof, group);
  assert.equal(roof.visible,true); assert.equal(group.children[0].visible,true); assert.equal(group.children[1].visible,false);
  syncReconstructionLayers('points', true, roof, group);
  assert.equal(roof.visible,false); assert.equal(group.visible,false);
  assert.throws(() => makeDetailLayers(metadata, {...arrays,radii:new Float32Array([1,1])},()=>new THREE.MeshBasicMaterial()),/radius/i);
});
