"""Read-only adapters for verified existing result artifacts."""
import hashlib,json
from pathlib import Path
import tifffile

def build(root,data):
 records={};geometry={}
 def add(dataset,name,path=None,channel=0,geo=None,note=''):
  d=data[dataset];shape=d.get('shape');factor=1;scope='volume'
  if path:
   with tifffile.TiffFile(path) as f:arrshape=list(f.series[0].shape)
   if len(arrshape)==2:scope='projection';arrshape=[1]+arrshape
   if shape:
    factor=shape[3]/arrshape[2]
    if shape[2]/arrshape[1]!=factor or (scope=='volume' and shape[0]!=arrshape[0]):return
  else:arrshape=shape[:1]+shape[2:];scope='projection' if geo and geo.get('boxes') else 'volume'
  rid=hashlib.sha256((dataset+name+str(path)).encode()).hexdigest()[:32]
  records[rid]=dict(id=rid,dataset=dataset,method=name,title=name,channel=channel,scope=scope,factor=int(factor),z=0,shape=arrshape,objects=None,seconds=None,created=0,historical=True,parameters=None,meaning=note or 'Earlier algorithm output; not expert-validated',mask_path=str(path) if path else None,source=d['path'],spacing=d['spacing'],geometry=bool(geo))
  if geo:geometry[rid]=geo
 base=root/'outputs/imop-methods-20260907'
 if base.exists():
  data['imop']['shape']=[14,2,1024,1024];data['imop']['dtype']='uint8'
  titles={'otsu':'Otsu','background_otsu':'Background + Otsu','sato':'Sato','sato_hysteresis':'Sato + hysteresis','frangi':'Frangi','meijering':'Meijering','watershed_nuclei':'Watershed nuclei','cellpose3d_nuclei':'Cellpose 3D • nuclei','cellpose3d_tuj1':'Cellpose 3D • Tuj1','cellpose_stitched_nuclei':'Cellpose • stitched slices','cellpose_mip_nuclei':'Cellpose projection • nuclei','cellpose_mip_tuj1':'Cellpose projection • Tuj1','stardist_mip_0.35':'StarDist • threshold 0.35','stardist_mip_0.5':'StarDist • threshold 0.5','microsam_log_prompted_nuclei':'micro-SAM • prompted nuclei'}
  for name,title in titles.items():
   p=base/(name+'.tif')
   if p.exists():add('imop',title,p,1 if any(s in name for s in ['nuclei','stardist']) else 0)
  x=json.loads((base/'experiments.json').read_text())
  for name in ['snt_t20','snt_auto']:add('imop',x['networks'][name]['title'],geo=x['networks'][name],note='Candidate paths; crossings do not establish neuron ownership')
  add('imop','LoG • nuclei centers',channel=1,geo=x['nuclei']['log_nuclei'])
 base=root/'outputs/set1-benchmark';protocol=base/'protocol.json'
 if protocol.exists():
  for field in json.loads(protocol.read_text())['fields']:
   name=field['key'];path=base/'inputs'/(name+'.tif');key='crop-'+hashlib.sha256(name.encode()).hexdigest()[:10]
   if not path.exists():continue
   c,z,h,w=field['shape_CZYX'];data[key]=dict(id=key,name='Benchmark crop • '+name,path=str(path.relative_to(root)),axes='CZYX',shape=[z,c,h,w],dtype='uint8',spacing=[.155981445,.155981445,1],calibrated=True,channels=['Myo7a','Channel 2','Channel 3','DAPI'],crop_origin=field['context_xyxy'][:2],original_source=field['source'])
   add(key,'Cellpose • projection',base/'projection'/(name+'.tif'))
   for folder,files in [('models',['cellpose3d','slices']),('classical',['connected3d','overlap-stitch','global-graph','dapi-watershed3d']),('usegment3d',['labels'])]:
    for fn in files:
     p=base/folder/name/(fn+'.tif')
     if p.exists():add(key,('u-Segment3D' if folder=='usegment3d' else fn.replace('-',' ').replace('cellpose','Cellpose ')),p)
   for entry in json.loads((base/'hcat/report.json').read_text())['fields']:
    if entry['field']==name:add(key,'HCAT • '+entry['mode'],geo={'boxes':entry['boxes']},note='Projection detection boxes in the benchmark context crop')
 return records,geometry
