import os
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np

os.environ.setdefault('STUDIO_ROOT', str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('STUDIO_STORE', tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from neurites import METHODS, skeleton_graph, measure, prune
from processing import process
import server as s


class NeuriteChecks(unittest.TestCase):
    def graph(self, points, shape=(9,9), spacing=(1,1)):
        a=np.zeros(shape,bool)
        for point in points:a[point]=True
        return skeleton_graph(a,spacing)

    def test_calibrated_straight_diagonal_and_corner(self):
        horizontal=self.graph([(3,x) for x in range(1,7)],spacing=(2,.5))
        self.assertAlmostEqual(horizontal['length'],2.5)
        self.assertEqual((horizontal['endpoints'],horizontal['junctions'],len(horizontal['branches'])),(2,0,1))
        diagonal=self.graph([(x,x) for x in range(1,7)],spacing=(2,.5))
        self.assertAlmostEqual(diagonal['length'],5*np.hypot(2,.5))
        # The corner has two occupied axial edges; a diagonal must not count again.
        corner=self.graph([(2,2),(2,3),(3,3)],spacing=(2,.5))
        self.assertAlmostEqual(corner['length'],2.5)
        self.assertEqual(corner['junctions'],0)

    def test_anisotropic_3d_and_y_branch(self):
        line=self.graph([(z,3,3) for z in range(1,6)],shape=(8,8,8),spacing=(3,1,.5))
        self.assertAlmostEqual(line['length'],12)
        points=[(3,3),(2,2),(1,1),(2,4),(1,5),(4,3),(5,3)]
        graph=self.graph(points)
        self.assertEqual((graph['endpoints'],graph['junctions'],len(graph['branches'])),(3,1,3))
        self.assertAlmostEqual(graph['length'],4*np.sqrt(2)+2)
        self.assertAlmostEqual(sum(b['length'] for b in graph['branches'])+graph['junction_length'],graph['length'])

    def test_junction_cluster_is_one_junction(self):
        points=[(3,3),(3,4),(2,3),(1,3),(4,3),(5,3),(2,4),(1,4),(4,4),(5,4)]
        graph=self.graph(points)
        self.assertEqual(graph['junctions'],1)
        self.assertAlmostEqual(sum(b['length'] for b in graph['branches'])+graph['junction_length'],graph['length'])

    def test_loop_and_short_terminal_pruning(self):
        loop=self.graph([(2,2),(2,3),(2,4),(3,4),(4,4),(4,3),(4,2),(3,2)])
        self.assertEqual(loop['endpoints'],0);self.assertEqual(len(loop['branches']),1)
        self.assertEqual(loop['branches'][0]['kind'],'loop');self.assertAlmostEqual(loop['length'],8)
        a=np.zeros((9,9),bool);a[4,1:8]=True;a[3,4]=True
        result=prune(a,[1,1],2)
        self.assertFalse(result[3,4]);self.assertTrue(result[4,4]);self.assertEqual(int(result.sum()),7)

    def test_calibration_and_empty_measurement(self):
        labels=np.zeros((1,10,10),np.uint32);labels[0,4,2:8]=1
        skeleton,rows,branches,summary=measure(labels,[2,1,.5],True)
        self.assertEqual(summary['total_length_um'],2.5);self.assertEqual(rows[0]['length_grid'],5)
        self.assertEqual(branches[0]['units'],'µm');self.assertEqual(skeleton.shape,labels.shape)
        _,_,_,uncal=measure(labels,[2,1,.5],False)
        self.assertIsNone(uncal['total_length_um']);self.assertEqual(uncal['total_length_grid'],5)
        self.assertEqual(measure(np.zeros_like(labels),[2,1,.5])[3]['networks'],0)
        with self.assertRaises(ValueError):skeleton_graph(labels[0],[-1,1])

    def test_methods_execute_and_physical_ridge_guards(self):
        a=np.zeros((3,48,48),np.float32);a[:,21:24,5:42]=100;a[:,8:42,21:24]=100
        metadata=dict(spacing=[.5,.5,2],calibrated=True)
        for method in METHODS:
            with self.subTest(method=method):
                processed,labels,score,_,effective=process(a,dict(method=method,min_size=2,ridge_sigmas=[1,2]),metadata,1)
                self.assertEqual(labels.shape,a.shape);self.assertTrue(np.any(labels));self.assertEqual(score.shape,a.shape)
                self.assertEqual(effective['neurite_mode'],'slice')
                if method=='neurite_adaptive':self.assertEqual(effective['adaptive_floor'],.25)
        _,_,_,_,effective=process(a,dict(method='neurite_sato',units='physical',ridge_scales_um=[.5,1],min_size_physical=0),metadata,1)
        self.assertEqual(effective['ridge_sigmas'],[1,2])
        with self.assertRaisesRegex(ValueError,'isotropic'):
            process(a,dict(method='neurite_sato',units='physical',neurite_mode='volume'),metadata,1)
        with self.assertRaisesRegex(ValueError,'odd integer'):
            process(a,dict(method='neurite_adaptive',adaptive_block_size=4),metadata,1)

    def test_adaptive_floor_rejects_connected_dim_noise(self):
        rng=np.random.default_rng(3)
        a=rng.uniform(0,2,(1,96,96)).astype(np.float32);a[:,46:49,8:88]=100
        yy,xx=np.mgrid[:96,:96]
        a+=80*np.exp(-((yy-65)**2+(xx-65)**2)/72)
        meta=dict(spacing=[1,1,1],calibrated=False)
        _,baseline,_,_,_=process(a,dict(method='neurite_adaptive',adaptive_floor=0,min_size=30),meta,1)
        _,limited,_,_,effective=process(a,dict(method='neurite_adaptive',adaptive_floor=.25,min_size=30),meta,1)
        self.assertLess(np.count_nonzero(limited),np.count_nonzero(baseline))
        self.assertGreater(effective['adaptive_floor_value'],0)
        self.assertTrue(np.all(limited[0,47,10:85]>0))

    def test_selected_saved_region_coordinates_measurements_and_lineage(self):
        key='neurite-'+uuid.uuid4().hex
        source=np.zeros((5,1,32,48),np.uint8);source[1:4,0,14:17,4:44]=100
        path=s.STORE/(key+'.tif');s.tifffile.imwrite(path,source,metadata={'axes':'ZCYX'})
        s.DATA[key]=dict(id=key,name='test',path=str(path),axes='ZCYX',shape=list(source.shape),spacing=[.5,.5,2],calibrated=True,channels=['signal'])
        def run(**extra):
            rid=uuid.uuid4().hex;s.JOBS[rid]={'created':time.time()}
            s.run_job(rid,dict(dataset=key,channel=0,factor=2,scope='volume',method='neurite_otsu',min_size=1,**extra))
            return rid
        try:
            rid=run(bounds=[5,9,1,33,25,4]);self.assertEqual(s.JOBS[rid]['status'],'completed')
            doc,folder=s.getrun(rid);self.assertEqual(doc['region_bounds'],[4,8,1,34,26,4]);self.assertEqual(doc['shape'],[5,16,24])
            labels=s.run_array(rid,'labels');self.assertEqual(labels.shape,(5,16,24));self.assertFalse(labels[0].any());self.assertFalse(labels[4].any());self.assertFalse(labels[:,:,:2].any());self.assertFalse(labels[:,:,17:].any())
            self.assertTrue((folder/'neurites.csv').is_file());self.assertTrue((folder/'skeleton.tif').is_file());self.assertGreater(doc['neurites']['total_length_um'],0)
            inherited=run(parent=rid);self.assertEqual(s.JOBS[inherited]['result']['region_bounds'],doc['region_bounds'])
            # A bounded crop can run below the compute limit while preserving a larger coordinate grid.
            with patch.dict(os.environ,{'STUDIO_PROCESS_VOXELS':'100','STUDIO_LABEL_VOXELS':'5000'}):
                bounded=run(bounds=[8,10,1,16,18,3],region_margin=0)
                self.assertEqual(s.JOBS[bounded]['status'],'completed')
                self.assertEqual(s.JOBS[bounded]['result']['shape'],[5,16,24])
            # Output allocations are guarded independently, before accessing source pixels.
            with patch.dict(os.environ,{'STUDIO_LABEL_VOXELS':'100'}),patch.object(s,'volume',side_effect=AssertionError('must guard output before source load')):
                oversized=run(bounds=[8,10,1,16,18,3],region_margin=0)
                self.assertEqual(s.JOBS[oversized]['status'],'failed')
                self.assertIn('output voxel limit',s.JOBS[oversized]['error'])
            with patch.object(s,'volume',side_effect=AssertionError('invalid region must fail before source load')):
                bad=run(bounds=[5.5,9,1,33,25,4]);self.assertEqual(s.JOBS[bad]['status'],'failed')
        finally:
            s.DATA.pop(key);s.volume.cache_clear();s.run_array.cache_clear()


if __name__=='__main__':unittest.main()
