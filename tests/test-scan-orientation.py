"""Timestamp and physical-viewpoint normal orientation regression checks."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('orientation',PROJECT/'scripts/scan-normal-orientation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np=module.np


class ScanOrientationTests(unittest.TestCase):
    def test_interpolation_uses_site_origin_and_rejects_extrapolation(self):
        track=np.array([[100,340150,2777800,52],[102,340152,2777804,54]],float)
        sensors=module.interpolate_sensors([100,101,102],track,[340150,2777800,50])
        np.testing.assert_allclose(sensors,[[0,0,2],[1,2,3],[2,4,4]])
        with self.assertRaises(ValueError):module.interpolate_sensors([99],track,[0,0,0])

    def test_record_ids_preserve_timestamp_order_across_read_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.las';header=bytearray(227)
            header[:4]=b'LASF';header[24:26]=bytes([1,2]);header[104]=3
            struct.pack_into('<I',header,96,227);struct.pack_into('<H',header,105,34)
            struct.pack_into('<I',header,107,5);struct.pack_into('<3d',header,131,.001,.001,.001)
            records=bytearray(34*5)
            for i in range(5):struct.pack_into('<d',records,i*34+20,100+i*.1)
            original=bytes(header+records);path.write_bytes(original)
            times=module.record_times(path,[4,0,2,2],chunk_size=2)
            np.testing.assert_allclose(times,[100.4,100,100.2,100.2])
            self.assertEqual(path.read_bytes(),original)
            trajectory=Path(directory)/'track.PosL'
            trajectory.write_text('time lat lon h roll pitch heading east north height\n'
                '101 0 0 2 0 0 0 0 0 2\n100 0 0 2 0 0 0 0 0 2\n')
            normals=np.array([[0,0,-1.],[0,0,1.]])
            report=module.orient(np.zeros((2,3)),normals,path,[4,0],trajectory,[0,0,0])
            np.testing.assert_array_equal(normals,[[0,0,1],[0,0,1]])
            self.assertEqual(report['flippedNormals'],1)
            self.assertEqual(report['trajectoryRowsReorderedByTimestamp'],2)


if __name__=='__main__':unittest.main()
