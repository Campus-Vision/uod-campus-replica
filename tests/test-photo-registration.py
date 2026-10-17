"""Coordinate and robust-registration checks independent of the real capture."""
import importlib.util
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('registration',PROJECT/'scripts/register-campus-photos.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np=module.np
spec=importlib.util.spec_from_file_location('projection',PROJECT/'scripts/check-photo-projection.py')
projection=importlib.util.module_from_spec(spec);spec.loader.exec_module(projection)
spec=importlib.util.spec_from_file_location('ties',PROJECT/'scripts/audit-photo-ties.py')
ties=importlib.util.module_from_spec(spec);spec.loader.exec_module(ties)


class RegistrationTests(unittest.TestCase):
    def test_zbuffer_preserves_nearest_actual_return_at_colliding_pixels(self):
        selected=projection.closest_per_pixel(np.array([5,2,5,2]),np.array([8.,9.,3.,4.]))
        np.testing.assert_array_equal(selected,[3,2])

    def test_resized_projection_agrees_with_colmap_distorted_camera(self):
        params=np.array([2781.,2784.,2029.,1500.,.07,-.12,-.0001,.0006,.08,0,0,0])
        camera=module.pycolmap.Camera(model='FULL_OPENCV',width=4032,height=3024,params=params)
        points=np.array([[.1,.2,1.],[-.4,.3,1.],[.3,-.4,1.]])
        k=projection.resized_intrinsics(params,.5)
        actual,_=projection.cv2.projectPoints(points,np.zeros(3),np.zeros(3),k,params[4:])
        expected=np.array([camera.img_from_cam(point) for point in points])*.5-.5
        np.testing.assert_allclose(actual.reshape(-1,2),expected,atol=1e-10)

    def test_tie_residuals_retain_systematic_misalignment(self):
        points=np.array([[0.,0.],[10.,0.],[0.,10.]])
        metrics=ties.residuals(points,points+[3,4])
        self.assertEqual(metrics['medianPixels'],5.)
        self.assertEqual(metrics['medianDeltaPixels'],[3.,4.])

    def test_similarity_handles_outlier_camera_locations_and_preserves_projection(self):
        rng=np.random.default_rng(31);source=rng.normal(size=(100,3))
        truth=module.pycolmap.Sim3d(17.,module.pycolmap.Rotation3d(np.array([0,0,.2])),[31,-22,9])
        expected=module.apply_similarity(truth,source)
        targets=expected+rng.normal(0,.003,expected.shape);targets[::7]+=20
        mask=np.arange(len(source))%5!=0
        fitted,metrics=module.fit_camera_similarity(source,targets,mask,max_error=.1)
        np.testing.assert_allclose(module.apply_similarity(fitted,source),expected,atol=.006)
        self.assertGreater(metrics['trainingInliers'],60)
        camera=module.pycolmap.Rigid3d(module.pycolmap.Rotation3d(),[0,0,5])
        transformed=fitted.transform_camera_world(camera)
        point=np.array([.1,.2,1.])
        before=camera*point;after=transformed*module.apply_similarity(fitted,point[None])[0]
        np.testing.assert_allclose(after/after[2],before/before[2],atol=1e-10)

    def test_vertical_modal_alignment_ignores_unmatched_elevated_objects(self):
        rng=np.random.default_rng(91)
        xy=rng.uniform(-50,50,(2000,2));ground=.01*xy[:,0]+.02*xy[:,1]
        target=np.column_stack([xy,ground]);photo=target.copy();photo[:,2]-=24.75
        photo[::5,2]+=8
        shift,metrics=module.vertical_shift(photo,target)
        self.assertAlmostEqual(shift,24.75,places=2)
        self.assertGreater(metrics['peakCandidates'],1000)


if __name__=='__main__':unittest.main()
