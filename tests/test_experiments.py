import base64
import io
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image

os.environ.setdefault('STUDIO_ROOT', str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('STUDIO_STORE', tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import server as s
import experiments as e
from processing import process, settings, physical_peaks


class ExperimentChecks(unittest.TestCase):
    def setUp(self):
        self.key='experiment-'+uuid.uuid4().hex
        zz,yy,xx=np.mgrid[:6,:32,:48]
        a=((xx-15)**2+(yy-14)**2+(zz-3)**2<49).astype(np.uint16)*200
        self.a=a+xx.astype(np.uint16)
        path=s.STORE/(self.key+'.tif')
        s.tifffile.imwrite(path,self.a[:,None],metadata={'axes':'ZCYX'})
        self.meta=dict(id=self.key,name='experiment fixture',path=str(path),axes='ZCYX',shape=[6,1,32,48],spacing=[.5,1,2],channels=['signal'],calibrated=True)
        s.DATA[self.key]=self.meta
        self.q=dict(dataset=self.key,channel=0,parameters=dict(method='preprocess',factor=2),bounds=[5,7,1,23,25,5],margin=3)

    def tearDown(self):
        s.DATA.pop(self.key)
        s.volume.cache_clear();s.run_array.cache_clear()

    def test_preview_native_block_alignment_and_no_saved_artifact(self):
        before=set((s.STORE/'runs').glob('*'))
        result=e.preview(self.q)
        self.assertEqual(result['bounds'],[4,6,1,24,26,5])
        self.assertEqual(result['context_bounds'],[0,2,1,28,30,5])
        self.assertEqual([p['z'] for p in result['planes']],[1,2,3,4])
        self.assertEqual(set((s.STORE/'runs').glob('*')),before)
        png=Image.open(io.BytesIO(base64.b64decode(result['planes'][0]['result'])))
        self.assertEqual(png.size,(20,20))
        expected=s.block_reduce(self.a[1:5,6:26,4:24],(1,2,2),np.mean)
        np.testing.assert_allclose(result['result_window'],np.percentile(expected,[1,99.7]))

    def test_preview_limit_checks_before_loading(self):
        with patch.dict(os.environ,{'STUDIO_PROCESS_VOXELS':'1'}),patch.object(s,'volume',side_effect=AssertionError('must not load pixels')):
            with self.assertRaisesRegex(ValueError,'Preview including context'):
                e.preview(self.q)
        for bounds in [[8,7,1,4,25,5],[5,7,-1,23,25,5],[5.5,7,1,23,25,5]]:
            with self.assertRaises(ValueError):e.preview({**self.q,'bounds':bounds})

    def test_physical_intent_across_resolution(self):
        params=dict(units='physical',sigma_um=2,background_um=8,min_size_physical=80,min_final_physical=40,seed_distance_um=3)
        one=settings(params,self.meta,1,3);two=settings(params,self.meta,2,3)
        self.assertEqual(one['sigma_yx'],[2,4]);self.assertEqual(two['sigma_yx'],[1,2])
        self.assertEqual(one['min_size'],80);self.assertEqual(two['min_size'],20)
        self.assertEqual(two['min_final_size'],10)
        with self.assertRaisesRegex(ValueError,'calibrated'):
            settings(params,{**self.meta,'calibrated':False},1,3)
        # A one-plane acquired volume still uses cubic units, not square units.
        _,_,_,_,effective=process(self.a[:1],{**params,'method':'preprocess','scope':'volume'},self.meta,2)
        self.assertEqual(effective['min_size'],20)

    def test_seed_suppression_uses_physical_distance(self):
        dist=np.zeros((5,5,12));dist[1,2,2]=10;dist[3,2,2]=9;dist[1,2,8]=8
        # Z peaks are 4 µm apart and survive 3 µm suppression; X peaks are 3 µm apart.
        points=physical_peaks(dist,dist>0,[2,1,.5],3)
        self.assertEqual(set(map(tuple,points)),{(1,2,2),(3,2,2)})

    def test_final_size_filter_is_after_segmentation(self):
        a=np.zeros((4,20,20),np.float32);a[1:3,2:4,2:4]=100;a[1:3,10:15,10:15]=100
        _,labels,_,_,_=process(a,dict(method='otsu',min_size=1,min_final_size=10),self.meta,1)
        self.assertEqual(int(labels.max()),1)
        self.assertEqual(int(np.count_nonzero(labels)),50)

    def make_run(self,method='otsu',**kwargs):
        rid=uuid.uuid4().hex;s.JOBS[rid]={'created':s.time.time()}
        params=dict(dataset=self.key,channel=0,factor=2,scope='volume',method=method,min_size=1,**kwargs)
        s.run_job(rid,params)
        self.assertEqual(s.JOBS[rid]['status'],'completed')
        return rid

    def test_saved_physical_provenance_and_comparison(self):
        a=self.make_run(units='physical',sigma_um=.5,min_size_physical=1,z=1)
        b=self.make_run(method='watershed',units='physical',seed_distance_um=3,min_size_physical=1,z=3)
        run,_=s.getrun(a)
        self.assertEqual(run['effective_parameters']['sigma_yx'],[.25,.5])
        result=e.compare(dict(dataset=self.key,channel=0,a=a,b=b,z=3,layer='processed',contrast='shared'))
        self.assertEqual(result['panes'][0]['window'],result['panes'][1]['window'])
        self.assertIn('method',[x['parameter'] for x in result['differences']])
        self.assertNotIn('z',[x['parameter'] for x in result['differences']])
        with self.assertRaisesRegex(ValueError,'two Sato'):
            e.compare(dict(dataset=self.key,channel=0,a=a,b=b,z=3,layer='ridge-response'))
        with self.assertRaises(ValueError):e.compare(dict(dataset=self.key,channel=1,a=a,b=b,z=3))

    def test_preview_scope_and_cancellation_guards(self):
        for scope in ['projection','slice']:
            with self.assertRaisesRegex(ValueError,'Full Z volume'):
                e.preview({**self.q,'parameters':dict(method='otsu',scope=scope)})
        with patch('processing.threshold_otsu',side_effect=AssertionError('must not segment')):
            _,labels,_,threshold,_=process(self.a,dict(method='otsu'),self.meta,1,lambda:True)
            self.assertIsNone(threshold)
            self.assertEqual(int(labels.max()),0)

    def test_preview_parent_and_projection_guards(self):
        rid=self.make_run(method='preprocess')
        with self.assertRaisesRegex(ValueError,'Parent must match'):
            e.preview({**self.q,'parameters':dict(method='preprocess',parent=rid,factor=1)})
        result=e.preview({**self.q,'parameters':dict(method='preprocess',parent=rid,factor=2)})
        self.assertEqual(result['parameters']['parent'],rid)
        folder=s.STORE/'runs'/rid;run,_=s.getrun(rid);s.atomic(folder/'run.json',{**run,'scope':'projection'})
        with self.assertRaisesRegex(ValueError,'full-volume'):
            e.compare(dict(dataset=self.key,channel=0,a=rid,b=rid,z=3))
