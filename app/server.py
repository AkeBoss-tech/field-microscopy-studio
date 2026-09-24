from __future__ import annotations
import base64, csv, hashlib, io, json, os, sys, threading, time, traceback, uuid, zipfile
# Review helpers must share this process's dataset registry when launched as a script.
if __name__ == "__main__": sys.modules["server"] = sys.modules[__name__]
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import xml.etree.ElementTree as ET
import numpy as np
import tifffile, czifile, roifile
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from skimage.filters import threshold_otsu, sato
from skimage.feature import peak_local_max
from skimage.segmentation import watershed, find_boundaries
from skimage.morphology import remove_small_objects, skeletonize
from skimage.measure import block_reduce
ROOT=Path(os.environ.get('STUDIO_ROOT') or Path(__file__).resolve().parents[2]).resolve()
STORE=Path(os.environ.get('STUDIO_STORE',str(ROOT/'outputs/analysis-studio-data'))); STORE.mkdir(parents=True,exist_ok=True)
from persistence import restore, persist, REPO as STATE_REPO
restore(STORE)
WEB=Path(__file__).parent/'web'
LOCK=threading.RLock(); POOL=ThreadPoolExecutor(max_workers=1); JOBS={}
DATA={'imop':dict(id='imop',name='iMOP • full field',path='data/kelvin-20260906/IMOP_Tuj1_G_DAPI_B.tif',spacing=[.445661272,.445661272,1],channels=['Tuj1 (presumed)','DAPI (presumed)'],calibrated=True)}
for p in sorted((ROOT/'data/set1').glob('*/*.czi')):
 key='hair-'+hashlib.sha256(str(p).encode()).hexdigest()[:10]
 DATA[key]=dict(id=key,name='Hair cells • '+p.parent.name+' / '+p.stem,path=str(p.relative_to(ROOT)))

if not (ROOT/DATA['imop']['path']).exists(): DATA.pop('imop')
for entry in (ROOT/'starter').glob('*.json'):
 d=json.loads(entry.read_text());DATA[d['id']]=d
from catalog import build
HIST,GEOMETRY=build(ROOT,DATA)
for entry in (STORE/'imports').glob('*/dataset.json'):
 d=json.loads(entry.read_text());d['path']=str(next(entry.parent.glob('source.*')));DATA[d['id']]=d

def atomic(path,obj):
 path=Path(path); temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,indent=2));temp.replace(path)
def metadata(key):
 d=DATA[key]
 if 'shape' not in d:
  p=ROOT/d['path']
  if p.suffix=='.czi':
   with czifile.CziFile(p) as f:
    axes=f.axes; dims=dict(zip(axes,f.shape)); xml=ET.fromstring(f.metadata())
    d['shape']=[dims.get(a,1) for a in 'ZCYX'];sc={n.attrib.get('Id'):float(n.findtext('Value'))*1e6 for n in xml.findall('.//Scaling/Items/Distance')}
    d['spacing']=[sc.get(a,1) for a in 'XYZ'];d['calibrated']=all(a in sc for a in 'XYZ');d['channels']=['Channel '+str(i+1) for i in range(d['shape'][1])]
  else:
   d['shape']=list(volume(key).shape)
   d.setdefault('channels',['Channel '+str(i+1) for i in range(d['shape'][1])]);d.setdefault('spacing',[1,1,1]);d.setdefault('calibrated',False)
  d['dtype']=str(volume(key).dtype)
 return d
@lru_cache(maxsize=1)
def volume(key):
 p=ROOT/DATA[key]['path']
 if p.suffix=='.czi':
  with czifile.CziFile(p) as f:
   if np.prod(f.shape)>int(os.environ.get('STUDIO_MAX_VOXELS','268435456')):raise ValueError('Scan exceeds demo voxel limit')
   a=f.asarray(); axes=f.axes
   for i in reversed(range(len(axes))):
    if axes[i] not in 'ZCYX':
     if a.shape[i]!=1:raise ValueError('Unsupported non-singleton axis '+axes[i])
     a=np.take(a,0,axis=i);axes=axes[:i]+axes[i+1:]
   return a.transpose([axes.index(x) for x in 'ZCYX'])
 with tifffile.TiffFile(p) as f:
  if np.prod(f.series[0].shape)>int(os.environ.get('STUDIO_MAX_VOXELS','268435456')):raise ValueError('Scan exceeds demo voxel limit')
  a=f.series[0].asarray();axes=DATA[key].get('axes') or f.series[0].axes
  if len(axes)!=a.ndim or len(set(axes))!=len(axes):raise ValueError('Axis order does not match this TIFF')
  if 'Y' not in axes or 'X' not in axes:raise ValueError('TIFF must contain Y and X axes')
  for i in reversed(range(len(axes))):
   if axes[i] not in 'ZCYX':
    if a.shape[i]!=1:raise ValueError('Ambiguous TIFF axes '+axes+'. Select its actual axis order when importing.')
    a=np.take(a,0,axis=i);axes=axes[:i]+axes[i+1:]
  for missing in 'ZC':
   if missing not in axes:a=np.expand_dims(a,0);axes=missing+axes
  return a.transpose([axes.index(x) for x in 'ZCYX'])
@lru_cache(maxsize=16)
def checksum(key):return hashlib.sha256((ROOT/DATA[key]['path']).read_bytes()).hexdigest()
def getrun(run):
 if run in HIST:return HIST[run],Path(HIST[run]['mask_path']).parent if HIST[run]['mask_path'] else ROOT
 if not run or any(c not in '0123456789abcdef-' for c in run):raise ValueError('Invalid run')
 p=STORE/'runs'/run/'run.json'
 if not p.exists():raise ValueError('Unknown completed run')
 return json.loads(p.read_text()),p.parent
@lru_cache(maxsize=4)
def run_array(run,kind):
 if kind not in ['processed','labels','ridge-response']:raise ValueError('Unknown result layer')
 r,p=getrun(run)
 if r.get('historical'):
  if kind=='processed':raise ValueError('Earlier run has labels only; select raw image with overlay')
  if not r['mask_path']:return np.zeros(r['shape'],np.uint16)
  a=tifffile.imread(r['mask_path']);return a[None] if a.ndim==2 else a
 a=tifffile.imread(p/(kind+'.tif'));return a[None] if a.ndim==2 else a
def array_for(key,ch,run=None,kind='processed'):
 if run:
  r,_=getrun(run)
  if r['dataset']!=key:raise ValueError('Run belongs to a different dataset')
  if r['channel']!=ch:raise ValueError('Run belongs to a different channel')
  return run_array(run,kind),r
 return volume(key)[:,ch],None

def number(v,lo,hi):
 n=float(v)
 if not np.isfinite(n) or n<lo or n>hi:raise ValueError('Parameter out of range')
 return n

def run_job(jid,params):
 job=JOBS[jid]
 try:
  job.update(status='running',message='Loading source volume')
  key=params['dataset'];d=metadata(key);ch=int(number(params.get('channel',0),0,d['shape'][1]-1));factor=int(params.get('factor',2))
  if factor not in [1,2,4]:raise ValueError('XY reduction must be 1, 2 or 4')
  mode=params.get('scope','volume');z=int(number(params.get('z',0),0,d['shape'][0]-1))
  if mode not in ['volume','projection','slice']:raise ValueError('Invalid processing scope')
  sample_count=(d['shape'][0] if mode=='volume' else 1)*(d['shape'][2]//factor)*(d['shape'][3]//factor)
  if sample_count>int(os.environ.get('STUDIO_PROCESS_VOXELS','268435456')):raise ValueError('Choose a lower XY resolution or a single slice: this volume exceeds the processing limit')
  parent=params.get('parent') or None
  if parent:
   old,_=getrun(parent)
   if old['dataset']!=key or old['scope']!='volume' or old['factor']!=factor or old['channel']!=ch or old.get('historical'):raise ValueError('Parent must be a current volume run on the same image, channel and XY reduction')
   a=run_array(parent,'processed').copy();ch=old['channel']
  else:
   a=volume(key)[z:z+1,ch].astype(np.float32) if mode=='slice' else volume(key)[:,ch].astype(np.float32)
   if factor>1:
    if a.shape[1]%factor or a.shape[2]%factor:raise ValueError('Image extent not divisible by reduction')
    a=block_reduce(a,(1,factor,factor),np.mean).astype(np.float32)
  if mode=='projection':a=a.max(axis=0,keepdims=True)
  if mode=='slice' and parent:a=a[z:z+1]
  if a.size>int(os.environ.get('STUDIO_PROCESS_VOXELS','268435456')):raise ValueError('Choose a lower XY resolution or a single slice: this volume exceeds the browser processing limit')
  from processing import process
  job['message']='Preprocessing and finding candidates'
  a,labels,score,threshold,effective=process(a,params,d,factor,lambda:job.get('cancel'))
  method=params.get('method','otsu');count=int(labels.max())
  if job.get('cancel'):job.update(status='canceled');return
  folder=STORE/'runs'/jid;folder.mkdir(parents=True,exist_ok=False)
  spacing=[d['spacing'][0]*factor,d['spacing'][1]*factor,d['spacing'][2]]
  tifffile.imwrite(folder/'processed.tif',a.astype(np.float32),ome=True,metadata=({'axes':'ZYX','PhysicalSizeX':spacing[0],'PhysicalSizeY':spacing[1],'PhysicalSizeZ':spacing[2],'PhysicalSizeXUnit':'µm','PhysicalSizeYUnit':'µm','PhysicalSizeZUnit':'µm'} if d.get('calibrated',True) else {'axes':'ZYX'}))
  if method=='sato':tifffile.imwrite(folder/'ridge-response.tif',np.asarray(score if score.ndim==3 else score[None],np.float32),ome=True,metadata=({'axes':'ZYX','PhysicalSizeX':spacing[0],'PhysicalSizeY':spacing[1],'PhysicalSizeZ':spacing[2],'PhysicalSizeXUnit':'µm','PhysicalSizeYUnit':'µm','PhysicalSizeZUnit':'µm'} if d.get('calibrated',True) else {'axes':'ZYX'}))
  tifffile.imwrite(folder/'labels.tif',labels,ome=True,metadata=({'axes':'ZYX','PhysicalSizeX':spacing[0],'PhysicalSizeY':spacing[1],'PhysicalSizeZ':spacing[2]} if d.get('calibrated',True) else {'axes':'ZYX'}))
  rows=[]
  if count:
   ids=np.arange(1,count+1);sizes=np.bincount(labels.ravel());centers=ndi.center_of_mass(np.ones(labels.shape),labels,ids)
   for i,(zz,yy,xx) in zip(ids,centers):rows.append(dict(id=int(i),voxels=int(sizes[i]),x=xx*factor+(factor-1)/2,y=yy*factor+(factor-1)/2,z=(zz if mode=='volume' else z if mode=='slice' else None),status='candidate'))
  with (folder/'objects.csv').open('w') as f:
   writer=csv.DictWriter(f,fieldnames=['id','voxels','x','y','z','status']);writer.writeheader();writer.writerows(rows)
  result=dict(id=jid,title=str(params.get('recipe_name') or method)[:100],dataset=key,source=DATA[key]['path'],sha256=checksum(key),created=time.time(),parameters=params,effective_parameters=effective,parent=parent,channel=ch,factor=factor,scope=mode,z=z,method=method,ridge_response=method=='sato',sato_mode=params.get('sato_mode','volume') if method=='sato' else None,spacing=spacing,shape=list(a.shape),objects=count,threshold=threshold,seconds=round(time.time()-job['created'],2),meaning='Connected network components, not neurons' if method=='sato' else 'Candidate regions, not reviewed cells',calibrated=d.get('calibrated',True),source_shape=d['shape'],transform={'scale':[factor,factor,1],'xy_translation':[(factor-1)/2]*2},software={'numpy':np.__version__,'tifffile':tifffile.__version__})
  atomic(folder/'run.json',result);persist(STORE,[folder]);job.update(status='completed',message='Saved result',result=result)
 except Exception as e:job.update(status='failed',error=str(e));traceback.print_exc()

def annotation_current(key):
 if key not in DATA:raise ValueError('Unknown dataset')
 p=STORE/'annotations'/key/'latest.json'
 return json.loads(p.read_text()) if p.exists() else {'revision':None,'items':[],'dataset':key}

def validate_items(key,items):
 d=metadata(key);nz,nc,h,w=d['shape']
 if len(items)>10000:raise ValueError('Too many annotations')
 for it in items:
  if it['type'] not in ['point','polygon','polyline']:raise ValueError('Unsupported annotation type')
  if it['domain'] not in ['slice','projection','volume']:raise ValueError('Invalid annotation domain')
  it['channel']=int(number(it['channel'],0,nc-1));it['z']=int(number(it['z'],0,nz-1));pts=it['points']
  minimum={'point':1,'polyline':2,'polygon':3}[it['type']]
  if len(pts)<minimum or len(pts)>20000:raise ValueError('Invalid point count')
  if it['domain']=='volume':
   if it['type']=='polygon':raise ValueError('3D polygons are not supported; use a slice outline')
   it['points']=[[number(x,0,w-1),number(y,0,h-1),number(z,0,nz-1)] for x,y,z in pts]
  else:it['points']=[[number(x,0,w-1),number(y,0,h-1)] for x,y in pts]
  it['label']=str(it.get('label',''))[:100]
  if it.get('status') not in ['unreviewed','accepted','uncertain','rejected']:raise ValueError('Invalid review state')
 return items

def save_annotations(body):
 key=body['dataset'];items=validate_items(key,body['items']);author=str(body.get('author','')).strip()
 if not author:raise ValueError('Enter an annotator name')
 with LOCK:
  current=annotation_current(key)
  if current['revision']!=body.get('base_revision'):raise ValueError('Revision conflict. Reload annotations before saving; another session has saved changes.')
  revision=uuid.uuid4().hex;folder=STORE/'annotations'/key/revision;folder.mkdir(parents=True)
  doc=dict(revision=revision,parent_revision=current['revision'],dataset=key,source=DATA[key]['path'],sha256=checksum(key),shape=metadata(key)['shape'],spacing=metadata(key)['spacing'],calibrated=metadata(key).get('calibrated',True),original_source=metadata(key).get('original_source'),crop_origin=metadata(key).get('crop_origin'),coordinate_system='Native source XY pixels; zero-based Z/C. Projection annotations have no unique Z.',author=author,created=time.time(),items=items)
  atomic(folder/'annotations.json',doc)
  rois=[];rows=[];d=metadata(key)
  for i,it in enumerate(items):
   if it['domain']=='volume':
    pts=np.asarray(it['points'])*d['spacing']
    length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum()) if it['type']=='polyline' else ''
    rows.append(dict(id=i+1,type=it['type'],domain='volume',channel=it['channel']+1,z='',status=it['status'],length_2d_um='',length_3d_um=length if d.get('calibrated',True) else '',area_2d_um2='',note=it.get('note',''),label=it.get('label','')))
    continue
   roi=roifile.ImagejRoi.frompoints(np.asarray(it['points'],np.float32),name=f'{i+1:04d}_{it["type"]}_{it["status"]}',c=it['channel'],z=(it['z'] if it['domain']=='slice' else None),t=0)
   roi.roitype={'point':roifile.ROI_TYPE.POINT,'polygon':roifile.ROI_TYPE.POLYGON,'polyline':roifile.ROI_TYPE.POLYLINE}[it['type']]
   rois.append(roi)
   pts=np.asarray(it['points'])*d['spacing'][:2]
   length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum()) if it['type']=='polyline' else ''
   area=float(abs(np.dot(pts[:,0],np.roll(pts[:,1],1))-np.dot(pts[:,1],np.roll(pts[:,0],1)))/2) if it['type']=='polygon' else ''
   rows.append(dict(id=i+1,type=it['type'],domain=it['domain'],channel=it['channel']+1,z=it['z']+1 if it['domain']=='slice' else '',status=it['status'],length_2d_um=length if d.get('calibrated',True) else '',area_2d_um2=area if d.get('calibrated',True) else '',note=it.get('note',''),label=it.get('label',''),length_3d_um=''))
  if rois:roifile.roiwrite(folder/'RoiSet.zip',rois,mode='w')
  else:
   with zipfile.ZipFile(folder/'RoiSet.zip','w'):pass
  with (folder/'measurements.csv').open('w') as f:
   writer=csv.DictWriter(f,fieldnames=['id','type','domain','channel','z','status','length_2d_um','area_2d_um2','note','label','length_3d_um']);writer.writeheader();writer.writerows(rows)
  with zipfile.ZipFile(folder/'annotation-package.zip','w',zipfile.ZIP_DEFLATED) as archive:
   for name in ['annotations.json','RoiSet.zip','measurements.csv']:archive.write(folder/name,name)
  # Mirror the immutable revision and latest pointer together, roll back pointer on failure.
  latest=folder.parent/'latest.json';old=latest.read_bytes() if latest.exists() else None
  atomic(latest,doc)
  try:persist(STORE,[folder,latest])
  except Exception:
   if old is None:latest.unlink(missing_ok=True)
   else:latest.write_bytes(old)
   raise
  return doc

def png_view(q):
 key=q['dataset'];d=metadata(key);ch=int(number(q.get('channel',0),0,d['shape'][1]-1));mode=q.get('view','slice');z=int(number(q.get('z',0),0,d['shape'][0]-1));run=q.get('run');overlay=q.get('overlay')
 a,r=array_for(key,ch,run,q.get('kind','processed'))
 if r and r['scope']=='slice' and (mode!='slice' or z!=r['z']):raise ValueError('This run only covers source plane '+str(r['z']+1))
 if r and r['scope']=='projection' and mode!='projection':raise ValueError('Projection-only run cannot be displayed on an acquired slice')
 plane=a.max(0) if mode=='projection' else a[z if not r or r['scope']=='volume' else 0]
 if overlay:
  a,r=array_for(key,ch,overlay,'labels')
  if r['scope']=='slice' and (mode!='slice' or z!=r['z']):raise ValueError('Overlay is on a different plane')
  if r['scope']=='projection' and mode!='projection':raise ValueError('2D projection overlays cannot be placed on a source slice')
  if mode=='projection':
   # Choose the first occupied label along Z, never the numeric maximum label ID.
   idx=(a>0).argmax(0);plane=np.take_along_axis(a,idx[None],0)[0]
  else:plane=a[z if r['scope']=='volume' else 0]
  ids=plane.astype(np.uint32);rgba=np.zeros((*ids.shape,4),np.uint8);valid=ids>0
  if q.get('style')=='outline':valid &= find_boundaries(ids,mode='inner')
  rgba[:,:,0]=(ids*67%160+80);rgba[:,:,1]=(ids*113%160+80);rgba[:,:,2]=(ids*41%160+80);rgba[:,:,3]=valid*190
  img=Image.fromarray(rgba,'RGBA').resize((d['shape'][3],d['shape'][2]),Image.Resampling.NEAREST)
 else:
  low,high=np.percentile(a,[1,99.7]);high=max(high,low+1e-9)
  gain=number(q.get('gain',1),.1,10);gray=np.uint8(np.clip((plane-low)/(high-low)*255*gain,0,255));img=Image.fromarray(gray,'L').resize((d['shape'][3],d['shape'][2]),Image.Resampling.BILINEAR)
 b=io.BytesIO();img.save(b,format='PNG');return b.getvalue()

def points_view(q):
 key=q['dataset'];d=metadata(key);a,r=array_for(key,int(q.get('channel',0)),q.get('run'),q.get('kind','processed'))
 if r and r['scope']!='volume':raise ValueError('3D requires a volume run')
 factor=r['factor'] if r else 1;stride=max(1,int(np.ceil(a.shape[1]/256)));b=a[:,::stride,::stride];lo,hi=np.percentile(b,[50,99.7]);coords=np.argwhere(b>lo+.2*(hi-lo));coords=coords[::max(1,int(np.ceil(len(coords)/50000)))];values=np.clip((b[tuple(coords.T)]-lo)/max(hi-lo,1e-9),0,1)
 points=[[float(x*stride*factor+(factor-1)/2),float(y*stride*factor+(factor-1)/2),int(z),round(float(v),3),0] for (z,y,x),v in zip(coords,values)]
 if q.get('overlay'):
  mask,mr=array_for(key,int(q.get('channel',0)),q['overlay'],'labels')
  if mr['scope']!='volume':raise ValueError('3D overlays require volumetric labels')
  for pt in points:
   xx=min(mask.shape[2]-1,int(pt[0]/mr['factor']));yy=min(mask.shape[1]-1,int(pt[1]/mr['factor']));pt[4]=int(mask[pt[2],yy,xx])
 return dict(points=points,spacing=d['spacing'],shape=d['shape'],note='Sampled fluorescence points; masks color visible source samples, not full surfaces')

class Handler(BaseHTTPRequestHandler):
 def valid_host(self):
  allowed={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
  allowed.update(filter(None,os.environ.get('STUDIO_HOSTS','').split(',')))
  if os.environ.get('SPACE_HOST'):allowed.add(os.environ['SPACE_HOST'])
  return self.headers.get('Host') in allowed

 def send(self,obj,status=200,ctype='application/json'):
  data=obj if isinstance(obj,bytes) else json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  try:
   if not self.valid_host():raise ValueError('Invalid host')
   parsed=urlparse(self.path);path=parsed.path;q={k:v[0] for k,v in parse_qs(parsed.query).items()}
   if path=='/api/config':return self.send(dict(shared=bool(os.environ.get('STUDIO_DEMO')),persistent=bool(STATE_REPO),storage='HF dataset' if STATE_REPO else 'local disk',process_limit=int(os.environ.get('STUDIO_PROCESS_VOXELS','268435456')),upload_limit_mb=int(os.environ.get('STUDIO_UPLOAD_MB','1024'))))
   if path=='/api/recipes':return self.send([json.loads(p.read_text()) for p in (STORE/'recipes').glob('*.json')])
   if path=='/api/datasets':return self.send([dict(id=d['id'],name=d['name']) for d in DATA.values()])
   if path=='/api/dataset':return self.send(metadata(q['id']))
   if path in ['/api/measurements','/api/object-location','/api/measurements.csv','/api/count-summary.json']:
    from measurements import table, locate, csv_export, summary_export
    if path=='/api/measurements.csv':return self.send(csv_export(q),ctype='text/csv; charset=utf-8')
    if path=='/api/count-summary.json':return self.send(summary_export(q),ctype='application/json')
    return self.send(locate(q) if path=='/api/object-location' else table(q))
   if path=='/api/review':
    from review import inspect_volume
    return self.send(inspect_volume(q))
   if path=='/api/image':return self.send(png_view(q),ctype='image/png')
   if path=='/api/probe':
    key=q['dataset'];d=metadata(key);x=int(number(q['x'],0,d['shape'][3]-1));y=int(number(q['y'],0,d['shape'][2]-1));z=int(number(q['z'],0,d['shape'][0]-1));ch=int(number(q['channel'],0,d['shape'][1]-1));a=volume(key)[:,ch,y,x];result=dict(intensity=float(a.max() if q.get('view')=='projection' else a[z]),objects=[])
    if q.get('view')=='projection':result['peak_z']=int(a.argmax())
    if q.get('run'):
     mask,r=array_for(key,ch,q['run'],'labels');xx=min(mask.shape[2]-1,int(x/r['factor']));yy=min(mask.shape[1]-1,int(y/r['factor']))
     if q.get('view')=='projection':ids=np.unique(mask[:,yy,xx])
     elif r['scope']=='volume':ids=[mask[z,yy,xx]]
     elif r['scope']=='slice' and r['z']==z:ids=[mask[0,yy,xx]]
     else:ids=[]
     result['objects']=[int(i) for i in ids if i]
    return self.send(result)
   if path=='/api/points':return self.send(points_view(q))
   if path=='/api/jobs':return self.send(list(JOBS.values()))
   if path=='/api/result-file':
    r,folder=getrun(q['run']);kind=q.get('kind','labels')
    if kind=='geometry':return self.send(GEOMETRY.get(q['run'],{}))
    if kind=='corrected-labels':
     from measurements import context, current, protocol_current, _pinned
     from corrections import current as correction_current
     context(q)
     with LOCK:
      review=current(folder);correction=correction_current(folder);protocol=protocol_current(folder)
      _pinned(q,review,correction,protocol)
      file=folder/'corrections'/(correction['revision']+'.tif') if correction['revision'] else folder/'labels.tif'
      return self.send(file.read_bytes(),ctype='application/octet-stream')
    if kind!='labels':raise ValueError('Unsupported result artifact')
    file=Path(r['mask_path']) if r.get('historical') and r.get('mask_path') else folder/'labels.tif'
    if not file.is_file():raise ValueError('This result contains geometry, not labels')
    return self.send(file.read_bytes(),ctype='application/octet-stream')
   if path=='/api/geometry':
    r,_=getrun(q['run'])
    if r['dataset']!=q['dataset']:raise ValueError('Result belongs to a different image')
    return self.send(GEOMETRY.get(q['run'],{}))
   if path=='/api/runs':return self.send([r for r in HIST.values() if r['dataset']==q['dataset']]+[json.loads(p.read_text()) for p in sorted((STORE/'runs').glob('*/run.json')) if json.loads(p.read_text())['dataset']==q['dataset']])
   if path=='/api/annotations':return self.send(annotation_current(q['dataset']))
   if path=='/api/download':
    base=(STORE/q['path']).resolve()
    if not base.is_relative_to(STORE.resolve()) or not base.is_file():raise ValueError('Unknown artifact')
    return self.send(base.read_bytes(),ctype='application/octet-stream')
   if path.count('/')==1 and path.endswith(('.js','.css')) and (WEB/path[1:]).is_file():
    return self.send((WEB/path[1:]).read_bytes(),ctype='application/javascript' if path.endswith('.js') else 'text/css')
   files={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/simple.js':'simple.js','/studio.js':'studio.js','/studio.css':'studio.css'}
   if path in files:return self.send((WEB/files[path]).read_bytes(),ctype={'/':'text/html','/app.js':'application/javascript','/style.css':'text/css','/simple.js':'application/javascript','/studio.js':'application/javascript','/studio.css':'text/css'}[path])
   self.send({'error':'Not found'},404)
  except Exception as e:self.send({'error':str(e)},400)
 def do_POST(self):
  try:
   if not self.valid_host():raise ValueError('Invalid host')
   if self.headers.get('X-Studio-Request')!='1':raise ValueError('Missing request header')
   origin=self.headers.get('Origin')
   if origin and origin not in ['http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')]:raise ValueError('Cross-origin request rejected')
   size=int(self.headers.get('Content-Length',0))
   if urlparse(self.path).path=='/api/inspect-source':
    if size<=0 or size>int(os.environ.get('STUDIO_UPLOAD_MB','1024'))*1048576:raise ValueError('File exceeds upload limit')
    raw=io.BytesIO(self.rfile.read(size));q={k:v[0] for k,v in parse_qs(urlparse(self.path).query).items()}
    if q.get('name','').lower().endswith('.czi'):
     with czifile.CziFile(raw) as f:info=dict(axes=f.axes,shape=list(f.shape),dtype=str(f.dtype))
    else:
     with tifffile.TiffFile(raw) as f:info=dict(axes=f.series[0].axes,shape=list(f.series[0].shape),dtype=str(f.series[0].dtype),series=len(f.series))
    return self.send(info)
   if urlparse(self.path).path=='/api/import-source':
    if size<=0 or size>int(os.environ.get('STUDIO_UPLOAD_MB','1024'))*1048576:raise ValueError('File exceeds upload size limit')
    if sum(p.stat().st_size for p in STORE.rglob('*') if p.is_file())+size>int(os.environ.get('STUDIO_STORE_MB','10240'))*1048576:raise ValueError('Demo storage full; export your work and contact the host')
    q={k:v[0] for k,v in parse_qs(urlparse(self.path).query).items()};name=Path(q.get('name','image.tif')).name;ext=Path(name).suffix.lower()
    if ext not in ['.tif','.tiff','.czi']:raise ValueError('Import TIFF or CZI files')
    key='import-'+uuid.uuid4().hex;folder=STORE/'imports'/key;folder.mkdir(parents=True);dest=folder/('source'+ext)
    remaining=size
    with dest.open('wb') as f:
     while remaining:
      chunk=self.rfile.read(min(1048576,remaining))
      if not chunk:raise ValueError('Upload interrupted')
      f.write(chunk);remaining-=len(chunk)
    d=dict(id=key,name=name,path=str(dest),axes=q.get('axes') or None,calibrated=False,spacing=[1,1,1])
    if q.get('xy') and q.get('z'):
     xy=number(q['xy'],.000001,10000);z=number(q['z'],.000001,10000);d.update(spacing=[xy,xy,z],calibrated=True)
    DATA[key]=d
    try:
     d=metadata(key)
     if not np.issubdtype(volume(key).dtype,np.number):raise ValueError('Unsupported pixel data type')
     atomic(folder/'dataset.json',d);persist(STORE,[folder])
    except Exception:
     DATA.pop(key,None);raise
    return self.send(d)
   if size>8_000_000:raise ValueError('Request too large')
   body=json.loads(self.rfile.read(size));path=urlparse(self.path).path
   if path=='/api/object-decision':
    from measurements import save
    return self.send(save(body))
   if path=='/api/count-protocol':
    from measurements import save_protocol
    return self.send(save_protocol(body))
   if path in ('/api/correction-preview','/api/correction-save'):
    from corrections import preview,save
    return self.send(preview(body) if path.endswith('preview') else save(body))
   if path=='/api/preview':
    from experiments import preview
    return self.send(preview(body))
   if path=='/api/compare':
    from experiments import compare
    return self.send(compare(body))
   if path=='/api/recipes':
    name=str(body.get('name','')).strip()[:100]
    if not name:raise ValueError('Name your recipe')
    recipe=dict(id=uuid.uuid4().hex,name=name,cell_type=str(body.get('cell_type',''))[:100],parameters=body.get('parameters',{}),created=time.time())
    if recipe['parameters'].get('method') not in ['otsu','watershed','sato','preprocess']:raise ValueError('Unsupported method')
    folder=STORE/'recipes';folder.mkdir(exist_ok=True);path=folder/(recipe['id']+'.json');atomic(path,recipe)
    try:persist(STORE,[path])
    except Exception:path.unlink();raise
    return self.send(recipe)
   if path=='/api/run':
    if body['dataset'] not in DATA:raise ValueError('Unknown dataset')
    if len([j for j in JOBS.values() if j['status'] in ['queued','running']])>=4:raise ValueError('Four runs already waiting; try again when one finishes')
    jid=uuid.uuid4().hex;JOBS[jid]=dict(id=jid,status='queued',created=time.time(),dataset=body['dataset']);POOL.submit(run_job,jid,body);return self.send(JOBS[jid])
   if path=='/api/cancel':
    job=JOBS[body['id']]
    if job['status'] in ['queued','running']:job['cancel']=True;job['message']='Cancel requested; waiting for current operation'
    return self.send(job)
   if path=='/api/annotations':return self.send(save_annotations(body))
   if path=='/api/import-rois':
    key=body['dataset'];data=base64.b64decode(body['data']);items=[]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
     infos=archive.infolist()
     if sum(i.file_size for i in infos)>20_000_000 or len(infos)>10000:raise ValueError('ROI archive too large')
     for info in infos:
      if not info.filename.endswith('.roi'):continue
      roi=roifile.ImagejRoi.frombytes(archive.read(info));kind={roifile.ROI_TYPE.POINT:'point',roifile.ROI_TYPE.POLYGON:'polygon',roifile.ROI_TYPE.FREEHAND:'polygon',roifile.ROI_TYPE.POLYLINE:'polyline',roifile.ROI_TYPE.FREELINE:'polyline'}.get(roi.roitype)
      if kind is None:raise ValueError('Unsupported ROI geometry in '+info.filename)
      if roi.t_position>1:raise ValueError('Time series ROI unsupported')
      if roi.position and not roi.z_position:raise ValueError('Legacy stack positions require explicit C/Z mapping')
      items.append(dict(id=uuid.uuid4().hex,type=kind,domain='slice' if roi.z_position else 'projection',channel=max(0,roi.c_position-1),z=max(0,roi.z_position-1),points=roi.coordinates().tolist(),status='unreviewed',note=roi.name))
    return self.send({'items':validate_items(key,items)})
   self.send({'error':'Not found'},404)
  except Exception as e:self.send({'error':str(e)},400)
 def log_message(self,fmt,*args):
  if args and 'api/image' in str(args[0]):return
  super().log_message(fmt,*args)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8777);args=p.parse_args();print('Studio: http://127.0.0.1:'+str(args.port),flush=True);ThreadingHTTPServer((os.environ.get('STUDIO_BIND','127.0.0.1'),args.port),Handler).serve_forever()
