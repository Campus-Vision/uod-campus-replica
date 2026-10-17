"""Render original LAS RGB into a solved photo camera for independent tie checks.

Outputs a measured-point image and XYZ lookup, never a guessed building texture.
Pixel centres follow COLMAP (+0.5) -> resized OpenCV (0-based) conventions.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT.parent
sys.path.insert(0,str(ROOT/'analysis/python-packages'))
import numpy as np
import cv2
from scipy.ndimage import distance_transform_edt
from PIL import Image
spec=importlib.util.spec_from_file_location('dense',PROJECT/'scripts/dense-las.py')
dense=importlib.util.module_from_spec(spec);spec.loader.exec_module(dense)


def resized_intrinsics(params,scale):
    """COLMAP half-pixel centres to OpenCV resized zero-based centres."""
    return np.array([[params[0]*scale,0,params[2]*scale-.5],
                     [0,params[1]*scale,params[3]*scale-.5],[0,0,1.]])


def closest_per_pixel(pixels,depths):
    order=np.lexsort((depths,pixels))
    return order[np.r_[True,np.diff(pixels[order])!=0]]


def render(registration,image_name,output,cache,size=2016):
    registration,output,cache=Path(registration),Path(output),Path(cache)
    output.mkdir(parents=True,exist_ok=True)
    poses=json.loads((registration/'solved-poses.json').read_text())
    pose=next(p for p in poses['poses'] if p['name']==image_name)
    camera=poses['cameras'][str(pose['cameraId'])]
    matrix=np.array(pose['cameraFromWorld']);rotation=matrix[:,:3];translation=matrix[:,3]
    centre=-rotation.T@translation
    metadata=json.loads((registration/'registration.json').read_text())
    photo=Image.open(Path(metadata['sourceDirectory'])/image_name).convert('RGB')
    scale=size/photo.width;height=round(photo.height*scale)
    photo=photo.resize((size,height),Image.Resampling.LANCZOS)
    if camera['model']!='FULL_OPENCV':raise ValueError('Only calibrated FULL_OPENCV cameras are supported')
    intrinsics=np.array(camera['params']);k=resized_intrinsics(intrinsics,scale)
    # A 110m radius includes the image footprint at the recorded ~60m height.
    records=dense.load_region(cache,[centre[0]-110,centre[0]+110,centre[1]-110,centre[1]+110])
    xyz=records['xyz'];rgb=records['rgb'];cam=xyz@rotation.T+translation
    front=(cam[:,2]>1)&(np.abs(cam[:,0]/np.maximum(cam[:,2],1))<2)&(np.abs(cam[:,1]/np.maximum(cam[:,2],1))<2)
    ids=np.flatnonzero(front)
    uv,_=cv2.projectPoints(cam[ids].astype('f8'),np.zeros(3),np.zeros(3),k,intrinsics[4:])
    uv=np.rint(uv.reshape(-1,2)).astype('i4')
    inside=(uv[:,0]>=0)&(uv[:,0]<size)&(uv[:,1]>=0)&(uv[:,1]<height)
    ids=ids[inside];uv=uv[inside];pixels=uv[:,1].astype('i8')*size+uv[:,0]
    selected=closest_per_pixel(pixels,cam[ids,2])
    pixel=pixels[selected];chosen=ids[selected]
    valid=np.zeros(size*height,bool);valid[pixel]=True;valid=valid.reshape(height,size)
    colours=np.zeros((size*height,3),'u1');colours[pixel]=rgb[chosen]
    lookup=np.zeros((size*height,3),'f4');lookup[pixel]=xyz[chosen]
    distance,nearest=distance_transform_edt(~valid,return_indices=True)
    fill=distance<=2.25;flat=nearest[0]*size+nearest[1]
    colours=colours[flat];lookup=lookup[flat]
    colours[~fill]=[225,225,225];lookup[~fill]=np.nan
    stem=Path(image_name).stem
    Image.fromarray(colours).save(output/(stem+'-las.png'))
    photo.save(output/(stem+'-photo.jpg'),quality=96)
    combined=(np.array(photo).astype(float)*.5+colours.astype(float)*.5).astype('u1')
    Image.fromarray(combined).save(output/(stem+'-overlay.jpg'),quality=96)
    np.savez(output/(stem+'-lookup.npz'),xyz=lookup,valid=fill,observed=valid,
             fillDistancePixels=distance,
             intrinsics=k,distortion=intrinsics[4:],worldToCamera=matrix,scale=scale)
    report={'image':image_name,'cameraCentreLocal':centre.tolist(),'scale':scale,
            'LASRecordsConsidered':len(records),'projectedRecords':len(ids),
            'coveredPixels':int(fill.sum()),'coverageFraction':float(fill.mean()),
            'limits':'Point-splat diagnostic. Missing scan coverage remains blank; nearest-point lookup can differ from a precise image feature by several centimetres.'}
    (output/(stem+'-projection.json')).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registration',type=Path,default=ROOT/'analysis/photo-registration/flight003-wide')
    p.add_argument('--cache',type=Path,default=ROOT/'analysis/dense-las-voxel040')
    p.add_argument('--image',default='DJI_20261008130911_0011_W.JPG')
    p.add_argument('--output',type=Path,default=ROOT/'analysis/photo-projection/flight003-wide')
    args=p.parse_args();render(args.registration,args.image,args.output,args.cache)
