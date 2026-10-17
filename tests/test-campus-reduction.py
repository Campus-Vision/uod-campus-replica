"""Independent geometric checks for the browser base, retaining its dense parent."""
import importlib.util
import json
from pathlib import Path
import unittest

PROJECT=Path(__file__).resolve().parents[1];ROOT=PROJECT.parent
spec=importlib.util.spec_from_file_location('reduction',PROJECT/'scripts/reduce-campus-base.py')
reduction=importlib.util.module_from_spec(spec);spec.loader.exec_module(reduction)
np,o3d=reduction.np,reduction.o3d


class CampusReductionTests(unittest.TestCase):
    def test_parent_overwrite_is_rejected_before_io(self):
        with self.assertRaises(ValueError):
            reduction.reduce(Path('preserve-this-parent'),Path('preserve-this-parent'),Path('unused'))

    @unittest.skipUnless((ROOT/'analysis/dense-reconstruction/campus-base-browser-v2.glb').exists(),
                         'Higher-detail browser base not generated')
    def test_actual_reduced_triangle_interiors_remain_near_parent(self):
        root=ROOT/'analysis/dense-reconstruction'
        metadata=json.loads((root/'campus-base-browser-v2.json').read_text())
        mesh=o3d.io.read_triangle_mesh(str(root/'campus-base-browser-v2.glb'))
        vertices=np.asarray(mesh.vertices);faces=np.asarray(mesh.triangles)
        self.assertEqual(len(faces),metadata['triangles'])
        self.assertTrue(np.isfinite(vertices).all())
        self.assertGreater(len(faces),0)
        rng=np.random.default_rng(46);chosen=rng.integers(len(faces),size=20000)
        weights=rng.dirichlet([1,1,1],size=len(chosen))
        samples=np.einsum('ij,ijk->ik',weights,vertices[faces[chosen]])
        parent=o3d.io.read_triangle_mesh(str(root/'campus-base-trajectory.glb'))
        scene=o3d.t.geometry.RaycastingScene()
        scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(parent));del parent
        distance=scene.compute_distance(o3d.core.Tensor(samples.astype('f4'))).numpy()
        self.assertLessEqual(float(distance.max()),.06502)
        self.assertEqual(metadata['reduction']['simplifier'],'fast-simplification 0.2.0')


if __name__=='__main__':unittest.main()
