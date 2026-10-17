"""UV preparation must preserve triangles while separating touching fans."""
import importlib.util
from pathlib import Path
import sys
import unittest
import json
import struct
import io
sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bake',PROJECT/'scripts/bake-dense.py')
bake=importlib.util.module_from_spec(spec);spec.loader.exec_module(bake)
np,o3d=bake.np,bake.o3d


class BakeTests(unittest.TestCase):
    @unittest.skipUnless((PROJECT.parent/'analysis/dense-reconstruction/south-pilot-textured.json').exists(), 'Textured trial not generated')
    def test_exported_textured_mesh_against_dense_parent(self):
        path=PROJECT.parent/'analysis/dense-reconstruction/south-pilot-textured'
        meta=json.loads(path.with_suffix('.json').read_text());blob=path.with_suffix('.glb').read_bytes()
        n=struct.unpack_from('<I',blob,12)[0];doc=json.loads(blob[20:20+n]);payload=memoryview(blob)[28+n:]
        primitive=doc['meshes'][0]['primitives'][0]
        def array(index):
            a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
            dtype={5126:'<f4',5125:'<u4',5121:'u1'}[a['componentType']]
            width={'VEC3':3,'VEC2':2,'SCALAR':1}[a['type']]
            return np.frombuffer(payload,dtype=dtype,count=a['count']*width,offset=v['byteOffset']).reshape(-1,width)
        vertices=array(primitive['attributes']['POSITION']);uv=array(primitive['attributes']['TEXCOORD_0'])
        faces=array(primitive['indices']).reshape(-1,3)
        self.assertEqual(len(faces),meta['triangles']);self.assertLess(len(faces),250000)
        self.assertTrue(np.isfinite(uv).all());self.assertGreaterEqual(uv.min(),0);self.assertLessEqual(uv.max(),1)
        view=doc['bufferViews'][doc['images'][0]['bufferView']]
        from PIL import Image
        image=Image.open(io.BytesIO(payload[view['byteOffset']:view['byteOffset']+view['byteLength']]))
        self.assertEqual(image.size,(2048,2048));image.verify()
        parent=o3d.io.read_triangle_mesh(str(path.with_name('south-pilot.glb')))
        scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(parent))
        rng=np.random.default_rng(17);ids=rng.integers(0,len(faces),20000)
        weights=rng.dirichlet([1,1,1],len(ids))
        points=np.einsum('nc,ncd->nd',weights,vertices[faces[ids]]).astype('f4')
        distance=scene.compute_distance(o3d.core.Tensor(points)).numpy()
        self.assertLessEqual(float(distance.max()),.06502)
        self.assertLessEqual(meta['adaptiveParentSupport']['maximumRetainedSampleDistanceMetres'],.025)

    def test_asymmetric_uv_reference_matches_top_row_first_texture(self):
        mesh=o3d.t.geometry.TriangleMesh(
            o3d.core.Tensor([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1.,1.,0.]],o3d.core.Dtype.Float32),
            o3d.core.Tensor([[0,1,2],[1,3,2]],o3d.core.Dtype.Int64))
        mesh.triangle['texture_uvs']=o3d.core.Tensor(
            [[[0.,0.],[1.,0.],[0.,1.]],[[1.,0.],[1.,1.],[0.,1.]]],o3d.core.Dtype.Float32)
        texture=mesh.bake_vertex_attr_textures(8,{'positions'},update_material=False)['positions'].numpy()
        original=np.array([[.1875,.3125],[.6875,.8125]],'f4')
        converted=bake.gltf_uv_from_atlas(original)
        for expected,uv in zip(original,converted):
            x,y=np.floor(uv*8).astype(int)
            np.testing.assert_allclose(texture[y,x,:2],expected,atol=1e-7)

    def test_large_face_cannot_span_unsupported_interior(self):
        corners=np.array([[0,0,0],[1,0,0],[0,1,0]],float)
        centres=np.vstack([corners,(corners[0]+corners[1])/2,
                           (corners[1]+corners[2])/2,(corners[2]+corners[0])/2,corners.mean(axis=0)])
        vertices=np.concatenate([c+[[0,0,0],[.003,0,0],[0,.003,0]] for c in centres])
        faces=np.arange(len(vertices)).reshape(-1,3)
        parent=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(faces))
        scene=o3d.t.geometry.RaycastingScene();scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(parent))
        candidate=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(corners),o3d.utility.Vector3iVector([[0,1,2]]))
        # All the old seven samples are supported, but the face interior is not.
        seven=scene.compute_distance(o3d.core.Tensor(centres.astype('f4'))).numpy()
        self.assertLess(seven.max(),.00001)
        keep,metadata=bake.adaptive_face_support(candidate,scene,spacing=.04,cutoff=.025)
        self.assertFalse(keep[0]);self.assertGreater(metadata['sampleCount'],100)

    def test_split_touching_vertex_fans_preserves_all_surface_positions(self):
        vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]],float)
        faces=np.array([[0,1,2],[0,3,4]],int)
        mesh=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices),o3d.utility.Vector3iVector(faces))
        self.assertFalse(mesh.is_vertex_manifold())
        result,count=bake.split_vertex_fans(mesh)
        self.assertTrue(result.is_vertex_manifold())
        self.assertEqual(count,1)
        np.testing.assert_array_equal(np.asarray(result.vertices)[np.asarray(result.triangles)],vertices[faces])


if __name__=='__main__':unittest.main()
