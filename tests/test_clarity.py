import os,sys,tempfile,unittest,uuid,time
from pathlib import Path
import numpy as np
os.environ.setdefault('STUDIO_ROOT',str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('STUDIO_STORE',tempfile.mkdtemp())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server as s
import reporting,experiments,measurements,corrections

class ClarityChecks(unittest.TestCase):
    def setUp(self):
        self.key='clarity-'+uuid.uuid4().hex
        a=np.zeros((5,1,32,32),np.uint8);a[1:4,0,8:14,8:14]=180;a[1:4,0,20:26,20:26]=120
        path=s.STORE/(self.key+'.tif');s.tifffile.imwrite(path,a,metadata={'axes':'ZCYX'})
        s.DATA[self.key]=dict(id=self.key,name='Test source',path=str(path),axes='ZCYX',shape=list(a.shape),spacing=[.2,.2,1],calibrated=True,channels=['Myo7a'])
    def run_recipe(self,**overrides):
        rid=uuid.uuid4().hex;s.JOBS[rid]={'created':time.time()}
        s.run_job(rid,dict(dataset=self.key,channel=0,scope='volume',factor=1,method='otsu',min_size=1,**overrides))
        self.assertEqual(s.JOBS[rid]['status'],'completed',s.JOBS[rid]);return rid
    def test_off_filters_and_review_are_not_claimed(self):
        rid=self.run_recipe();q=dict(dataset=self.key,run=rid,channel=0)
        result=reporting.explain(q)
        self.assertIn('all off',result['sections']['Preparation'])
        self.assertIn('2 candidate regions',result['sections']['Output'])
        self.assertIn('2 unreviewed',result['sections']['Review'])
        self.assertIn('not established',result['sections']['Validation'])
        with self.assertRaises(ValueError):reporting.explain({**q,'dataset':'another'})
    def test_parent_preparation_and_current_corrections(self):
        parent=self.run_recipe(sigma=.3,normalize=True)
        rid=self.run_recipe(parent=parent);q=dict(dataset=self.key,run=rid,channel=0)
        report=reporting.explain(q)
        self.assertIn('percentile normalization',report['sections']['Preparation'])
        self.assertEqual(len(report['provenance']['parent_stages']),2)
        corrections.save(dict(q,action='delete',object=1,expected_label_revision=None))
        report=reporting.explain(q)
        self.assertIn('Original algorithm output: 2',report['sections']['Output'])
        self.assertIn('Current label layer: 1',report['sections']['Review'])
        protocol=measurements.save_protocol(dict(q,target='hair cells',channel_role='Myo7a',edge_policy='include',expected_revision=None))
        measurements.save(dict(q,object=2,status='accepted',expected_revision=None))
        report=reporting.explain(q)
        self.assertIn('Reviewed count under saved rules: 1 hair cells',report['sections']['Review'])
        self.assertIn('not established',report['sections']['Validation'])
    def test_four_options_share_window_and_leave_no_runs(self):
        before=set((s.STORE/'runs').glob('*'))
        result=experiments.cleanup_compare(dict(dataset=self.key,channel=0,parameters=dict(scope='volume',method='watershed',factor=1,normalize=True),bounds=[4,4,0,28,28,5],margin=2,smooth=.5,background=3))
        variants=result['variants'];self.assertEqual(len(variants),4)
        self.assertTrue(all(v['result_window']==variants[0]['source_window'] for v in variants))
        self.assertTrue(all(v['parameters']['normalize'] is False for v in variants))
        self.assertTrue(all(v['bounds']==variants[0]['bounds'] for v in variants))
        self.assertEqual(set((s.STORE/'runs').glob('*')),before)
        self.assertNotEqual(variants[0]['planes'][2]['result'],variants[1]['planes'][2]['result'])
        with self.assertRaisesRegex(ValueError,'original source'):
            experiments.cleanup_compare(dict(parameters=dict(parent='something')))
    def test_queue_wraps_and_respects_current_decisions(self):
        rid=self.run_recipe();q=dict(dataset=self.key,run=rid,channel=0,status='unresolved',limit=1)
        self.assertEqual(measurements.table(dict(q,after=1))['next_candidate'],2)
        self.assertEqual(measurements.table(dict(q,after=2))['next_candidate'],1)
        review=measurements.save(dict(q,object=1,status='accepted',expected_revision=None))
        self.assertEqual(measurements.table(dict(q,after=2))['next_candidate'],2)
        measurements.save(dict(q,object=2,status='rejected',expected_revision=review['revision']))
        self.assertIsNone(measurements.table(q)['next_candidate'])
    def test_new_methods_save_and_explain(self):
        for method in ['adaptive_regions','prominence_watershed']:
            rid=uuid.uuid4().hex;s.JOBS[rid]={'created':time.time()}
            s.run_job(rid,dict(dataset=self.key,channel=0,scope='volume',factor=1,method=method,min_size=1))
            self.assertEqual(s.JOBS[rid]['status'],'completed',s.JOBS[rid])
            q=dict(dataset=self.key,run=rid,channel=0)
            report=reporting.explain(q)
            self.assertIn('Local window' if method=='adaptive_regions' else 'Peak prominence',report['sections']['Detection'])
            self.assertGreater(measurements.table(q)['total'],0)
