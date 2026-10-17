"""Resume bounded, overlapping measured mesh jobs across the full scan footprint.

Each process exits before the next begins, releasing native reconstruction memory.
This prepares offline detail meshes; it does not silently publish partial trials.
"""
import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('locks',Path(__file__).with_name('preparation-lock.py'))
locks=importlib.util.module_from_spec(spec);spec.loader.exec_module(locks)
exclusive_worker=locks.exclusive_worker


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
    return digest.hexdigest()


def script_hashes():
    return {name:file_hash(ROOT/'campus-replica/scripts'/name)
        for name in ['reconstruct-dense.py','scan-normal-orientation.py','dense-las.py','preparation-lock.py']}


def plan_tiles(manifest,minimum=1000):
    if manifest.get('voxelMetres')!=.04:
        raise ValueError('Fine mesh preparation requires the physical 4cm cache')
    size=manifest['tileSizeMetres'];crop=manifest['boundsLocal'];jobs=[]
    for name,count in sorted(manifest['bins'].items(),key=lambda item:(-item[1],item[0])):
        # Bin keys are emitted by dense-las.py; negative coordinates keep signs.
        match=re.fullmatch(r'tile-(-?\d+)-(-?\d+)\.bin',name)
        if not match:raise ValueError('Unexpected spatial bin name')
        x,y=map(int,match.groups())
        bounds=[max(x*size,crop[0]),min((x+1)*size,crop[1]),
                max(y*size,crop[2]),min((y+1)*size,crop[3])]
        jobs.append({'id':f'cell-{x}-{y}','boundsLocal':bounds,'coreCacheRecords':count,
                     'status':'pending' if count>=minimum else 'insufficient-source'})
    return jobs


def write_progress(path,progress):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(progress,indent=2),encoding='utf-8')
    temporary.replace(path)


def run(cache,output,trajectory,limit=None):
    with exclusive_worker(output):return run_locked(cache,output,trajectory,limit)


def run_locked(cache,output,trajectory,limit=None):
    cache,output,trajectory=Path(cache).resolve(),Path(output).resolve(),Path(trajectory).resolve()
    manifest_path=cache/'manifest.json';manifest=json.loads(manifest_path.read_text())
    identity={'cacheManifestSHA256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'trajectorySHA256':hashlib.sha256(trajectory.read_bytes()).hexdigest(),
              'normalVoxelMetres':.04,'normalRadiusMetres':.24,'poissonDepth':10,
              'haloMetres':2.,'taubinIterations':2,'preparationVersion':1}
    identity['preparationScriptsSHA256']=script_hashes()
    output.mkdir(parents=True,exist_ok=True);checkpoint=output/'progress.json'
    if checkpoint.exists():
        progress=json.loads(checkpoint.read_text())
        if progress['identity']!=identity:raise ValueError('Existing checkpoint has different inputs/settings')
        expected={job['id']:job['boundsLocal'] for job in plan_tiles(manifest)}
        actual={job['id']:job['boundsLocal'] for job in progress['jobs']}
        if expected!=actual:raise ValueError('Checkpoint tile plan differs')
    else:
        progress={'identity':identity,'cache':str(cache),'trajectory':str(trajectory),
                  'status':'preparing','jobs':plan_tiles(manifest),
                  'limits':'Estimated connected local surfaces; missing scan support stays missing. Adjacent tiles require boundary review before browser assembly. No photographic texture approval is implied.'}
    completed=0
    for job in progress['jobs']:
        target=output/job['id']
        if job['status']=='insufficient-source':continue
        if job['status']=='complete':
            metadata=json.loads(target.with_suffix('.json').read_text())
            if (not target.with_suffix('.glb').exists() or
                    target.with_suffix('.glb').stat().st_size!=job['fileBytes'] or
                    file_hash(target.with_suffix('.glb'))!=job['GLBSHA256'] or
                    metadata['inputCacheManifestSHA256']!=identity['cacheManifestSHA256']):
                raise ValueError('Completed tile files/provenance changed; inspect before resuming')
            continue
        if limit is not None and completed>=limit:break
        if script_hashes()!=identity['preparationScriptsSHA256']:
            progress['status']='preparation-changed';write_progress(checkpoint,progress)
            raise ValueError('Preparation scripts changed during the batch')
        job['status']='running';progress['status']='running';write_progress(checkpoint,progress)
        command=[sys.executable,str(ROOT/'campus-replica/scripts/reconstruct-dense.py'),
            '--cache',str(cache),'--output',str(target),'--bounds',*map(str,job['boundsLocal']),
            '--voxel','.04','--depth','10','--normal-radius','.24',
            '--trajectory',str(trajectory),'--no-obj']
        print('Reconstructing',job['id'],job['boundsLocal'],flush=True)
        log_path=target.with_name(target.name+f'-attempt-{time.time_ns()}.log')
        job['lastAttemptLog']=log_path.name
        with log_path.open('w',encoding='utf-8') as log:
            child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            job['childPid']=child.pid;write_progress(checkpoint,progress)
            try:returncode=child.wait()
            except BaseException:
                if child.poll() is None:child.terminate();child.wait()
                raise
        if returncode:
            job['status']='failed';progress['status']='needs-inspection';write_progress(checkpoint,progress)
            raise RuntimeError(f"Reconstruction failed for {job['id']}; inspect its log")
        if script_hashes()!=identity['preparationScriptsSHA256']:
            job['status']='preparation-changed';progress['status']='needs-inspection';write_progress(checkpoint,progress)
            raise ValueError('Preparation scripts changed during a reconstruction; output not accepted')
        metadata=json.loads(target.with_suffix('.json').read_text())
        job.update(status='complete',triangles=metadata['triangles'],vertices=metadata['vertices'],
                   elapsedSeconds=metadata['elapsedSeconds'],fileBytes=target.with_suffix('.glb').stat().st_size,
                   GLBSHA256=file_hash(target.with_suffix('.glb')))
        completed+=1;write_progress(checkpoint,progress)
    progress['status']='complete' if all(job['status'] in ['complete','insufficient-source'] for job in progress['jobs']) else 'prepared-partial'
    write_progress(checkpoint,progress)
    print(json.dumps({'status':progress['status'],'completed':sum(j['status']=='complete' for j in progress['jobs']),
                      'total':len(progress['jobs'])}),flush=True)
    return progress


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=ROOT/'analysis/dense-las-voxel040')
    parser.add_argument('--output',type=Path,default=ROOT/'analysis/campus-fine-meshes')
    parser.add_argument('--trajectory',type=Path,default=ROOT/'@@2026-10-08-081521_REFINE2_Scanner1.PosL')
    parser.add_argument('--limit',type=int,help='Complete at most this many new tiles, preserving resumable progress')
    args=parser.parse_args();run(args.cache,args.output,args.trajectory,args.limit)
