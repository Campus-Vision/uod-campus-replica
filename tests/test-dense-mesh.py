"""Geometry gates for the full-resolution reconstruction pipeline."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('mesh',PROJECT/'scripts/reconstruct-dense.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np,o3d=module.np,module.o3d


class DenseMeshTests(unittest.TestCase):
    @unittest.skipUnless((PROJECT.parent/'analysis/dense-reconstruction/vegetation-pilot.json').exists(), 'Dense trials not generated')
    def test_dense_trial_glbs_against_original_record_cache(self):
        for name in ['south-pilot','building-pilot','vegetation-pilot']:
            path=PROJECT.parent/'analysis/dense-reconstruction'/name
            meta=json.loads(path.with_suffix('.json').read_text())
            blob=path.with_suffix('.glb').read_bytes()
            n=struct.unpack_from('<I',blob,12)[0];doc=json.loads(blob[20:20+n]);payload=memoryview(blob)[28+n:]
            primitive=doc['meshes'][0]['primitives'][0]
            def array(index):
                a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
                size={'VEC3':3,'SCALAR':1}[a['type']]
                dtype={5126:'<f4',5125:'<u4',5121:'u1'}[a['componentType']]
                return np.frombuffer(payload,dtype=dtype,count=a['count']*size,offset=v['byteOffset']).reshape(-1,size)
            positions=array(primitive['attributes']['POSITION']);colours=array(primitive['attributes']['COLOR_0'])
            faces=array(primitive['indices']).reshape(-1,3)
            self.assertEqual(len(faces),meta['triangles']);self.assertEqual(len(positions),meta['vertices'])
            self.assertTrue(np.isfinite(positions).all());self.assertLess(int(faces.max()),len(positions))
            records=module.dense.load_region(PROJECT.parent/'analysis/dense-las',meta['boundsLocal'],meta['haloMetres'])
            tree=module.cKDTree(records['xyz'])
            chosen=np.linspace(0,len(positions)-1,1024,dtype=int)
            distance,nearest=tree.query(positions[chosen],k=4,workers=8)
            self.assertLessEqual(float(distance[:,0].max()),.10002)
            weight=1/np.maximum(distance,.004)**2
            weight[distance>np.maximum(distance[:,:1]+.015,.04)]=0
            expected=np.rint((records['rgb'][nearest]*weight[:,:,None]).sum(axis=1)/weight.sum(axis=1)[:,None]).astype('u1')
            np.testing.assert_array_equal(colours[chosen],expected)
            self.assertGreater(meta['originalRegionRecords'],4000000)

    def test_supported_vertices_cannot_bridge_unmeasured_space(self):
        vertices=np.array([[0,0,0],[.1,0,0],[0,.1,0],[1,0,0],[1.1,0,0],[1,.1,0]],float)
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),
            o3d.utility.Vector3iVector([[0,1,2],[3,4,5],[1,3,2]]))
        tree=module.cKDTree(vertices)
        result=module.supported_mesh(mesh,tree,[-1,2,-1,1])
        self.assertEqual(len(result.triangles),2)
        self.assertLess(np.linalg.norm(np.asarray(result.vertices)[np.asarray(result.triangles)[:,0]]-
                                      np.asarray(result.vertices)[np.asarray(result.triangles)[:,1]],axis=1).max(),.15)

    def test_export_contains_triangle_indices_normals_and_colour(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'mesh.glb'
            module.write_glb(path,np.array([[0,0,0],[.1,0,0],[0,.1,0]],'<f4'),
                np.array([[0,1,2]],'<u4'),np.full((3,3),128,'u1'),
                np.tile([0,0,1],(3,1)).astype('<f4'))
            blob=path.read_bytes();self.assertEqual(struct.unpack_from('<I',blob,8)[0],len(blob))
            n=struct.unpack_from('<I',blob,12)[0];doc=json.loads(blob[20:20+n])
            primitive=doc['meshes'][0]['primitives'][0]
            self.assertEqual(doc['accessors'][primitive['indices']]['count'],3)
            self.assertEqual(set(primitive['attributes']),{'POSITION','NORMAL','COLOR_0'})
            self.assertEqual(primitive.get('mode',4),4)


if __name__=='__main__':unittest.main()
