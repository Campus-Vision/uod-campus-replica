"""Register solved original-flight geometry to the measured LAS frame.

GPS similarity, measured vertical-mode alignment and robust geometric ICP are
reported separately. Geometry registration alone does not approve photo textures:
independent projected-image ties and capture consistency still require checking.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT.parent
sys.path.insert(0,str(ROOT/'analysis/python-packages'))
import numpy as np
import pycolmap
import open3d as o3d
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter1d
from pyproj import Transformer
from PIL import Image

spec=importlib.util.spec_from_file_location('dense',PROJECT/'scripts/dense-las.py')
dense=importlib.util.module_from_spec(spec);spec.loader.exec_module(dense)
spec=importlib.util.spec_from_file_location('photos',PROJECT/'scripts/align-campus-photos.py')
photos=importlib.util.module_from_spec(spec);spec.loader.exec_module(photos)


def apply_similarity(similarity,points):
    return np.asarray(points)@similarity.rotation.matrix().T*similarity.scale+similarity.translation


def summary(values):
    values=np.asarray(values);values=values[np.isfinite(values)]
    if not len(values):raise ValueError('No finite registration observations')
    return {'median':float(np.median(values)),'p95':float(np.quantile(values,.95)),
            'max':float(values.max()),'count':len(values)}


def fit_camera_similarity(source,target,train,max_error=1.):
    source,target=np.asarray(source,float),np.asarray(target,float)
    train=np.asarray(train,bool)
    result=pycolmap.estimate_sim3d_robust(source[train],target[train],
        pycolmap.RANSACOptions(max_error=max_error))
    if result is None:raise ValueError('Could not recover a camera-location similarity')
    # The pinned 4.2.1 runtime returns a result dict despite its stale docstring.
    fitted=result['tgt_from_src']
    error=np.linalg.norm(apply_similarity(fitted,source)-target,axis=1)
    return fitted,{'trainingInliers':int(np.sum(error[train]<=max_error)),
        'training3dMetres':summary(error[train]),'heldout3dMetres':summary(error[~train]),
        'heldoutHorizontalMetres':summary(np.linalg.norm((apply_similarity(fitted,source)-target)[~train,:2],axis=1)),
        'ransacThresholdMetres':max_error}


def vertical_shift(source,target):
    """Modal same-XY height differences; elevated mismatches cannot set the mean."""
    tree=cKDTree(target[:,:2]);distance,nearest=tree.query(source[:,:2],k=min(8,len(target)),workers=6)
    if distance.ndim==1:distance=distance[:,None];nearest=nearest[:,None]
    delta=target[nearest,2]-source[:,None,2]
    valid=(distance<=.25)&(delta>=-60)&(delta<=80)
    values=delta[valid];weight=1/np.maximum(distance[valid],.03)**2
    if len(values)<100:raise ValueError('Insufficient XY overlap for measured vertical alignment')
    edges=np.arange(-60,80.05,.05)
    histogram,_=np.histogram(values,bins=edges,weights=weight)
    peak=int(np.argmax(gaussian_filter1d(histogram.astype(float),2)))
    centre=(edges[peak]+edges[peak+1])/2
    selected=values[np.abs(values-centre)<=.15]
    shift=float(np.median(selected))
    return shift,{'candidateCount':len(values),'peakCandidates':len(selected),
        'maximumHorizontalNeighbourDistanceMetres':.25,'histogramBinMetres':.05,
        'modalHeightShiftMetres':shift,'withinPeakSpreadMetres':summary(np.abs(selected-shift)),
        'limits':'Coarse height mode, not a certified vertical-datum transformation'}


def gps_location(path,origin,transformer):
    with Image.open(path) as image:gps=image.getexif().get_ifd(34853)
    def angle(value):return float(value[0])+float(value[1])/60+float(value[2])/3600
    latitude,longitude=angle(gps[2]),angle(gps[4])
    if gps[1]=='S':latitude=-latitude
    if gps[3]=='W':longitude=-longitude
    easting,northing=transformer.transform(longitude,latitude)
    altitude=float(gps[6]);reference=gps.get(5,0)
    if reference==1 or reference==b'\x01':altitude=-altitude
    return np.array([easting,northing,altitude])-origin


def register(alignment,cache,output):
    alignment,cache,output=Path(alignment),Path(cache),Path(output)
    output.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    progress=json.loads((alignment/'progress.json').read_text())
    source_model=alignment/'sparse'/str(progress['bestModel'])
    if output.resolve()==source_model.resolve():raise ValueError('Registration output must not overwrite the original solve')
    model=pycolmap.Reconstruction(source_model)
    site=json.loads((PROJECT/'public/replica/site.json').read_text());origin=np.array(site['origin'])
    images=sorted(model.images.values(),key=lambda image:image.name)
    centres=np.array([image.projection_center() for image in images])
    transform=Transformer.from_crs('EPSG:4326','EPSG:32640',always_xy=True)
    locations=np.array([gps_location(Path(progress['sourceDirectory'])/image.name,origin,transform) for image in images])
    train=np.arange(len(images))%5!=0
    similarity,gps_metrics=fit_camera_similarity(centres,locations,train)
    print('GPS similarity',json.dumps(gps_metrics),flush=True)
    model.transform(similarity)
    selected=[point for point in model.points3D.values() if point.error<=2 and point.track.length()>=5]
    points=np.array([point.xyz for point in selected])
    colours=np.array([point.color for point in selected],dtype='u1')
    cache_meta=json.loads((cache/'manifest.json').read_text());b=cache_meta['boundsLocal']
    valid=(points[:,0]>=b[0])&(points[:,0]<b[1])&(points[:,1]>=b[2])&(points[:,1]<b[3])
    points,colours=points[valid],colours[valid]
    if len(points)<1000:raise ValueError('Too little sparse geometry overlaps the LAS bounds')
    bounds=[max(float(points[:,0].min())-5,b[0]),min(float(points[:,0].max())+5,b[1]),
            max(float(points[:,1].min())-5,b[2]),min(float(points[:,1].max())+5,b[3])]
    records=dense.load_region(cache,bounds);target=records['xyz'].copy();del records
    # Point IDs are disjoint; neighbouring points/shared image tracks remain
    # correlated. This is internal validation, not independent survey control.
    rng=np.random.default_rng(20261017);order=rng.permutation(len(points))
    holdout=order[::5];training=np.delete(order,np.arange(0,len(order),5))
    height_ids=training[np.linspace(0,len(training)-1,min(len(training),100000),dtype=int)]
    shift,height_metrics=vertical_shift(points[height_ids],target)
    print('Measured vertical shift',json.dumps(height_metrics),flush=True)
    points[:,2]+=shift
    z_transform=pycolmap.Sim3d(1.,pycolmap.Rotation3d(),[0,0,shift]);model.transform(z_transform)
    parent=np.eye(4);parent[:3]=similarity.matrix();parent[2,3]+=shift
    target_tree=cKDTree(target)
    before,_=target_tree.query(points[holdout],workers=6)
    source_cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points[training]))
    target_cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(target.astype(float))).voxel_down_sample(.16)
    target_cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=.45,max_nn=30))
    estimator=o3d.pipelines.registration.TransformationEstimationPointToPlane(o3d.pipelines.registration.TukeyLoss(.12))
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=35,relative_fitness=1e-7,relative_rmse=1e-7)
    print('Refining geometry',len(points),'sparse points and',len(target),'LAS representatives',flush=True)
    coarse=o3d.pipelines.registration.registration_icp(source_cloud,target_cloud,.5,np.eye(4),estimator,criteria)
    predicted=points[training]@coarse.transformation[:3,:3].T+coarse.transformation[:3,3]
    distance,nearest=target_tree.query(predicted,k=12,distance_upper_bound=.22,workers=6)
    ids=np.unique(nearest[np.isfinite(distance)])
    if len(ids)<1000:raise ValueError('Too few supported fine ICP correspondences')
    fine_cloud=o3d.geometry.PointCloud(o3d.utility.Vector3dVector(target[ids].astype(float)))
    fine_cloud.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=.30,max_nn=24))
    fine=o3d.pipelines.registration.registration_icp(source_cloud,fine_cloud,.18,coarse.transformation,estimator,criteria)
    registered=points@fine.transformation[:3,:3].T+fine.transformation[:3,3]
    after,_=target_tree.query(registered[holdout],workers=6)
    if np.median(after)>np.median(before):raise ValueError('ICP worsened heldout sparse-to-LAS median distance')
    model.transform(pycolmap.Sim3d(fine.transformation[:3]));matrix=fine.transformation@parent
    sparse_out=output/'sparse';sparse_out.mkdir(exist_ok=True);model.write(sparse_out)
    photos.export_model(model,output)
    poses=json.loads((output/'solved-poses.json').read_text())
    poses['coordinateFrame']='Local UTM40N metres, Z up; origin [340150,2777800,50]; Z aligned to LAS as supplied'
    poses['origin']=origin.tolist();(output/'solved-poses.json').write_text(json.dumps(poses,indent=2))
    final_centres=np.array([model.image(image.image_id).projection_center() for image in images])
    np.savez(output/'sparse-las.npz',xyz=registered.astype('f4'),rgb=colours)
    report={'sourceModel':str(source_model),'sourceDirectory':progress['sourceDirectory'],
        'registeredImages':len(images),'sparseAuditPoints':len(points),
        'referenceSource':'Original LAS physical 8cm representatives; not independent survey checkpoints',
        'origin':origin.tolist(),'sourceWorldToLocalLAS':matrix.tolist(),'localLASToSourceWorld':np.linalg.inv(matrix).tolist(),
        'gpsSimilarity':gps_metrics,'verticalAlignment':height_metrics,
        'initialHeldoutGeometryMetres':summary(before),'finalHeldoutGeometryMetres':summary(after),
        'heldoutFractionWithin10cm':float(np.mean(after<=.10)),'heldoutFractionWithin20cm':float(np.mean(after<=.20)),
        'finalHeldoutGPSHorizontalMetres':summary(np.linalg.norm((final_centres-locations)[~train,:2],axis=1)),
        'rigidRefinement':fine.transformation.tolist(),'targetCacheSampling':cache_meta['sampling'],
        'acceptedForPhotoTextureBaking':False,
        'registrationStatus':'Provisional: internal geometry residuals and independent image ties have not met an acceptance gate',
        'validationLimits':'Internal disjoint sparse-point holdout; spatial neighbours and shared tracks are correlated. GPS locations are not independent surveyed control.',
        'requiredNextCheck':'Independent projected image ties, visibility and temporal object consistency; broad ground proximity alone cannot certify XY texture registration',
        'elapsedSeconds':round(time.monotonic()-started,2)}
    (output/'registration.json').write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps(report,indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alignment',type=Path,default=ROOT/'analysis/photo-alignment/flight003-wide')
    parser.add_argument('--cache',type=Path,default=ROOT/'analysis/dense-las-voxel080')
    parser.add_argument('--output',type=Path,default=ROOT/'analysis/photo-registration/flight003-wide')
    args=parser.parse_args();register(args.alignment,args.cache,args.output)
