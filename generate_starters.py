"""Deterministic synthetic fluorescence phantoms. No lab/patient images."""
import json
from pathlib import Path
import numpy as np
import tifffile
from scipy.ndimage import gaussian_filter
folder=Path(__file__).parent/'starter';folder.mkdir(exist_ok=True)
rng=np.random.default_rng(17)
z,y,x=np.mgrid[:24,:256,:256]
for kind in ['cells','neurites']:
    a=np.zeros((24,2,256,256),np.float32)
    if kind=='cells':
        for row in range(3):
            for col in range(6):
                cx=28+col*39+rng.uniform(-4,4);cy=48+row*72+rng.uniform(-8,8);cz=rng.uniform(8,15)
                r=((x-cx)/rng.uniform(10,15))**2+((y-cy)/rng.uniform(16,23))**2+((z-cz)/rng.uniform(3,5))**2
                a[:,0]+=150*np.exp(-r*1.5)
                r=((x-cx)/6)**2+((y-cy)/7)**2+((z-cz)/2.5)**2
                a[:,1]+=210*np.exp(-r*1.5)
    else:
        for n in range(9):
            cx=rng.integers(25,230);cy=rng.integers(25,230);cz=rng.integers(5,19)
            a[:,1]+=190*np.exp(-(((x-cx)/5)**2+((y-cy)/6)**2+((z-cz)/2)**2))
            a[:,0]+=130*np.exp(-(((x-cx)/9)**2+((y-cy)/10)**2+((z-cz)/3)**2))
            for branch in range(3):
                theta=rng.uniform(0,np.pi*2)
                for t in np.linspace(0,90,200):
                    xx=int(cx+np.cos(theta)*t+np.sin(t/18)*8);yy=int(cy+np.sin(theta)*t);zz=int(np.clip(cz+np.sin(t/25)*3,0,23))
                    if 0<=xx<256 and 0<=yy<256:a[zz,0,yy,xx]=250
        a[:,0]=gaussian_filter(a[:,0],(.5,.65,.65))*1.3
    a=np.clip(a+rng.poisson(1.5,size=a.shape),0,255).astype(np.uint8)
    file=folder/(kind+'.ome.tif');tifffile.imwrite(file,a,ome=True,metadata={'axes':'ZCYX','PhysicalSizeX':.5,'PhysicalSizeY':.5,'PhysicalSizeZ':1.,'PhysicalSizeXUnit':'µm','PhysicalSizeYUnit':'µm','PhysicalSizeZUnit':'µm'},compression='deflate')
    (folder/(kind+'.json')).write_text(json.dumps({'id':'demo-'+kind,'name':'Synthetic · '+('cell bodies & nuclei' if kind=='cells' else 'neurite network'),'path':'starter/'+file.name,'axes':'ZCYX','spacing':[.5,.5,1.],'calibrated':True,'channels':['Synthetic signal','Synthetic nuclei'],'synthetic':True},indent=2))
