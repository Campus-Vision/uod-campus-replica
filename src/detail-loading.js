// All coordinates share the measured local Z-up frame. This manager owns loaded
// objects until release(), including late results after cancellation/disposal.
export function selectDetailTiles(tiles, eye, target, limit=4) {
  if (eye.distanceTo(target)>130) return [];
  return tiles.map(tile=>{
    const [x0,x1,y0,y1]=tile.boundsLocal;
    const dx=Math.max(x0-target.x,0,target.x-x1),dy=Math.max(y0-target.y,0,target.y-y1);
    const centre=Math.hypot((x0+x1)/2-target.x,(y0+y1)/2-target.y);
    return {tile,distance:Math.hypot(dx,dy),centre};
  }).filter(item=>item.distance<=40)
    .sort((a,b)=>a.distance-b.distance||a.centre-b.centre||a.tile.id.localeCompare(b.tile.id))
    .slice(0,Math.min(limit,4)).map(item=>item.tile);
}

/**
 * load(tile, AbortSignal) resolves to an owned scene object. release(object)
 * disposes its GPU resources. The full-campus base must remain available as
 * fallback: a loaded tile does not establish complete surface coverage.
 * No scene coordinates or camera state are modified by this manager.
 */
export function createDetailManager({tiles,group,load,release,invalidate,onError=()=>{},maxResident=4}) {
  if (!Number.isInteger(maxResident)||maxResident<1||maxResident>4) throw new Error('Invalid detail resident cap');
  const ids=new Set();
  for(const tile of tiles){
    const b=tile.boundsLocal;
    if(ids.has(tile.id)||typeof tile.id!=='string'||!Array.isArray(b)||b.length!==4||
      !b.every(Number.isFinite)||b[1]-b[0]<=2||b[3]-b[2]<=2)throw new Error('Invalid detail tile');
    ids.add(tile.id);
  }
  const entries=new Map();let wanted=[],pending=0,closed=false,clock=0;
  function drop(id){
    const entry=entries.get(id);if(!entry)return;
    entries.delete(id);entry.controller?.abort();
    if(entry.object){group.remove(entry.object);release(entry.object);}
  }
  function refresh(){
    for(const [id,entry] of entries){
      if(!entry.object)continue;
      entry.object.visible=wanted.some(tile=>tile.id===id);
      if(entry.object.visible){
        entry.used=++clock;
      }
    }
    invalidate();
  }
  function pump(){
    if(closed)return;
    while(pending<2){
      const tile=wanted.find(tile=>!entries.has(tile.id));if(!tile)break;
      if(entries.size>=maxResident){
        const inactive=[...entries].filter(([id])=>!wanted.some(tile=>tile.id===id))
          .sort((a,b)=>(a[1].used||0)-(b[1].used||0));
        if(!inactive.length)break;drop(inactive[0][0]);
      }
      const entry={tile,controller:new AbortController(),used:++clock};
      entries.set(tile.id,entry);pending++;
      // Invoke immediately so the caller sees its cancellation signal before
      // update() returns; catch synchronous failures through the same promise.
      let promise;
      try{promise=Promise.resolve(load(tile,entry.controller.signal));}
      catch(error){promise=Promise.reject(error);}
      promise.then(object=>{
        if(closed||entry.controller.signal.aborted||entries.get(tile.id)!==entry){release(object);return;}
        entry.object=object;group.add(object);refresh();
      }).catch(error=>{
        if(!closed&&!entry.controller.signal.aborted&&entries.get(tile.id)===entry){
          entry.failed=true;onError(error,tile);refresh();
        }
      }).finally(()=>{pending--;pump();});
    }
  }
  return {
    update(eye,target,enabled){
      if(closed)return;
      const next=enabled?selectDetailTiles(tiles,eye,target,maxResident):[];
      if(JSON.stringify(next.map(t=>t.id))===JSON.stringify(wanted.map(t=>t.id)))return;
      wanted=next;
      for(const [id,entry] of entries)if(!entry.object&&!wanted.some(tile=>tile.id===id))drop(id);
      refresh();pump();
    },
    retry(){
      if(closed)return;
      for(const [id,entry] of entries)if(entry.failed)drop(id);
      pump();
    },
    visibleIds(){
      return [...entries].filter(([,entry])=>entry.object?.visible).map(([id])=>id);
    },
    dispose(){
      if(closed)return;closed=true;wanted=[];
      for(const id of [...entries.keys()])drop(id);
    },
  };
}
