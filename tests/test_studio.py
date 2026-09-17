import os,sys,tempfile,json,unittest,csv,io
from pathlib import Path
os.environ['STUDIO_ROOT']=str(Path(__file__).resolve().parents[1]);os.environ['STUDIO_STORE']=tempfile.mkdtemp()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import server as s
for entry in (Path(__file__).parent/"fixtures").glob("*.json"):
 d=json.loads(entry.read_text());d["path"]=str(entry.with_name(Path(d["path"]).name).resolve());s.DATA[d["id"]]=d
class StudioChecks(unittest.TestCase):
 def test_3d_roundtrip_and_length(self):
  item=dict(id='trace',type='polyline',domain='volume',channel=0,z=0,points=[[10,10,2],[10,10,5]],status='unreviewed',label='Depth QA')
  d=s.save_annotations(dict(dataset='demo-cells',author='QA',items=[item],base_revision=None));p=s.STORE/'annotations/demo-cells'/d['revision']
  self.assertEqual(s.annotation_current('demo-cells')['items'][0]['points'],item['points'])
  row=list(csv.DictReader(io.StringIO((p/'measurements.csv').read_text())))[0];self.assertEqual(float(row['length_3d_um']),3);self.assertEqual(row['length_2d_um'],'')
 def test_persist_failure_rolls_back(self):
  old=s.annotation_current('demo-cells');persist=s.persist
  s.persist=lambda *args:(_ for _ in ()).throw(RuntimeError('offline'))
  try:
   with self.assertRaisesRegex(RuntimeError,'offline'):s.save_annotations(dict(dataset='demo-cells',author='QA',items=[],base_revision=old['revision']))
   self.assertEqual(s.annotation_current('demo-cells')['revision'],old['revision'])
  finally:s.persist=persist
 def test_invalid_depth(self):
  with self.assertRaises(ValueError):s.validate_items('demo-cells',[dict(type='point',domain='volume',channel=0,z=0,points=[[0,0,24]],status='accepted')])
 def test_real_processing(self):
  for method in ['otsu','watershed','sato']:
   jid={'otsu':'aaa','watershed':'bbb','sato':'ccc'}[method];s.JOBS[jid]={'created':s.time.time()}
   s.run_job(jid,dict(dataset='demo-cells',channel=1,scope='volume',factor=2,method=method,min_size=10))
   self.assertEqual(s.JOBS[jid]['status'],'completed');self.assertGreater(s.JOBS[jid]['result']['objects'],0)
 def test_open_neurite_export(self):
  key='demo-neurites';current=s.annotation_current(key)
  points=[[10,10],[13,10],[13,14]]
  item=dict(id='open-trace',type='polyline',domain='slice',channel=0,z=2,points=points,status='unreviewed',label='Neurite 1')
  doc=s.save_annotations(dict(dataset=key,author='QA',items=[item],base_revision=current['revision']))
  folder=s.STORE/'annotations'/key/doc['revision']
  row=list(csv.DictReader(io.StringIO((folder/'measurements.csv').read_text())))[0]
  sx,sy,_=s.metadata(key)['spacing']
  self.assertAlmostEqual(float(row['length_2d_um']),3*sx+4*sy)
  self.assertEqual(row['area_2d_um2'],'');self.assertEqual(row['length_3d_um'],'')
  roi=s.roifile.roiread(folder/'RoiSet.zip')[0]
  self.assertEqual(roi.roitype,s.roifile.ROI_TYPE.POLYLINE)
  self.assertEqual(len(roi.coordinates()),3)
 def test_planar_roi(self):
  item=dict(id='point',type='point',domain='slice',channel=1,z=3,points=[[11.25,20.5]],status='accepted')
  doc=s.save_annotations(dict(dataset='demo-neurites',author='QA',items=[item],base_revision=s.annotation_current('demo-neurites')['revision']))
  rois=s.roifile.roiread(s.STORE/'annotations/demo-neurites'/doc['revision']/'RoiSet.zip')
  self.assertEqual(rois[0].z_position,4);self.assertEqual(rois[0].c_position,2)
if __name__=='__main__':unittest.main()
