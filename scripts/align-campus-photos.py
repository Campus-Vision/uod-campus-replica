"""Solve a single original Wide flight without copying or modifying its images.

Produces camera poses and sparse geometry for subsequent scan registration and
photo texture baking. These poses are NOT yet in the LAS coordinate frame.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis/python-packages'))
import pycolmap

CAPTURES=Path('C:/Users/SamDerTad/Desktop/Flight01_8-10-26/DJI Recordings')
CALIBRATION=Path('C:/Users/SamDerTad/Desktop/CampusVision/Photogrammetry/processed/wide_angle_1/cameras.json')


def export_camera(camera):
    return {'model':camera.model.name,'width':camera.width,'height':camera.height,
            'params':camera.params.tolist()}


def export_model(model,output):
    poses=[]
    for image in model.images.values():
        poses.append({'name':image.name,'cameraId':image.camera_id,
                      'cameraFromWorld':image.cam_from_world().matrix().tolist(),
                      'projectionCenter':image.projection_center().tolist()})
    data={'coordinateFrame':'Unregistered structure-from-motion frame',
          'cameras':{key:export_camera(camera) for key,camera in model.cameras.items()},'poses':poses}
    (Path(output)/'solved-poses.json').write_text(json.dumps(data,indent=2))


def camera_parameters(calibration):
    """OpenSfM Brown normalised intrinsics -> COLMAP FULL_OPENCV pixels."""
    width,height=calibration['width'],calibration['height'];scale=max(width,height)
    return [calibration['focal_x']*scale,calibration['focal_y']*scale,
            width/2+calibration['c_x']*scale,height/2+calibration['c_y']*scale,
            calibration['k1'],calibration['k2'],calibration['p1'],calibration['p2'],
            calibration['k3'],0.,0.,0.]


def align(images,output):
    images,output=Path(images),Path(output);output.mkdir(parents=True,exist_ok=True)
    names=sorted(p.name for p in images.glob('*_W.JPG'))
    if len(names)<20:raise ValueError('Expected one overlapping Wide flight, not mixed camera modes')
    inputs=[{'name':name,'bytes':(images/name).stat().st_size,
             'modifiedNs':(images/name).stat().st_mtime_ns} for name in names]
    calibration=next(iter(json.loads(CALIBRATION.read_text()).values()))
    parameters=camera_parameters(calibration)
    database=output/'database.db';started=time.monotonic()
    status={'sourceDirectory':str(images),'inputImages':len(names),'images':inputs,
            'processor':'pycolmap '+pycolmap.__version__,'coordinateFrame':'Unregistered structure-from-motion frame',
            'cameraPrior':'Optimised Brown calibration from existing eastern Wide processing; same camera/dimensions',
            'limits':'Camera poses require independent registration to LAS before texture projection. Nadir photography does not establish unseen facade coverage.'}
    def progress(stage):
        status.update(stage=stage,elapsedSeconds=round(time.monotonic()-started,1))
        (output/'progress.json').write_text(json.dumps(status,indent=2));print(stage,flush=True)
    reader=pycolmap.ImageReaderOptions(camera_model='FULL_OPENCV',camera_params=','.join(map(str,parameters)))
    extraction=pycolmap.FeatureExtractionOptions(num_threads=6,max_image_size=2400,use_gpu=False)
    extraction.sift.max_num_features=10000
    matching=pycolmap.FeatureMatchingOptions(num_threads=6,use_gpu=False)
    pairing=pycolmap.SequentialPairingOptions(overlap=12,quadratic_overlap=True,num_threads=6)
    options=pycolmap.IncrementalPipelineOptions(num_threads=6,random_seed=20261017,
        ba_refine_extra_params=False,ba_refine_focal_length=True,
        max_num_models=5,extract_colors=True)
    # Match registration-time refinement to the shared distortion prior.
    options.mapper.abs_pose_refine_extra_params=False
    try:
        progress('extracting-features')
        pycolmap.extract_features(database,images,image_names=names,camera_mode=pycolmap.CameraMode.SINGLE,
            reader_options=reader,extraction_options=extraction,device=pycolmap.Device.cpu)
        progress('matching-overlapping-images')
        pycolmap.match_sequential(database,matching_options=matching,pairing_options=pairing,device=pycolmap.Device.cpu)
        sparse=output/'sparse';sparse.mkdir(exist_ok=True)
        progress('solving-camera-poses')
        models=pycolmap.incremental_mapping(database,images,sparse,options=options)
        if not models:raise ValueError('No connected camera reconstruction was recovered')
        status['models']=[{'id':key,'registeredImages':model.num_reg_images(),
            'points3D':model.num_points3D(),'meanReprojectionErrorPixels':model.compute_mean_reprojection_error()}
            for key,model in models.items()]
        best=max(models,key=lambda key:models[key].num_reg_images());model=models[best]
        status['bestModel']=best
        export_model(model,output)
        status['sourceFilesUnchanged']=all((images/i['name']).stat().st_size==i['bytes'] and
            (images/i['name']).stat().st_mtime_ns==i['modifiedNs'] for i in inputs)
        if not status['sourceFilesUnchanged']:raise ValueError('Original image metadata changed during processing')
        progress('poses-solved-awaiting-LAS-registration')
    except Exception as error:
        status['error']=str(error);progress('failed');raise
    return status


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images',type=Path,default=CAPTURES/'DJI_202610081303_003_Day-ntrip-ironred-test1')
    p.add_argument('--output',type=Path,default=ROOT/'analysis/photo-alignment/flight003-wide')
    p.add_argument('--export-only',type=Path,help='Existing COLMAP sparse model; rewrite numeric pose JSON without reprocessing')
    args=p.parse_args()
    if args.export_only:export_model(pycolmap.Reconstruction(args.export_only),args.output)
    else:align(args.images,args.output)
