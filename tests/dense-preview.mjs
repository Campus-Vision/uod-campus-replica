// Fixed camera inspection of actual triangles, old surfaces and original points.
import {chromium} from '@playwright/test';
import {mkdir,writeFile,copyFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const review='../.impeccable/review/dense';await mkdir(review,{recursive:true});
const name=process.argv[2]||'south-pilot';
const textured=process.argv.includes('--textured');
const modelName=name+(textured?'-textured':'');
const viewName=process.argv.find(arg=>arg.startsWith('--view='))?.slice(7)||name;
const captureName=modelName+(viewName!==name?'-'+viewName:'');
const views={
 'south-pilot':{target:[-15.85,-220.46,3.8],camera:[-1.85,-241.46,21.8]},
 'building-pilot':{target:[-57,-140,14],camera:[-90,-182,48]},
 'building-trajectory':{target:[-57,-140,14],camera:[-90,-182,48]},
 'vegetation-pilot':{target:[-110,-180,4],camera:[-90,-205,20]},
 'campus-base-browser':{target:[-20,-150,5],camera:[-280,-510,330]},
 'campus-base-browser-v2':{target:[-20,-150,5],camera:[-280,-510,330]},
};
assert.ok(views[viewName], 'Unknown fixed comparison view');
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto('http://127.0.0.1:5174/');
 await page.waitForFunction(()=>window.uodReplica?.state.ready,null,{timeout:120000});
 await copyFile(`../analysis/dense-reconstruction/${modelName}.glb`,`public/replica/dense-${modelName}.glb`);
 const report=await page.evaluate(async ({name,view})=>{
  const {GLTFLoader}=await import('/node_modules/three/examples/jsm/loaders/GLTFLoader.js');
  const gltf=await new GLTFLoader().loadAsync(`/replica/dense-${name}.glb`);const v=window.uodReplica;
  let sourceMaterial;v.buildingSurface.traverse(o=>{if(o.isMesh&&!o.userData.estimated)sourceMaterial=o.material;});
  let faces=0;gltf.scene.traverse(o=>{if(o.isMesh){const texture=o.material.map;o.material=sourceMaterial.clone();if(texture){texture.colorSpace='';texture.needsUpdate=true;o.material.defines={...o.material.defines,ROOF_TEXTURE:1};o.material.uniforms.uRoofMap.value=texture;}faces+=o.geometry.index.count/3;}});
  v.scene.add(gltf.scene);window.__denseTrial=gltf.scene;
  v.building.visible=false;v.buildingSurface.visible=false;v.measuredDetails.visible=false;
  v.landscape.visible=false;
  v.controls.target.set(...view.target);v.camera.position.set(...view.camera);v.controls.update();
  v.renderer.render(v.scene,v.camera);return {triangles:faces,target:v.controls.target.toArray(),camera:v.camera.position.toArray()};
 },{name:modelName,view:views[viewName]});
 assert.ok(textured?report.triangles>50000&&report.triangles<500000:
   report.triangles>(name.startsWith('campus-base-')?100000:1000000));
 await page.screenshot({path:`${review}/${captureName}-dense.png`});
 await page.evaluate(()=>{const v=window.uodReplica;window.__denseTrial.visible=false;v.buildingSurface.visible=true;v.measuredDetails.visible=true;v.renderer.render(v.scene,v.camera);});
 await page.screenshot({path:`${review}/${captureName}-previous.png`});
 await page.evaluate(()=>{const v=window.uodReplica;v.buildingSurface.visible=false;v.measuredDetails.visible=false;v.building.visible=true;v.renderer.render(v.scene,v.camera);});
 await page.screenshot({path:`${review}/${captureName}-points.png`});
 report.errors=errors;await writeFile(`${review}/${captureName}-results.json`,JSON.stringify(report,null,2));
 assert.deepEqual(errors,[]);console.log(report);
}finally{await browser.close();}
