"""Check chunked LAS extraction using real binary records, including tile seams."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT.parent / 'analysis/python-packages'))
import numpy as np

spec = importlib.util.spec_from_file_location('dense', PROJECT/'scripts/dense-las.py')
dense = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dense)


class DenseLasTests(unittest.TestCase):
    @unittest.skipUnless((PROJECT.parent/'analysis/dense-las/manifest.json').exists(), 'Dense source cache not generated')
    def test_full_scan_cache_record_provenance(self):
        directory=PROJECT.parent/'analysis/dense-las'
        meta=json.loads((directory/'manifest.json').read_text())
        self.assertEqual(meta['recordsRead'],200700295)
        self.assertEqual(sum(meta['bins'].values()),meta['recordsRetained'])
        source=Path(meta['source'])
        self.assertEqual(source.stat().st_mtime_ns,meta['sourceModifiedNs'])
        header=dense.read_header(source)
        with source.open('rb') as las:
            for name,count in meta['bins'].items():
                self.assertEqual((directory/name).stat().st_size,count*dense.DTYPE.itemsize)
                data=np.memmap(directory/name,dtype=dense.DTYPE,mode='r')
                for i in np.linspace(0,count-1,min(count,8),dtype=int):
                    row=data[i]; las.seek(header['offset']+int(row['record'])*header['stride'])
                    record=las.read(header['stride'])
                    xyz=np.array(struct.unpack_from('<3i',record))*header['scale']+header['offsetXYZ']-meta['origin']
                    np.testing.assert_allclose(row['xyz'],xyz,atol=.00002,rtol=0)
                    rgb=np.array(struct.unpack_from('<3H',record,28))
                    np.testing.assert_array_equal(row['rgb'],np.where(rgb<=255,rgb,np.rint(rgb/257)).astype('u1'))

    def test_every_record_and_overlap_recover_original_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            header = bytearray(227)
            header[:4] = b'LASF'
            header[24:26] = bytes([1, 2])
            struct.pack_into('<H', header, 94, 227)
            struct.pack_into('<I', header, 96, 227)
            header[104] = 3
            struct.pack_into('<H', header, 105, 34)
            struct.pack_into('<I', header, 107, 5)
            struct.pack_into('<3d', header, 131, .001, .001, .001)
            struct.pack_into('<3d', header, 155, 340150., 2777800., 50.)
            rows = [(0,0,1000), (9990,0,2000), (10010,0,3000),
                    (11000,0,4000), (30000,0,5000)]
            records = bytearray()
            for i, xyz in enumerate(rows):
                record = bytearray(34)
                struct.pack_into('<3i', record, 0, *xyz)
                struct.pack_into('<3H', record, 28, 257*(i+1), 0, 65535)
                records.extend(record)
            path = root/'input.las'; path.write_bytes(header+records)
            original = path.read_bytes()
            meta = dense.extract(path, root/'cache', [340150,2777800,50],
                                 [-1,21,-1,1,0,10], tile_size=10, chunk_size=2)
            self.assertEqual(meta['recordsRead'], 5)
            self.assertEqual(meta['recordsRetained'], 4)
            self.assertEqual(path.read_bytes(), original)
            a = dense.load_region(root/'cache', [-1,10,-1,1], halo=.02)
            self.assertEqual(sorted(a['record'].tolist()), [0,1,2])
            for row in a:
                i = int(row['record'])
                np.testing.assert_allclose(row['xyz'], np.array(rows[i])*.001, atol=1e-6)
                np.testing.assert_array_equal(row['rgb'], [i+1,0,255])
            manifest = json.loads((root/'cache/manifest.json').read_text())
            self.assertEqual(manifest['sampling'], 'Every LAS record; no temporal or voxel sampling')

    def test_reject_compressed_or_truncated_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'bad.las'; path.write_bytes(b'LASF'+bytes(223))
            with self.assertRaises(ValueError): dense.read_header(path)


if __name__ == '__main__': unittest.main()
