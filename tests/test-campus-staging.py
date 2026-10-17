"""Measured volume suppresses duplicate background models, not ground-only data."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('staging',PROJECT/'scripts/prepare-campus-base.py')
staging=importlib.util.module_from_spec(spec);spec.loader.exec_module(staging)
np=staging.np


class StagingTests(unittest.TestCase):
    def test_stale_audit_rejects_staging_before_changing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);mesh=root/'source'
            mesh.with_suffix('.glb').write_bytes(b'original mesh bytes')
            mesh.with_suffix('.json').write_text('{}')
            (root/'source-raw-audit.json').write_text(json.dumps({'meshSHA256':'stale'}))
            with self.assertRaisesRegex(ValueError,'audit does not match'):
                staging.prepare(mesh,root/'unused-cache',root/'output')
            self.assertFalse((root/'output').exists())
            self.assertEqual(mesh.with_suffix('.glb').read_bytes(),b'original mesh bytes')

    def test_ground_only_points_do_not_suppress_background_models(self):
        rng=np.random.default_rng(90);points=np.zeros((600,3))
        points[:,:2]=rng.uniform(-.3,.3,(600,2));points[200:400,2]=4
        points[400:,0]+=10
        original=points.copy()
        excluded=staging.captured_volumes(points,[[0,0,0,2],[10,0,0,2],[30,0,0,2]])
        self.assertEqual([item['treeIndex'] for item in excluded],[0])
        np.testing.assert_array_equal(points,original)


if __name__=='__main__':unittest.main()
