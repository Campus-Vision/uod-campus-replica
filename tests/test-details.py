"""Focused source-fidelity and unsupported-gap checks for local scan patches."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('details', PROJECT / 'scripts/prepare-details.py')
details = importlib.util.module_from_spec(spec)
spec.loader.exec_module(details)
np = details.np


class DetailTests(unittest.TestCase):
    def test_normal_estimation_retains_plane_and_rejects_isolated_returns(self):
        x, y = np.meshgrid(np.arange(9)*.055, np.arange(9)*.055)
        plane = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 2)))
        cloud = np.vstack((plane, [[20, 20, 20], [21, 20, 20]]))
        accepted, normals, radii, _ = details.patches(cloud)
        self.assertGreater(len(accepted), 50)
        self.assertTrue((accepted < len(plane)).all())
        np.testing.assert_allclose(normals[:, 2], 1, atol=1e-6)
        self.assertTrue((radii <= .12).all())

    def test_collinear_returns_cannot_define_a_surface(self):
        cloud = np.column_stack((np.arange(30)*.02, np.zeros(30), np.zeros(30)))
        self.assertEqual(len(details.patches(cloud)[0]), 0)

    def test_shipping_buffers_are_finite_bounded_and_contiguous(self):
        out = PROJECT / 'public/replica'
        meta = json.loads((out / 'details.json').read_text())
        count = meta['count']
        positions = np.fromfile(out / meta['positions'], '<f4').reshape(-1, 3)
        colors = np.fromfile(out / meta['colors'], 'uint8').reshape(-1, 3)
        normals = np.fromfile(out / meta['normals'], '<f4').reshape(-1, 3)
        radii = np.fromfile(out / meta['radii'], '<f4')
        for array in [positions, colors, normals, radii]:
            self.assertEqual(len(array), count)
            self.assertTrue(np.isfinite(array).all())
        np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-6)
        self.assertGreaterEqual(float(radii.min()), .034999)
        self.assertLessEqual(float(radii.max()), .120001)
        start = 0
        audit = []
        for region in meta['metadata']['regions']:
            self.assertEqual(region['start'], start)
            end = start + region['count']
            bounds = region['boundsLocal']
            self.assertTrue((positions[start:end] >= np.array(bounds['min'])-1e-5).all())
            self.assertTrue((positions[start:end] <= np.array(bounds['max'])+1e-5).all())
            local = positions[start:end].astype('float64')
            self.assertTrue(details.inside_polygon(
                np.column_stack(((local[:, 0]+340150-339750)/900*1497,
                                 (2778350.09765625-local[:, 1]-2777800)/1000.1953125*1664)),
                region['referencePixelPolygon']).all())
            audit.extend(np.linspace(start, end-1, 128, dtype=int))
            start = end
        self.assertEqual(start, count)
        # Independent nearest-source audit proves the renderer receives actual
        # source positions/colours rather than smoothed centres or averaged RGB.
        source = np.fromfile(out / 'building.positions.bin', '<f4').reshape(-1, 3)
        source_colors = np.fromfile(out / 'building.colors.bin', 'uint8').reshape(-1, 3)
        distance, nearest = details.cKDTree(source).query(positions[audit], workers=8)
        np.testing.assert_array_equal(distance, 0)
        np.testing.assert_array_equal(source_colors[nearest], colors[audit])


if __name__ == '__main__':
    unittest.main()
