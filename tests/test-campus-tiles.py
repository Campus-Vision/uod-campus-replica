"""Spatial plans retain partial edge bins and disclose unsupported sparse cells."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('tiles',PROJECT/'scripts/reconstruct-campus-tiles.py')
tiles=importlib.util.module_from_spec(spec);spec.loader.exec_module(tiles)


class CampusTileTests(unittest.TestCase):
    def test_duplicate_worker_is_rejected_and_lock_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            with tiles.exclusive_worker(directory):
                with self.assertRaises(RuntimeError):
                    with tiles.exclusive_worker(directory):pass
            with tiles.exclusive_worker(directory):pass

    def test_signed_cells_clip_only_to_measured_crop(self):
        manifest={'voxelMetres':.04,'tileSizeMetres':40,'boundsLocal':[-250,200,-320,60,-8,45],
                  'bins':{'tile--7--8.bin':2000,'tile-4-1.bin':500,'tile--1--1.bin':10000}}
        jobs={job['id']:job for job in tiles.plan_tiles(manifest)}
        self.assertEqual(jobs['cell--7--8']['boundsLocal'],[-250,-240,-320,-280])
        self.assertEqual(jobs['cell-4-1']['boundsLocal'],[160,200,40,60])
        self.assertEqual(jobs['cell--1--1']['boundsLocal'],[-40,0,-40,0])
        self.assertEqual(jobs['cell-4-1']['status'],'insufficient-source')
        self.assertEqual(jobs['cell--1--1']['status'],'pending')
        manifest['voxelMetres']=.08
        with self.assertRaises(ValueError):tiles.plan_tiles(manifest)


if __name__=='__main__':unittest.main()
