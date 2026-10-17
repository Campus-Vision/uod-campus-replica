"""Independent shipping-GLB support/colour/edge audit for local parking meshes."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('details',PROJECT/'scripts/prepare-details.py')
details=importlib.util.module_from_spec(spec)
spec.loader.exec_module(details)
np=details.np


class ParkingSurfaceTests(unittest.TestCase):
    def test_binary_geometry_and_source_support(self):
        out=PROJECT/'public/replica'
        blob=(out/'parking-surfaces.glb').read_bytes()
        magic,version,size=struct.unpack_from('<III',blob)
        self.assertEqual((magic,version,size),(0x46546c67,2,len(blob)))
        header_size,kind=struct.unpack_from('<II',blob,12)
        self.assertEqual(kind,0x4e4f534a)
        doc=json.loads(blob[20:20+header_size])
        payload=memoryview(blob)[28+header_size:]
        metadata=json.loads((out/'parking-surfaces.json').read_text())
        self.assertLess(metadata['count'],500000)
        source=np.fromfile(out/'building.positions.bin','<f4').reshape(-1,3)
        colors=np.fromfile(out/'building.colors.bin','uint8').reshape(-1,3)
        world=source[:,:2].astype(float)+[340150,2777800]
        pixels=np.column_stack(((world[:,0]-339750)/900*1497,
                               (2778350.09765625-world[:,1])/1000.1953125*1664))

        def array(index):
            accessor=doc['accessors'][index]
            view=doc['bufferViews'][accessor['bufferView']]
            dtype={5126:'<f4',5125:'<u4',5121:'uint8'}[accessor['componentType']]
            width={'VEC3':3,'SCALAR':1}[accessor['type']]
            return np.frombuffer(payload,dtype=dtype,count=accessor['count']*width,
                                 offset=view['byteOffset']).reshape(-1,width)

        for region in metadata['regions']:
            node=doc['nodes'][region['node']]
            self.assertEqual(node['name'],region['id'])
            primitive=doc['meshes'][node['mesh']]['primitives'][0]
            vertices=array(primitive['attributes']['POSITION'])
            rgb=array(primitive['attributes']['COLOR_0'])
            faces=array(primitive['indices']).reshape(-1,3)
            self.assertEqual(len(faces),region['triangles'])
            self.assertTrue(np.isfinite(vertices).all())
            self.assertLess(int(faces.max()),len(vertices))
            p=vertices[faces]
            for a,b in [(0,1),(1,2),(2,0)]:
                self.assertLessEqual(float(np.linalg.norm(p[:,a]-p[:,b],axis=1).max()),.45002)
            ids=np.flatnonzero(details.inside_polygon(pixels,region['referencePixelPolygon']))
            height=source[ids,2]-details.local_floor(source[ids])
            ids=ids[(height>=metadata['minimumAboveLocalFloorMetres']) &
                    (height<=metadata['maximumAboveLocalFloorMetres'])]
            tree=details.cKDTree(source[ids])
            distance,nearest=tree.query(vertices,workers=8)
            self.assertLessEqual(float(distance.max()),.14002)
            np.testing.assert_array_equal(colors[ids[nearest]],rgb)
            distance,_=tree.query(p.mean(axis=1),workers=8)
            self.assertLessEqual(float(distance.max()),.16002)
            self.assertGreater(region['coverageFractionImprovement'],0)


if __name__=='__main__': unittest.main()
