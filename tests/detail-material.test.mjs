import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {applyDetailPriority,disposeSceneResources} from '../src/detail-material.js';

test('priority preserves screen coordinates and limits effective depth at close and distant views',()=>{
  const camera=new THREE.PerspectiveCamera(43,1,1,12000);
  for(const depth of [1.001,1.03,5,20,100,500]){
    const preference=Math.min(.08,Math.max(0,depth-camera.near-.001));
    const original=new THREE.Vector4(2,3,-depth,1).applyMatrix4(camera.projectionMatrix);
    const preferred=new THREE.Vector4(2,3,-depth+preference,1).applyMatrix4(camera.projectionMatrix);
    const displayed=original.clone();
    const fragmentDepth=.5*(original.z/original.w)+.5 +
      .5*camera.projectionMatrix.elements[14]*(1/(depth-preference)-1/depth);
    displayed.z=(fragmentDepth*2-1)*original.w;
    assert.ok(Math.abs(displayed.z/displayed.w-preferred.z/preferred.w)<1e-12);
    assert.equal(displayed.x/displayed.w,original.x/original.w);
    assert.equal(displayed.y/displayed.w,original.y/original.w);
    const recovered=new THREE.Vector4(0,0,displayed.z/displayed.w,1).applyMatrix4(camera.projectionMatrixInverse);
    assert.ok(Math.abs(-recovered.z/recovered.w-(depth-preference))<1e-8);
    assert.ok(depth-preference>=camera.near);
  }
  const material=new THREE.ShaderMaterial({vertexShader:'void main() { gl_Position = projectionMatrix * viewPosition; }',fragmentShader:'void main() { gl_FragColor = vec4(1.); }'});
  applyDetailPriority(material,[0,40,-240,-200],camera);
  assert.match(material.fragmentShader,/gl_FragDepth = gl_FragCoord.z/);
  assert.equal(material.transparent,false);assert.equal(material.depthWrite,true);
});

test('eviction releases shared atlas uniforms, materials and geometry exactly once',()=>{
  const root=new THREE.Group(),geometry=new THREE.PlaneGeometry(),texture=new THREE.Texture();
  const material=new THREE.ShaderMaterial({uniforms:{uRoofMap:{value:texture}}});
  root.add(new THREE.Mesh(geometry,material),new THREE.Mesh(geometry,material));
  const counts={geometry:0,material:0,texture:0};
  for(const [name,value] of Object.entries({geometry,material,texture}))value.addEventListener('dispose',()=>counts[name]++);
  disposeSceneResources(root);assert.deepEqual(counts,{geometry:1,material:1,texture:1});
});
