"""Full-record audit sampling must not overweight small spatial bins."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit',PROJECT/'scripts/audit-campus-mesh.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
np=audit.np


class CampusAuditTests(unittest.TestCase):
    def test_uniform_source_sampling_and_all_record_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rows=np.zeros(10000,audit.module.dense.DTYPE)
            rows['record']=np.arange(len(rows));rows['xyz'][:,0]=np.arange(len(rows))
            rows[:100].tofile(root/'small.bin');rows[100:].tofile(root/'large.bin')
            (root/'manifest.json').write_text(json.dumps({'recordsRetained':len(rows),
                'bins':{'small.bin':100,'large.bin':9900}}))
            selected,_=audit.sample_records(root,count=2000)
            self.assertEqual(len(np.unique(selected['record'])),2000)
            self.assertLess(np.mean(selected['record']<100),.025)
            np.testing.assert_array_equal(selected['xyz'][:,0],selected['record'])
            repeated,_=audit.sample_records(root,count=2000)
            np.testing.assert_array_equal(selected,repeated)
            full,_=audit.sample_records(root,count=20000)
            np.testing.assert_array_equal(np.sort(full['record']),rows['record'])
            (root/'manifest.json').write_text(json.dumps({'voxelMetres':.08}))
            with self.assertRaises(ValueError):audit.sample_records(root)


if __name__=='__main__':unittest.main()
