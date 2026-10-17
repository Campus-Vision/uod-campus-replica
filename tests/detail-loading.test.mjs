import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { selectDetailTiles, createDetailManager } from '../src/detail-loading.js';

const tiles=[
  {id:'left',boundsLocal:[0,40,-240,-200]},
  {id:'right',boundsLocal:[40,80,-240,-200]},
  {id:'far',boundsLocal:[500,540,500,540]},
];
const eye=new THREE.Vector3(40,-250,30),target=new THREE.Vector3(40,-220,5);
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('detail selection is bounded, stable and inactive at overview distance',()=>{
  assert.deepEqual(selectDetailTiles(tiles,eye,target).map(t=>t.id),['left','right']);
  assert.deepEqual(selectDetailTiles(tiles,new THREE.Vector3(0,0,500),target),[]);
  assert.equal(selectDetailTiles(tiles,eye,target,1).length,1);
  assert.deepEqual(eye.toArray(),[40,-250,30]);
});

test('only ready detail is visible; the manager never modifies base coverage',async()=>{
  const group=new THREE.Group(),clips={count:0,rects:[]};let resolve;
  const manager=createDetailManager({tiles:[tiles[0]],group,clips,load:()=>new Promise(r=>resolve=r),
    release:()=>{},invalidate:()=>{}});
  manager.update(eye,target,true);
  assert.equal(clips.count,0);
  resolve(new THREE.Group());await tick();
  assert.equal(group.children.length,1);assert.deepEqual(manager.visibleIds(),['left']);
  assert.deepEqual(clips,{count:0,rects:[]});
  manager.update(eye,target,false);
  assert.equal(clips.count,0);assert.equal(group.children[0].visible,false);
  manager.dispose();
});

test('cancelled or disposed late results are released, never attached',async()=>{
  const group=new THREE.Group(),clips={count:0,rects:[]},released=[];let resolve,signal;
  const manager=createDetailManager({tiles:[tiles[0]],group,clips,
    load:(_,s)=>{signal=s;return new Promise(r=>resolve=r);},release:o=>released.push(o),invalidate:()=>{}});
  manager.update(eye,target,true);manager.dispose();
  assert.equal(signal.aborted,true);
  const object=new THREE.Group();resolve(object);await tick();
  assert.deepEqual(released,[object]);assert.equal(group.children.length,0);assert.equal(clips.count,0);
});

test('camera changes evict inactive meshes within the resident cap',async()=>{
  const group=new THREE.Group(),clips={count:0,rects:[]},released=[];
  const manager=createDetailManager({tiles,group,clips,maxResident:1,
    load:async t=>Object.assign(new THREE.Group(),{name:t.id}),release:o=>released.push(o.name),invalidate:()=>{}});
  manager.update(new THREE.Vector3(10,-230,20),new THREE.Vector3(10,-220,0),true);await tick();
  manager.update(new THREE.Vector3(70,-230,20),new THREE.Vector3(70,-220,0),true);await tick();
  assert.equal(group.children.length,1);assert.equal(group.children[0].name,'right');
  assert.deepEqual(released,['left']);manager.dispose();
});

test('at most two requests run concurrently even when four tiles are wanted',async()=>{
  const group=new THREE.Group(),clips={count:0,rects:[]},requests=[];
  const manager=createDetailManager({tiles:Array.from({length:4},(_,i)=>({...tiles[0],id:String(i)})),
    group,clips,load:()=>new Promise(resolve=>requests.push(resolve)),release:()=>{},invalidate:()=>{}});
  manager.update(eye,target,true);assert.equal(requests.length,2);
  requests[0](new THREE.Group());await tick();assert.equal(requests.length,3);
  manager.dispose();requests[1](new THREE.Group());requests[2](new THREE.Group());await tick();
  assert.equal(requests.length,3);assert.equal(group.children.length,0);
});

test('failed detail requires explicit retry and can recover at an unchanged view',async()=>{
  const group=new THREE.Group();let attempts=0,failures=0;
  const manager=createDetailManager({tiles:[tiles[0]],group,
    load:async()=>{if(++attempts===1)throw new Error('Transient failure');return new THREE.Group();},
    release:()=>{},invalidate:()=>{},onError:()=>failures++});
  manager.update(eye,target,true);await tick();
  manager.update(eye,target,true);await tick();
  assert.equal(attempts,1);assert.equal(failures,1);
  manager.retry();await tick();
  assert.equal(attempts,2);assert.deepEqual(manager.visibleIds(),['left']);
  manager.dispose();manager.retry();assert.equal(attempts,2);
});
