"""Orient measured normals toward the scanner that observed each LAS record.

Uses original LAS format-3 time fields and the supplied PosL trajectory without
changing either input. Times must already share the same numerical time base.
"""
import hashlib
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT.parent/'analysis/python-packages'))
import numpy as np
spec=importlib.util.spec_from_file_location('dense',PROJECT/'scripts/dense-las.py')
dense=importlib.util.module_from_spec(spec);spec.loader.exec_module(dense)


def record_times(source,record_ids,chunk_size=500000):
    """Bounded sequential I/O, even when representatives are spatially ordered."""
    source=Path(source);header=dense.read_header(source)
    ids=np.asarray(record_ids,dtype='i8')
    if not len(ids) or ids.min()<0 or ids.max()>=header['count']:
        raise ValueError('Invalid original LAS record IDs')
    order=np.argsort(ids);sorted_ids=ids[order];result=np.empty(len(ids),'f8')
    dtype=np.dtype({'names':['gps'],'formats':['<f8'],'offsets':[20],'itemsize':header['stride']})
    with source.open('rb') as stream:
        for start in range(0,header['count'],chunk_size):
            stop=min(start+chunk_size,header['count'])
            begin,end=np.searchsorted(sorted_ids,[start,stop])
            if begin==end:continue
            stream.seek(header['offset']+start*header['stride'])
            data=stream.read((stop-start)*header['stride'])
            if len(data)!=(stop-start)*header['stride']:raise ValueError('Truncated LAS source')
            rows=np.frombuffer(data,dtype=dtype)
            result[order[begin:end]]=rows['gps'][sorted_ids[begin:end]-start]
    return result


def interpolate_sensors(times,trajectory,origin):
    trajectory=np.asarray(trajectory,float);times=np.asarray(times,float)
    if trajectory.ndim!=2 or trajectory.shape[1]!=4 or not np.isfinite(trajectory).all():
        raise ValueError('Trajectory requires finite [time,easting,northing,height] rows')
    if np.any(np.diff(trajectory[:,0])<=0):raise ValueError('Trajectory times must strictly increase')
    if not np.isfinite(times).all() or times.min()<trajectory[0,0] or times.max()>trajectory[-1,0]:
        raise ValueError('LAS times are outside the PosL time span; no time-base conversion is assumed')
    return np.column_stack([np.interp(times,trajectory[:,0],trajectory[:,i])-origin[i-1] for i in range(1,4)])


def orient(points,normals,source,record_ids,trajectory_path,origin):
    path=Path(trajectory_path)
    trajectory=np.loadtxt(path,skiprows=1,usecols=(0,7,8,9))
    order=np.argsort(trajectory[:,0],kind='stable')
    reordered=int(np.count_nonzero(order!=np.arange(len(order))))
    trajectory=trajectory[order]
    times=record_times(source,record_ids)
    sensors=interpolate_sensors(times,trajectory,origin)
    toward=sensors-np.asarray(points)
    normals=np.asarray(normals)
    flip=np.einsum('ij,ij->i',normals,toward)<0
    normals[flip]*=-1
    ranges=np.linalg.norm(toward,axis=1)
    return {'method':'PCA normals oriented toward interpolated scanner position for each original measured record',
            'trajectory':path.name,'trajectorySHA256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'trajectoryRows':len(trajectory),'pointTimes':[float(times.min()),float(times.max())],
            'trajectoryRowsReorderedByTimestamp':reordered,
            'trajectoryTimes':[float(trajectory[0,0]),float(trajectory[-1,0])],
            'flippedNormals':int(flip.sum()),'scannerRangeMedianMetres':float(np.median(ranges)),
            'scannerRangeP95Metres':float(np.quantile(ranges,.95)),
            'limits':'Visibility-derived sign of estimated PCA normals; not proof of a watertight surface. Original numerical time bases must match.'}
