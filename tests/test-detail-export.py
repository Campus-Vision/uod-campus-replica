"""Independent raw-record reviews reject prepared subsets and stale provenance."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review', PROJECT/'scripts/audit-detail-export.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
np = review.np


class DetailExportTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        source = root/'original.las'
        source.write_bytes(b'original fixture identity')
        rows = np.zeros(10000, review.dense.DTYPE)
        rows['record'] = np.arange(len(rows))
        rows['xyz'][:, 0] = np.arange(len(rows)) % 100 / 10
        rows['xyz'][:, 1] = 2
        rows['xyz'][:, 2] = np.arange(len(rows)) % 53 - 8
        rows.tofile(root/'tile-0-0.bin')
        manifest = {'source': str(source), 'sourceBytes': source.stat().st_size,
                    'sourceModifiedNs': source.stat().st_mtime_ns,
                    'recordsRead': len(rows), 'header': {'count': len(rows)},
                    'recordsRetained': len(rows), 'recordBytes': review.dense.DTYPE.itemsize,
                    'sampling': 'Every LAS record; no temporal or voxel sampling',
                    'origin': [0, 0, 0], 'boundsLocal': [0, 40, 0, 40, -8, 45],
                    'tileSizeMetres': 40, 'bins': {'tile-0-0.bin': len(rows)}}
        (root/'manifest.json').write_text(json.dumps(manifest))
        return root, source, rows, manifest

    def test_rejects_voxel_or_ambiguous_sampling_before_reading_bins(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _, manifest = self.fixture(directory)
            for change in [{'voxelMetres': .04}, {'parentManifestSHA256': 'parent'},
                           {'sampling': 'One unchanged measured representative per voxel'}]:
                (root/'manifest.json').write_text(json.dumps({**manifest, **change}))
                with self.assertRaisesRegex(ValueError, 'every-record'):
                    review.validate_cache(root)

    def test_rejects_changed_original_size_and_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, _, manifest = self.fixture(directory)
            source.write_bytes(b'changed original')
            with self.assertRaisesRegex(ValueError, 'Original LAS changed'):
                review.validate_cache(root)
            manifest['sourceBytes'] = source.stat().st_size
            manifest['sourceModifiedNs'] = source.stat().st_mtime_ns - 1000000
            (root/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Original LAS changed'):
                review.validate_cache(root)

    def test_exact_bounds_uniform_deterministic_sample_and_all_height_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, rows, _ = self.fixture(directory)
            bounds = [2, 8, 0, 4, -8, 45]
            selected, total, bands = review.sample_region(root, bounds, count=1000)
            repeated, _, _ = review.sample_region(root, bounds, count=1000)
            np.testing.assert_array_equal(selected, repeated)
            self.assertEqual(len(np.unique(selected['record'])), 1000)
            self.assertTrue(np.all((selected['xyz'][:, 0] >= 2) & (selected['xyz'][:, 0] < 8)))
            kept = rows[(rows['xyz'][:, 0] >= 2) & (rows['xyz'][:, 0] < 8)]
            self.assertEqual(total, len(kept))
            self.assertEqual(sum(bands), total)
            self.assertLess(abs(float(np.mean(selected['xyz'][:, 0])) - 4.95), .2)
            all_rows, _, _ = review.sample_region(root, bounds, count=100000)
            np.testing.assert_array_equal(all_rows, kept)

    def test_rejects_truncated_cache_and_outside_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _, _ = self.fixture(directory)
            with self.assertRaisesRegex(ValueError, 'bounds'):
                review.sample_region(root, [-1, 8, 0, 4, -8, 45])
            (root/'tile-0-0.bin').write_bytes(b'incomplete')
            with self.assertRaisesRegex(ValueError, 'bin length'):
                review.validate_cache(root)

    def test_empty_band_metrics_are_null_and_nonfinite_distances_fail(self):
        result = review.metrics(np.empty(0))
        self.assertIsNone(result['p95'])
        self.assertIsNone(result['within5cm'])
        result = review.metrics(np.array([0, .05, .1, .2, .3]))
        self.assertEqual(result['within5cm'], .4)
        self.assertEqual(result['within10cm'], .6)
        self.assertEqual(result['within20cm'], .8)
        with self.assertRaisesRegex(ValueError, 'finite'):
            review.metrics(np.array([np.inf]))

    def test_reads_actual_exported_triangles_and_preserves_all_inputs(self):
        # Small real GLB fixture, independent of existing prepared outputs.
        with tempfile.TemporaryDirectory() as directory:
            root, source, rows, manifest = self.fixture(directory)
            positions = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], '<f4')
            indices = np.array([0, 1, 2], '<u4')
            payload = positions.tobytes() + indices.tobytes()
            document = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
                        'nodes': [{'mesh': 0}], 'meshes': [{'primitives': [
                            {'attributes': {'POSITION': 0}, 'indices': 1}]}],
                        'buffers': [{'byteLength': len(payload)}],
                        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': positions.nbytes},
                                        {'buffer': 0, 'byteOffset': positions.nbytes, 'byteLength': indices.nbytes}],
                        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3,
                                       'type': 'VEC3', 'min': [0, 0, 0], 'max': [10, 10, 0]},
                                      {'bufferView': 1, 'componentType': 5125, 'count': 3, 'type': 'SCALAR'}]}
            header = json.dumps(document).encode()
            header += b' ' * (-len(header) % 4)
            glb = (struct.pack('<III', 0x46546c67, 2, 28+len(header)+len(payload))
                   + struct.pack('<II', len(header), 0x4e4f534a) + header
                   + struct.pack('<II', len(payload), 0x004e4942) + payload)
            prefix = root/'synthetic-textured'
            prefix.with_suffix('.glb').write_bytes(glb)
            prefix.with_suffix('.json').write_text(json.dumps({'origin': manifest['origin'],
                                                             'boundsLocal': [0, 10, 0, 4]}))
            files = [source, root/'manifest.json', root/'tile-0-0.bin',
                     prefix.with_suffix('.glb'), prefix.with_suffix('.json')]
            before = [review.file_identity(path) for path in files]
            distances, triangles, _ = review.mesh_distances(prefix.with_suffix('.glb'),
                                                           np.array([[1, 1, 2], [1, 1, 0]], 'f4'))
            np.testing.assert_allclose(distances, [2, 0], atol=1e-6)
            self.assertEqual(triangles, 1)
            result = review.audit(prefix, root, prefix.with_suffix('.glb'), count=100)
            self.assertEqual(result['sourceRecords'], len(rows))
            self.assertEqual(result['sampledRecords'], 100)
            self.assertEqual(result['exportedGLB']['triangles'], 1)
            self.assertEqual(len(result['localHeightBands']), 5)
            self.assertEqual(result['exportedGLB']['before'], result['exportedGLB']['after'])
            self.assertEqual(result['exportDistanceMetres'], result['baseDistanceMetres'])
            self.assertEqual(before, [review.file_identity(path) for path in files])
            self.assertTrue(prefix.with_name(prefix.name+'-review.json').exists())


if __name__ == '__main__':
    unittest.main()
