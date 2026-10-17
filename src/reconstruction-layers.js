import * as THREE from 'three';

export function makeRoofLayer(data, material) {
  const count = data.positions.length / 3;
  if (!Number.isInteger(count) || !data.positions.every(Number.isFinite)) throw new Error('Invalid roof positions');
  if (data.uv.length !== count * 2 || !data.uv.every(v => Number.isFinite(v) && v >= 0 && v <= 1)) throw new Error('Invalid roof UV data');
  if (data.indices.length % 3 || !data.indices.every(i => Number.isInteger(i) && i >= 0 && i < count)) throw new Error('Invalid roof index');
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(data.positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(data.uv, 2));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(count * 3).fill(1), 3));
  geometry.setIndex(data.indices); geometry.computeBoundingSphere();
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = 'Aerial-informed western roof repair';
  mesh.userData = {...data.metadata, estimated: true};
  return mesh;
}

export function makeDetailLayers(data, arrays, materialFactory) {
  for (const key of ['positions','colors','normals']) {
    if (arrays[key].length !== data.count * 3) throw new Error(`Invalid detail ${key}`);
  }
  if (arrays.radii.length !== data.count || !arrays.radii.every(r => Number.isFinite(r) && r > 0 && r <= .14)) throw new Error('Invalid detail radius');
  const regions = data.metadata.regions;
  let expectedStart = 0;
  const group = new THREE.Group(); group.name = 'Measured local surface detail';
  const base = new THREE.PlaneGeometry(2, 2);
  for (const region of regions) {
    if (region.start !== expectedStart || region.count < 1 || region.start + region.count > data.count) throw new Error('Invalid detail region range');
    expectedStart += region.count;
    const begin = region.start, end = begin + region.count;
    const geometry = new THREE.InstancedBufferGeometry();
    geometry.index = base.index.clone();
    for (const name of ['position','uv']) geometry.setAttribute(name, base.attributes[name].clone());
    geometry.setAttribute('patchCenter', new THREE.InstancedBufferAttribute(arrays.positions.slice(begin*3,end*3),3));
    geometry.setAttribute('patchColour', new THREE.InstancedBufferAttribute(arrays.colors.slice(begin*3,end*3),3,true));
    geometry.setAttribute('patchNormal', new THREE.InstancedBufferAttribute(arrays.normals.slice(begin*3,end*3),3));
    geometry.setAttribute('patchRadius', new THREE.InstancedBufferAttribute(arrays.radii.slice(begin,end),1));
    geometry.instanceCount = region.count;
    geometry.boundingBox = new THREE.Box3().setFromArray(arrays.positions.subarray(begin*3,end*3));
    geometry.boundingBox.expandByScalar(.14);
    geometry.boundingSphere = geometry.boundingBox.getBoundingSphere(new THREE.Sphere());
    const mesh = new THREE.Mesh(geometry, materialFactory());
    mesh.name = region.id; mesh.userData = { ...region, measuredCentres: true };
    group.add(mesh);
  }
  base.dispose();
  if (expectedStart !== data.count) throw new Error('Unassigned detail points');
  return group;
}

export function syncReconstructionLayers(representation, showLandscape, roof, details) {
  if (roof) roof.visible = representation === 'surface';
  if (details) {
    details.visible = representation === 'surface';
    for (const region of details.children) region.visible = !region.userData.landscape || showLandscape;
  }
}
