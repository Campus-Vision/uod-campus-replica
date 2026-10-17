import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const root = new URL('../public/replica/', import.meta.url);
const world = (x,y) => [339750+x/1497*900,2778350.09765625-y/1664*1000.1953125];
function contains(p,a,b,c) {
  const cross=(u,v,w)=>(v[0]-u[0])*(w[1]-u[1])-(v[1]-u[1])*(w[0]-u[0]);
  const s=[cross(a,b,p),cross(b,c,p),cross(c,a,p)];
  return s.every(x=>x>=-1e-5)||s.every(x=>x<=1e-5);
}
test('roof infill closes measured reflective gaps while preserving the courtyard and georeference',async()=>{
  const blob=await readFile(new URL('building-surface.glb',root));
  const jsonLength=blob.readUInt32LE(12), glb=JSON.parse(blob.subarray(20,20+jsonLength));
  const primitive=glb.meshes[0].primitives[0], dataStart=28+jsonLength;
  const accessor=(id,width)=>{
    const a=glb.accessors[id],v=glb.bufferViews[a.bufferView],start=dataStart+(v.byteOffset??0)+(a.byteOffset??0);
    return {count:a.count,read:(index,axis=0)=>a.componentType===5126?blob.readFloatLE(start+(index*width+axis)*4):blob.readUInt32LE(start+index*4)};
  };
  const measured=accessor(primitive.attributes.POSITION,3),faces=accessor(primitive.indices,1);
  const originalVertex=index=>[measured.read(index,0)+340150,measured.read(index,1)+2777800,measured.read(index,2)+50];
  const gaps=[[580,1120],[600,1150],[625,1180]];
  for(const pixel of gaps){
    const q=world(...pixel);let covered=false;
    for(let face=0;face<faces.count;face+=3){
      const a=originalVertex(faces.read(face));
      if(Math.abs(a[0]-q[0])>1.3||Math.abs(a[1]-q[1])>1.3||a[2]<70)continue;
      const b=originalVertex(faces.read(face+1)),c=originalVertex(faces.read(face+2));
      if(contains(q,a,b,c)){covered=true;break;}
    }
    assert.equal(covered,false,`pre-existing measured roof is missing at ${pixel}`);
  }
  const r=JSON.parse(await readFile(new URL('roof-repair.json',root),'utf8'));
  const {positions:p,uv,indices:i,metadata:m}=r;
  assert.equal(p.length%3,0);assert.equal(i.length%3,0);assert.equal(uv.length,p.length/3*2);
  assert.ok([...p,...uv].every(Number.isFinite));
  assert.deepEqual(m.origin,[340150,2777800,50]);
  const vertices=Array.from({length:p.length/3},(_,j)=>p.slice(j*3,j*3+3).map((v,k)=>v+m.origin[k]));
  for(let j=0;j<vertices.length;j++){
    assert.ok(Math.abs(uv[j*2]-(vertices[j][0]-339600)/1050)<1e-6);
    assert.ok(Math.abs(uv[j*2+1]-(2778350-vertices[j][1])/1000)<1e-6);
    assert.ok(vertices[j][2]>=m.supportProfile.elevationMin-0.01 && vertices[j][2]<=m.supportProfile.elevationMax+0.05);
  }
  for(let j=0;j<i.length;j+=3){
    const [a,b,c]=i.slice(j,j+3).map(k=>{assert.ok(Number.isInteger(k)&&k>=0&&k<vertices.length);return vertices[k];});
    assert.ok((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])>1e-8,'upward nondegenerate faces');
    assert.ok(!contains(world(650,1110),a,b,c),'courtyard remains open');
  }
  for(const pixel of gaps){
    const q=world(...pixel);assert.ok(i.some((_,j)=>j%3===0&&contains(q,vertices[i[j]],vertices[i[j+1]],vertices[i[j+2]])),`missing roof ${pixel} filled`);
  }
  assert.ok(m.baselineCoverage.missingFraction>.8,'baseline genuinely has missing roof');
  assert.ok(m.supportProfile.pointCount>10000);
  assert.match(m.limits,/estimated|interpolat/i);
});
