"""The photo-alignment prior must preserve Brown projection, including k3."""
import importlib.util
from pathlib import Path
import sys
import unittest
import json
sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('photos',PROJECT/'scripts/align-campus-photos.py')
photos=importlib.util.module_from_spec(spec);spec.loader.exec_module(photos)
import numpy as np
import cv2


class CalibrationTests(unittest.TestCase):
    def test_exported_intrinsics_roundtrip_as_numeric_json(self):
        camera=photos.pycolmap.Camera(model='OPENCV',width=4032,height=3024,
            params=[2773,2773,2029,1500,.075,-.125,-.0001,.0006])
        data=json.loads(json.dumps(photos.export_camera(camera)))
        self.assertIsInstance(data['params'],list)
        self.assertTrue(all(isinstance(x,(int,float)) for x in data['params']))
        restored=photos.pycolmap.Camera(model=data['model'],width=data['width'],height=data['height'],params=data['params'])
        np.testing.assert_array_equal(restored.params,camera.params)

    def test_full_opencv_matches_brown_projection(self):
        prior={'width':4032,'height':3024,'focal_x':.687,'focal_y':.688,
               'c_x':.003,'c_y':-.003,'k1':.075,'k2':-.125,'k3':.083,
               'p1':-.0001,'p2':.0006}
        params=photos.camera_parameters(prior)
        camera=photos.pycolmap.Camera(model='FULL_OPENCV',width=4032,height=3024,params=params)
        matrix=np.array([[params[0],0,params[2]],[0,params[1],params[3]],[0,0,1]])
        for point in [[0,0,1],[.5,.4,1],[-.45,.35,1]]:
            expected,_=cv2.projectPoints(np.array([point],float),np.zeros(3),np.zeros(3),matrix,
                np.array([prior['k1'],prior['k2'],prior['p1'],prior['p2'],prior['k3']]))
            np.testing.assert_allclose(camera.img_from_cam(np.array(point,float)),expected.reshape(2),atol=1e-8)


if __name__=='__main__':unittest.main()
