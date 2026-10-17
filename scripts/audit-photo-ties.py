"""Measure cross-image feature residuals without fitting away registration error.

A robust homography only rejects descriptor mismatches. Reported residuals use
the original projected LAS locations, never homography-corrected coordinates.
These automatic ties are diagnostic, not surveyed control or texture approval.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis/python-packages'))
import cv2
import numpy as np


def residuals(projected,observed):
    delta=np.asarray(observed)-np.asarray(projected)
    distance=np.linalg.norm(delta,axis=1)
    return {'count':len(distance),'medianPixels':float(np.median(distance)),
            'p95Pixels':float(np.quantile(distance,.95)),
            'medianDeltaPixels':np.median(delta,axis=0).tolist()}


def audit(directory,stem):
    directory=Path(directory)
    las=cv2.imread(str(directory/(stem+'-las.png')))
    photo=cv2.imread(str(directory/(stem+'-photo.jpg')))
    if las is None or photo is None or las.shape!=photo.shape:
        raise ValueError('Matching projection/photo images are required')
    lookup=np.load(directory/(stem+'-lookup.npz'))
    mask=lookup['valid'].astype('u1')*255
    # Keep features away from filled scan boundaries, where descriptors include
    # artificial blank pixels. No exclusion based on measured residuals.
    mask=cv2.erode(mask,np.ones((13,13),'u1'))
    clahe=cv2.createCLAHE(clipLimit=2.,tileGridSize=(12,12))
    detector=cv2.SIFT_create(nfeatures=16000)
    key1,desc1=detector.detectAndCompute(clahe.apply(cv2.cvtColor(las,cv2.COLOR_BGR2GRAY)),mask)
    key2,desc2=detector.detectAndCompute(clahe.apply(cv2.cvtColor(photo,cv2.COLOR_BGR2GRAY)),None)
    if desc1 is None or desc2 is None:raise ValueError('No image descriptors')
    matches=cv2.BFMatcher().knnMatch(desc1,desc2,k=2)
    good=[a for a,b in matches if a.distance<.70*b.distance]
    if len(good)<20:raise ValueError('Too few distinct image ties')
    projected=np.array([key1[m.queryIdx].pt for m in good])
    observed=np.array([key2[m.trainIdx].pt for m in good])
    cv2.setRNGSeed(20261017)
    _,consistent=cv2.findHomography(projected,observed,cv2.RANSAC,3.)
    if consistent is None:raise ValueError('No coherent tie set')
    keep=consistent.ravel().astype(bool)
    sectors=np.floor(projected[keep]/np.array([las.shape[1]/4,las.shape[0]/4])).astype(int)
    report={'image':stem,'descriptorRatio':.70,'ratioMatches':len(good),
            'allRatioMatches':residuals(projected,observed),
            'homographyConsistent':residuals(projected[keep],observed[keep]),
            'occupied4x4Sectors':len(np.unique(sectors,axis=0)),
            'projectionImageScale':float(lookup['scale']),
            'acceptedForPhotoTextureBaking':False,
            'limits':'Automatic cross-modal features, with homography used only for mismatch rejection. Raw residuals retain registration error. Spatially correlated ties and moving objects require independent review; one camera does not certify the flight.'}
    np.savez(directory/(stem+'-ties.npz'),projected=projected,observed=observed,consistent=keep)
    canvas=photo.copy()
    for start,end in zip(projected[keep],observed[keep]):
        a=tuple(np.rint(start).astype(int));b=tuple(np.rint(end).astype(int))
        cv2.line(canvas,a,b,(0,0,255),1);cv2.circle(canvas,a,3,(255,255,0),1)
    cv2.imwrite(str(directory/(stem+'-ties.jpg')),canvas)
    (directory/(stem+'-ties.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=ROOT/'analysis/photo-projection/flight003-wide')
    parser.add_argument('--stem',default='DJI_20261008130911_0011_W')
    args=parser.parse_args();audit(args.directory,args.stem)
