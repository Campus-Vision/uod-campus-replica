import * as THREE from 'three';

// Depth preference affects rasterization only. XYZ, screen coordinates and the
// original full-campus base remain intact. The base fills every fine-mesh hole.
export function applyDetailPriority(material, bounds, camera) {
  if(!material.vertexShader.includes('gl_Position = projectionMatrix * viewPosition;')||
     !material.fragmentShader.includes('gl_FragColor ='))throw new Error('Measured detail shader required');
  material.uniforms.uDetailBounds={value:new THREE.Vector4(...bounds)};
  material.uniforms.uDetailNear={value:camera.near};
  material.uniforms.uDetailProjectionB={value:camera.projectionMatrix.elements[14]};
  material.vertexShader=material.vertexShader.replace('void main() {',`
    varying vec3 detailPosition;
    varying float detailDepth;
    void main() {`).replace('gl_Position = projectionMatrix * viewPosition;',`
    gl_Position = projectionMatrix * viewPosition;
    detailPosition = surfacePosition;
    detailDepth = -viewPosition.z;
  `);
  material.fragmentShader=material.fragmentShader.replace('void main() {',`
    uniform vec4 uDetailBounds;
    uniform float uDetailNear;
    uniform float uDetailProjectionB;
    varying vec3 detailPosition;
    varying float detailDepth;
    void main() {`).replace('gl_FragColor =',`
    float rim = min(min(detailPosition.x-uDetailBounds.x,uDetailBounds.y-detailPosition.x),
                    min(detailPosition.y-uDetailBounds.z,uDetailBounds.w-detailPosition.y));
    float preference = min(.08*smoothstep(0.,1.,rim),max(0.,detailDepth-uDetailNear-.001));
    gl_FragDepth = gl_FragCoord.z + .5*uDetailProjectionB*(1./(detailDepth-preference)-1./detailDepth);
    gl_FragColor =`);
  material.transparent=false;material.depthWrite=true;material.depthTest=true;
  material.needsUpdate=true;
  return material;
}

export function disposeSceneResources(root) {
  const geometries=new Set(),materials=new Set(),textures=new Set();
  root?.traverse(object=>{
    if(object.geometry)geometries.add(object.geometry);
    for(const material of Array.isArray(object.material)?object.material:[object.material]){
      if(!material)continue;
      materials.add(material);
      for(const value of Object.values(material))if(value?.isTexture)textures.add(value);
      for(const uniform of Object.values(material.uniforms||{})){
        const values=Array.isArray(uniform.value)?uniform.value:[uniform.value];
        for(const value of values)if(value?.isTexture)textures.add(value);
      }
    }
  });
  for(const value of [...textures,...materials,...geometries])value.dispose();
}
