import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const output='../.impeccable/review/progressive-details';await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
const views=[
  {id:'parking-oblique',target:[40,-220,5],eye:[40,-277,80],expected:'cell-1--6-textured'},
  {id:'parking-top',target:[40,-220,5],eye:[40,-220.01,100],expected:'cell-0--6-textured'},
  {id:'building-oblique',target:[-57,-140,14],eye:[-100,-205,55],expected:'building-pilot-textured'},
  {id:'vegetation-oblique',target:[-110,-180,4],eye:[-90,-205,20],expected:'vegetation-pilot-textured'},
  {id:'south-oblique',target:[-15.85,-220.46,3.8],eye:[-1.85,-251.46,24.8],expected:'south-pilot-textured'},
];
const results=[];
try{
  await page.goto('http://127.0.0.1:5174/');
  await page.waitForFunction(()=>window.uodReplica?.state.ready,null,{timeout:120000});
  await page.waitForTimeout(300);
  for(const view of views){
    await page.evaluate(view=>{
      const v=window.uodReplica;v.controls.enableDamping=false;v.controls.update();
      v.controls.target.set(...view.target);v.camera.position.set(...view.eye);v.controls.update();
    },view);
    const expected=await page.evaluate(async()=>{
      const {selectDetailTiles}=await import('/src/detail-loading.js');
      const manifest=await(await fetch('/replica/mesh-details.json')).json(),v=window.uodReplica;
      return selectDetailTiles(manifest.tiles,v.camera.position,v.controls.target).map(t=>t.id);
    });
    await page.waitForFunction(ids=>ids.every(id=>window.uodReplica.state.detail.visible.includes(id)),expected,{timeout:30000});
    await page.screenshot({path:`${output}/${view.id}-detail.png`});
    const result=await page.evaluate(()=>{
      const v=window.uodReplica;
      const result={visible:v.state.detail.visible,resident:v.measuredDetails.children.length,
        camera:v.camera.position.toArray(),target:v.controls.target.toArray(),textures:v.renderer.info.memory.textures};
      v.measuredDetails.visible=false;v.renderer.render(v.scene,v.camera);return result;
    });
    assert.ok(result.resident<=4);assert.ok(result.visible.length<=4);
    await page.screenshot({path:`${output}/${view.id}-base.png`});
    await page.evaluate(()=>{const v=window.uodReplica;v.measuredDetails.visible=true;v.renderer.render(v.scene,v.camera);});
    results.push({view:view.id,...result});
  }
  // Original points must hide all mesh detail, without altering the camera.
  const before=await page.evaluate(()=>window.uodReplica.camera.position.toArray());
  await page.getByRole('button',{name:'Original points',exact:true}).click();
  await page.waitForFunction(()=>window.uodReplica.state.detail.visible.length===0);
  assert.deepEqual(await page.evaluate(()=>window.uodReplica.camera.position.toArray()),before);
  assert.equal(await page.evaluate(()=>window.uodReplica.measuredDetails.visible),false);
  await page.getByRole('button',{name:'Reconstructed mesh',exact:true}).click();
  await page.waitForFunction(()=>window.uodReplica.state.detail.visible.length>0);
  assert.deepEqual(errors,[]);
  await writeFile(`${output}/results.json`,JSON.stringify({views:results,errors},null,2));
  console.log(JSON.stringify({views:results,errors},null,2));
}finally{await browser.close();}
