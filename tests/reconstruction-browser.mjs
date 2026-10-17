import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const directory='../.impeccable/review/reconstruction';await mkdir(directory,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
await page.goto('http://127.0.0.1:5174/');await page.waitForFunction(()=>window.uodReplica?.state.ready,null,{timeout:120000});
// Restore the original coarse GLB index only for the baseline capture; do not
// compare against an empty region after replacement has already removed faces.
await page.evaluate(async()=>{
 const buffer=await(await fetch('/replica/building-surface.glb')).arrayBuffer(),view=new DataView(buffer),length=view.getUint32(12,true);
 const doc=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,20,length))),p=doc.meshes[0].primitives[0],a=doc.accessors[p.indices],b=doc.bufferViews[a.bufferView];
 const start=28+length+(b.byteOffset||0)+(a.byteOffset||0),raw=a.componentType===5125?new Uint32Array(buffer,start,a.count):new Uint16Array(buffer,start,a.count);
 window.__baselineIndices=[];
 window.uodReplica.buildingSurface.traverse(o=>{if(o.isMesh&&!o.userData.estimated){const filtered=o.geometry.index;window.__baselineIndices.push({geometry:o.geometry,filtered,original:new filtered.constructor(raw,1)});}});
});
const results={errors,baseline:'Original coarse GLB index and hidden new detail; identical camera',regions:[]};
for(const id of ['south-parking','west-tree-row']){
 const info=await page.evaluate(id=>{const v=window.uodReplica,r=v.measuredDetails.children.find(o=>o.name===id),a=r.geometry.attributes.patchCenter.array,b=r.geometry.boundingBox,c=b.getCenter(v.controls.target.clone());let best=0,d=Infinity;for(let i=0;i<a.length;i+=3){const q=(a[i]-c.x)**2+(a[i+1]-c.y)**2;if(q<d){best=i;d=q}}v.controls.target.set(a[best],a[best+1],a[best+2]);v.camera.position.copy(v.controls.target).add(c.set(14,-21,17));v.controls.update();v.renderer.render(v.scene,v.camera);return {id,count:r.geometry.instanceCount,target:v.controls.target.toArray(),camera:v.camera.position.toArray()};},id);
 await page.waitForTimeout(150);await page.screenshot({path:`${directory}/${id}-detail.png`});
 await page.evaluate(()=>{const v=window.uodReplica;v.measuredDetails.visible=false;window.__baselineIndices.forEach(r=>r.geometry.setIndex(r.original));v.renderer.render(v.scene,v.camera)});await page.screenshot({path:`${directory}/${id}-base.png`});
 await page.evaluate(()=>{const v=window.uodReplica;v.measuredDetails.visible=true;window.__baselineIndices.forEach(r=>r.geometry.setIndex(r.filtered));v.renderer.render(v.scene,v.camera)});results.regions.push(info);
}
await page.getByRole('button',{name:'Switch to dark theme'}).click();await page.screenshot({path:`${directory}/dark-detail.png`});
await page.getByRole('button',{name:'University building',exact:false}).click();await page.screenshot({path:`${directory}/roof-dark.png`});
await writeFile(`${directory}/comparison-results.json`,JSON.stringify(results,null,2));await browser.close();if(errors.length)throw Error(errors.join('\n'));console.log(JSON.stringify(results));
