"""Stage independently audited local meshes without replacing the campus base."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]


def file_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare(paths,output):
    output=Path(output)
    prepared=[]
    # Validate the entire batch before publishing any references.
    for path in map(Path,paths):
        metadata=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        review_path=path.with_name(path.name+'-review').with_suffix('.json')
        review=json.loads(review_path.read_text(encoding='utf-8'))
        asset_hash=file_hash(path.with_suffix('.glb'))
        if review['metadataSHA256']!=file_hash(path.with_suffix('.json')):raise ValueError('Detail metadata changed after audit')
        base=json.loads((output/'campus-surface.json').read_text(encoding='utf-8'))
        if review['baseGLB']['after']['sha256']!=base['assetSHA256']:raise ValueError('Detail audit references another campus base')
        if review['sourceManifestSHA256']!=file_hash(ROOT/'analysis/dense-las/manifest.json'):raise ValueError('Detail raw cache identity changed')
        original=review['originalLASIdentity']['after'];stat=Path(original['path']).stat()
        if stat.st_size!=original['bytes'] or stat.st_mtime_ns!=original['modifiedNs']:raise ValueError('Original LAS changed after detail audit')
        if review['exportedGLB']['after']['sha256']!=asset_hash:raise ValueError('Detail audit does not match exported bytes')
        if review['metadataBoundsLocal']!=metadata['boundsLocal'] or review['origin']!=metadata['origin']:
            raise ValueError('Detail audit frame differs from export metadata')
        if review['exportedGLB']['triangles']!=metadata['triangles']:raise ValueError('Detail triangle count mismatch')
        if review['exportDistanceMetres']['within10cm']<.95:raise ValueError('Detail raw agreement is below95% within10cm')
        if review['exportDistanceMetres']['within10cm']<review['baseDistanceMetres']['within10cm']:
            raise ValueError('Detail has less raw coverage than the campus base in this region')
        if metadata['origin']!=[340150.,2777800.,50.]:raise ValueError('Unexpected local frame')
        tile_id=path.name
        if not tile_id.replace('-','').isalnum():raise ValueError('Unsafe asset identifier')
        prepared.append((path,review_path,metadata,review,asset_hash,tile_id))
    if len({item[-1] for item in prepared})!=len(prepared):raise ValueError('Duplicate detail identifier')
    output.mkdir(parents=True,exist_ok=True)
    tiles=[]
    for path,review_path,metadata,review,asset_hash,tile_id in prepared:
        asset='detail-'+tile_id+'.glb'
        shutil.copyfile(path.with_suffix('.glb'),output/asset)
        if file_hash(output/asset)!=asset_hash:raise ValueError('Staged detail checksum mismatch')
        provenance='detail-'+tile_id+'-provenance.json'
        audit='detail-'+tile_id+'-review.json'
        shutil.copyfile(path.with_suffix('.json'),output/provenance)
        shutil.copyfile(review_path,output/audit)
        tiles.append({'id':tile_id,'asset':asset,'assetSHA256':asset_hash,
                      'boundsLocal':metadata['boundsLocal'],'triangles':metadata['triangles'],
                      'bytes':path.with_suffix('.glb').stat().st_size,
                      'provenance':provenance,'review':audit})
    manifest={'version':1,'origin':[340150.,2777800.,50.],'tiles':tiles,
              'baseCoverage':'Full campus base retained, including through all detail holes',
              'maximumViewDepthPreferenceMetres':.08,'edgeRampMetres':1.,
              'limits':'Selected local refinements only; remaining campus uses the measured base. Scan RGB atlases are not registered photograph textures. Depth preference changes visibility within8cm; exact source coordinates remain unchanged. Independent tiles are not topologically stitched.'}
    (output/'mesh-details.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'stagedTiles':len(tiles),'totalBytes':sum(t['bytes'] for t in tiles)},indent=2),flush=True)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh',type=Path,nargs='+')
    parser.add_argument('--output',type=Path,default=ROOT/'campus-replica/public/replica')
    args=parser.parse_args();prepare(args.mesh,args.output)
