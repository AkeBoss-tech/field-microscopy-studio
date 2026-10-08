import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import numpy as np
from processing import process
from measurements import count_summary

class DetectionChecks(unittest.TestCase):
    metadata={'spacing':[.2,.2,1], 'calibrated':True}
    def labels(self,a,method,**kw):
        return process(a,dict(method=method,min_size=1,**kw),self.metadata,1)
    def test_blank_is_blank(self):
        for method in ['adaptive_regions','prominence_watershed']:
            for shape in [(1,32,32),(4,32,32)]:
                result=self.labels(np.zeros(shape),method)
                self.assertEqual(result[1].shape,shape)
                self.assertEqual(result[1].max(),0)
    def test_prominence_suppresses_shallow_splits_without_losing_foreground(self):
        y,x=np.mgrid[:64,:64]
        a=(((x-24)**2+(y-32)**2<12**2)|((x-40)**2+(y-32)**2<12**2))[None].astype(float)*100
        low=self.labels(a,'prominence_watershed',peak_prominence=.5)
        high=self.labels(a,'prominence_watershed',peak_prominence=20)
        self.assertEqual(low[1].max(),2)
        self.assertEqual(high[1].max(),1)
        np.testing.assert_array_equal(high[1]>0,a>0)
    def test_local_threshold_recovers_dim_object_on_uneven_background(self):
        y,x=np.mgrid[:64,:96];a=(x*.5+5).astype(float)
        dim=(x-16)**2+(y-32)**2<7**2;bright=(x-78)**2+(y-32)**2<7**2
        a[dim]+=10;a[bright]+=60
        global_labels=self.labels(a[None],'otsu')[1][0]
        local=self.labels(a[None],'adaptive_regions',local_floor=.15,local_window=31)
        self.assertEqual(global_labels[32,16],0)
        self.assertGreater(local[1][0,32,16],0)
        self.assertGreater(local[1][0,32,78],0)
        self.assertEqual(local[4]['local_window'],31)
    def test_parameters_and_count_readiness(self):
        a=np.zeros((1,32,32))
        with self.assertRaises(ValueError):self.labels(a,'adaptive_regions',local_window=4)
        with self.assertRaises(ValueError):self.labels(a,'prominence_watershed',peak_prominence=0)
        for method in ['adaptive_regions','prominence_watershed']:
            summary=count_summary({'method':method},[{'status':'accepted','boundary_faces':[]}],{'revision':'r','edge_policy':'include','target':'nuclei','channel_role':'DAPI'})
            self.assertTrue(summary['ready']);self.assertEqual(summary['reviewed_count'],1)
