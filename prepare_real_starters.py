"""Package user-authorized real scans without resampling or dropping channels/planes."""
import sys,json,hashlib
from pathlib import Path
import tifffile,czifile,numpy as np
root=Path(sys.argv[1]).resolve();folder=Path(__file__).parent/'starter'
items=[('imop','iMOP · neurons · native 14Z',root/'data/kelvin-20260906/IMOP_Tuj1_G_DAPI_B.tif',[.445661272,.445661272,1],['Tuj1 (presumed)','DAPI (presumed)']),('hair-control','Hair cells · Control Mid-1 · native 40Z',root/'data/set1/PLPCre-GAP-Control/Mid-1_x20x2.czi',[.155981445,.155981445,1],['Channel 1','Channel 2','Channel 3','Channel 4'])]
for key,name,source,spacing,channels in items:
 if source.suffix=='.czi':
  with czifile.CziFile(source) as f:
   a=f.asarray();axes=f.axes
   for i in reversed(range(len(axes))):
    if axes[i] not in 'ZCYX':
     assert a.shape[i]==1;a=np.take(a,0,axis=i);axes=axes[:i]+axes[i+1:]
   a=a.transpose([axes.index(x) for x in 'ZCYX'])
 else:a=tifffile.imread(source)
 dest=folder/(key+'.ome.tif')
 tifffile.imwrite(dest,a,ome=True,metadata={'axes':'ZCYX','PhysicalSizeX':spacing[0],'PhysicalSizeY':spacing[1],'PhysicalSizeZ':spacing[2],'PhysicalSizeXUnit':'µm','PhysicalSizeYUnit':'µm','PhysicalSizeZUnit':'µm'},compression='deflate',maxworkers=1)
 assert np.array_equal(tifffile.imread(dest),a)
 d=dict(id=key,name=name,path='starter/'+dest.name,axes='ZCYX',shape=list(a.shape),dtype=str(a.dtype),spacing=spacing,calibrated=True,channels=channels,original_source=source.name,original_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),sha256_packaged=hashlib.sha256(dest.read_bytes()).hexdigest(),pixel_transform='Identity: all channels, full XY, all acquired Z planes; lossless TIFF container conversion only',synthetic=False)
 (folder/(key+'.json')).write_text(json.dumps(d,indent=2));print(name,list(a.shape),round(dest.stat().st_size/1048576,2),'MB; pixel equality verified')
