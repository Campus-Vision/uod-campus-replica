import * as THREE from 'three';

const LIMBS_PER_TREE = 25;
const LEAVES_PER_TWIG = 40;
const LEAVES_PER_TREE = 16 * LEAVES_PER_TWIG;

// Seed only from the source location/radius: filtering or reordering trees must
// never change the appearance of the remaining illustrative vegetation.
function treeRandom(x, y, radius) {
  let seed = 2166136261;
  for (const character of `${x},${y},${radius}`) seed = Math.imul(seed ^ character.charCodeAt(0), 16777619);
  return () => {
    seed += 0x6d2b79f5;
    let value = Math.imul(seed ^ seed >>> 15, 1 | seed);
    value ^= value + Math.imul(value ^ value >>> 7, 61 | value);
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  };
}

/**
 * Optional illustrative background trees, never a reconstruction of scanned
 * vegetation. Input uses the scene's local Z-up [x,y,z,radius] coordinates;
 * source z is ignored in favour of groundHeight(x,y), matching terrain anchors.
 * Radius bounds the horizontal canopy. No textures, billboards, or animation.
 */
export function createBackgroundLandscape(trees, groundHeight) {
  const group = new THREE.Group();
  group.name = 'Illustrative background landscape';
  const anchored = [];
  for (const tree of trees) {
    if (!tree || ![tree[0], tree[1], tree[3]].every(Number.isFinite) || tree[3] <= 0) continue;
    const ground = typeof groundHeight === 'function' ? groundHeight(tree[0], tree[1]) : groundHeight;
    if (Number.isFinite(ground)) anchored.push([tree[0], tree[1], ground, tree[3]]);
  }
  group.userData.modelledTreeCount = anchored.length;
  group.userData.illustrative = true;
  if (!anchored.length) return group;

  // Six-sided open tapered cylinders: 12 triangles per limb. Leaves are small
  // folded diamonds (two triangles), with no alpha textures or point sprites.
  const woodGeometry = new THREE.CylinderGeometry(.35, 1, 1, 6, 1, true);
  const leafGeometry = new THREE.BufferGeometry();
  leafGeometry.setAttribute('position', new THREE.Float32BufferAttribute([
    0, -.5, 0, -.22, 0, .08, 0, .5, 0, .22, 0, .08,
  ], 3));
  leafGeometry.setIndex([0, 1, 2, 0, 2, 3]);
  leafGeometry.computeVertexNormals();
  const wood = new THREE.InstancedMesh(woodGeometry,
    new THREE.MeshStandardMaterial({ color: '#fff', roughness: 1 }), anchored.length * LIMBS_PER_TREE);
  const leaves = new THREE.InstancedMesh(leafGeometry,
    new THREE.MeshStandardMaterial({ color: '#fff', roughness: .92, side: THREE.DoubleSide }), anchored.length * LEAVES_PER_TREE);
  wood.name = 'Illustrative trunks and branches';
  leaves.name = 'Illustrative leaves';
  const olive = ['#656b3d', '#72764a', '#58603a', '#808052', '#606842'].map(value => new THREE.Color(value));
  const bark = new THREE.Color();
  const transform = new THREE.Object3D();
  const start = new THREE.Vector3(), end = new THREE.Vector3(), direction = new THREE.Vector3();
  const branchStart = new THREE.Vector3(), branchEnd = new THREE.Vector3();
  const up = new THREE.Vector3(0, 1, 0);
  let woodIndex = 0, leafIndex = 0;
  function limb(from, to, thickness, random) {
    direction.subVectors(to, from);
    transform.position.copy(from).addScaledVector(direction, .5);
    const length = direction.length();
    transform.quaternion.setFromUnitVectors(up, direction.multiplyScalar(1 / length));
    transform.scale.set(thickness, length, thickness);
    transform.updateMatrix();
    wood.setMatrixAt(woodIndex, transform.matrix);
    bark.setHSL(.095 + random() * .025, .15 + random() * .08, .26 + random() * .08);
    wood.setColorAt(woodIndex++, bark);
  }
  for (const [x, y, ground, radius] of anchored) {
    const random = treeRandom(x, y, radius), height = Math.max(3, radius * 1.55);
    const phase = random() * Math.PI * 2;
    start.set(x, y, ground);
    end.set(x, y, ground + height * .65);
    limb(start, end, Math.min(.25, radius * .07), random);
    for (let b = 0; b < 8; b++) {
      const angle = phase + b * 2.399963 + (random() - .5) * .35;
      const reach = radius * (.37 + random() * .16);
      branchStart.set(x, y, ground + height * (.36 + random() * .23));
      branchEnd.set(x + Math.cos(angle) * reach, y + Math.sin(angle) * reach,
        ground + height * (.69 + random() * .22));
      limb(branchStart, branchEnd, radius * .028, random);
      for (let t = 0; t < 2; t++) {
        const twigAngle = angle + (t ? .48 : -.48);
        end.set(branchEnd.x + Math.cos(twigAngle) * radius * .21,
          branchEnd.y + Math.sin(twigAngle) * radius * .21,
          branchEnd.z + height * (.03 + random() * .12));
        limb(branchEnd, end, radius * .011, random);
        for (let l = 0; l < LEAVES_PER_TWIG; l++) {
          const azimuth = random() * Math.PI * 2;
          const vertical = random() * 2 - 1;
          const spread = Math.cbrt(random());
          const horizontal = Math.sqrt(1 - vertical * vertical) * spread * radius * .25;
          let dx = end.x - x + Math.cos(azimuth) * horizontal;
          let dy = end.y - y + Math.sin(azimuth) * horizontal;
          const radial = Math.hypot(dx, dy);
          if (radial > radius * .88) { dx *= radius * .88 / radial; dy *= radius * .88 / radial; }
          transform.position.set(x + dx, y + dy, end.z + vertical * spread * radius * .22);
          transform.rotation.set(random() * Math.PI, random() * Math.PI, random() * Math.PI * 2);
          const size = radius * (.095 + random() * .065);
          transform.scale.setScalar(size);
          transform.updateMatrix();
          leaves.setMatrixAt(leafIndex, transform.matrix);
          leaves.setColorAt(leafIndex++, olive[Math.floor(random() * olive.length)]);
        }
      }
    }
  }
  for (const mesh of [wood, leaves]) {
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.computeBoundingSphere();
    group.add(mesh);
  }
  return group;
}
