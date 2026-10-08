"""Run the studio's five neurite techniques on real traced fields + 2D/3D fixtures.

Sparse preexisting ImageJ paths provide path-support diagnostics, never a false
positive denominator or complete neuron identities. All fixed settings are
recorded before evaluation; this is exploratory comparison, not held-out tuning.
"""
import argparse
import hashlib
import html
import json
import sys
import time
from pathlib import Path
import numpy as np
import roifile
import tifffile
import scipy
import skimage
from scipy import ndimage as ndi
from skimage.measure import block_reduce
from PIL import Image, ImageDraw

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'app'))
from processing import process
from neurites import METHODS, measure, csv_bytes, NETWORK_FIELDS, BRANCH_FIELDS


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def sampled_path(coordinates,shape):
    points=[]
    for start,end in zip(coordinates[:-1],coordinates[1:]):
        steps=max(1,int(np.ceil(np.linalg.norm(end-start)*2)))
        points.append(start[None]+np.linspace(0,1,steps,endpoint=False)[:,None]*(end-start))
    points.append(coordinates[-1:]);xy=np.rint(np.concatenate(points)).astype(int)
    xy[:,0]=np.clip(xy[:,0],0,shape[1]-1);xy[:,1]=np.clip(xy[:,1],0,shape[0]-1)
    return xy


def support(skeleton,paths):
    distance=ndi.distance_transform_edt(~skeleton)
    result={}
    for radius in (1,2,3):
        fractions=[float(np.mean(distance[xy[:,1],xy[:,0]]<=radius)) for xy in paths]
        result[str(radius)]=dict(mean_per_trace=float(np.mean(fractions)),median_per_trace=float(np.median(fractions)),
            sampled_point_fraction=sum(int(np.count_nonzero(distance[xy[:,1],xy[:,0]]<=radius)) for xy in paths)/sum(len(xy) for xy in paths),
            traces_at_least_80pct=int(np.count_nonzero(np.asarray(fractions)>=.8)))
    return result


def preview_panel(image,skeleton,trace_mask=None):
    high=max(float(np.percentile(image,99.8)),1e-6)
    gray=np.uint8(np.clip(image/high,0,1)*255)
    rgb=np.stack([gray]*3,axis=-1);rgb[skeleton]=[255,174,58]
    if trace_mask is not None:rgb[trace_mask]=[82,222,231]
    return Image.fromarray(rgb).resize((384,384))


def save_result(out,name,array,params,metadata,factor,paths=None,trace_mask=None):
    started=time.perf_counter();processed,labels,score,threshold,effective=process(array,params,metadata,factor)
    spacing=metadata['spacing'];spacing_zyx=[spacing[2],spacing[1]*factor,spacing[0]*factor]
    skeleton,rows,branches,summary=measure(labels,spacing_zyx,metadata['calibrated'],effective['neurite_min_branch_length'],effective['neurite_pruning_units']=='µm')
    record=dict(parameters=params,effective_parameters=effective,threshold=threshold,foreground_fraction=float(np.mean(labels>0)),
                network_measurements=summary,seconds=round(time.perf_counter()-started,3))
    if paths is not None:record['trace_support']=support(skeleton[0],paths)
    if params.get('variant')=='base':
        tifffile.imwrite(out/(name+'-skeleton.tif'),skeleton.astype(np.uint8),metadata={'axes':'ZYX'})
        (out/(name+'-networks.csv')).write_bytes(csv_bytes(rows,NETWORK_FIELDS));(out/(name+'-branches.csv')).write_bytes(csv_bytes(branches,BRANCH_FIELDS))
    return record,skeleton


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=REPO.parent)
    parser.add_argument('--output',type=Path,default=REPO.parent/'outputs'/'neurite-comparison-20261003')
    parser.add_argument('--resume',action='store_true',help='Resume completed samples from the output checkpoint')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    report=dict(scope='Five actual studio techniques; fixed threshold/preprocessing sensitivity variants; sparse real traces plus simulated ground truth and a real 14Z field.',
        metric='Real traced fields: fraction of <=0.5px sampled ImageJ path points within 1/2/3 working pixels of a candidate skeleton. Unannotated pixels are not assumed negative. Synthetic: known unique centerline sample support only.',
        limitation='Network skeleton length includes remaining soma skeleton and joins at crossings. No automated neuron ownership. Sparse path support is not precision, biological recall, or an independent whole-neuron accuracy result.',
        sources=[dict(title='scikit-image ridge filters',url='https://scikit-image.org/docs/stable/api/skimage.filters.html'),dict(title='scikit-image skeletonize',url='https://scikit-image.org/docs/stable/api/skimage.morphology.html#skimage.morphology.skeletonize')],
        software=dict(numpy=np.__version__,tifffile=tifffile.__version__,scipy=scipy.__version__,skimage=skimage.__version__,python=sys.version.split()[0]),
        implementation_sha256={name:digest(REPO/'app'/name) for name in ['neurites.py','processing.py']},samples=[])
    checkpoint=out/'checkpoint.json'
    if args.resume and checkpoint.is_file():
        report=json.loads(checkpoint.read_text())
    report.setdefault('implementation_sha256',{name:digest(REPO/'app'/name) for name in ['neurites.py','processing.py']})
    report['software'].update(scipy=scipy.__version__,skimage=skimage.__version__,python=sys.version.split()[0])
    completed={sample['source'] for sample in report['samples']}
    def save_checkpoint():
        checkpoint.write_text(json.dumps(report,indent=2)+'\n')
    box=args.root/'work'/'box-tracing-20260927';workbook=json.loads((box/'workbook_lengths.json').read_text())
    for stem in ['iMOP_D7_neuron',"Sox11_5'dCas9","Sox11_5'mecp2"]:
        if stem in completed:continue
        image_path=box/(stem+'_Tuj1_G_DAPI_B.tif');roi_path=box/(stem+'_RoiSet.zip')
        with tifffile.TiffFile(image_path) as file:
            image=file.series[0].asarray()[0].astype(np.float32)/255
            xr=file.pages[0].tags['XResolution'].value;yr=file.pages[0].tags['YResolution'].value
            spacing=[xr[1]/xr[0],yr[1]/yr[0],1]
            if (file.imagej_metadata or {}).get('unit')!='micron':raise ValueError('Unverified Box calibration')
        metadata=dict(spacing=spacing,calibrated=True);rois=roifile.roiread(roi_path);paths=[sampled_path(r.coordinates(),image.shape) for r in rois]
        lengths=[float(np.linalg.norm(np.diff(r.coordinates()*np.asarray(spacing[:2]),axis=0),axis=1).sum()) for r in rois]
        errors=[abs(a-b) for a,b in zip(lengths,workbook[stem])]
        trace_mask=np.zeros(image.shape,bool)
        for xy in paths:trace_mask[xy[:,1],xy[:,0]]=True
        record=dict(source=stem,kind='real_sparse_2d',shape=list(image.shape),image_sha256=digest(image_path),roi_sha256=digest(roi_path),
                    spacing_xyz_um=spacing,trace_count=len(rois),manual_trace_length_um=sum(lengths),roi_workbook_max_error_um=max(errors),methods={})
        montage=Image.new('RGB',(384*3,420*2),(13,17,23));draw=ImageDraw.Draw(montage)
        montage.paste(preview_panel(image,np.zeros_like(trace_mask),trace_mask),(0,24));draw.text((8,5),stem+' / cyan: supplied paths',fill='white')
        for i,method in enumerate(METHODS):
            for variant,kwargs in [('base',{}),('lower_threshold',dict(threshold=.7)),('background',dict(sigma=.6,background=12,threshold=.85))]:
                params=dict(method=method,scope='slice',min_size=30,ridge_sigmas=[1,2,3],neurite_mode='slice',variant=variant,**kwargs)
                name=stem.replace("'",'')+'-'+method+'-'+variant
                result,skeleton=save_result(out,name,image[None],params,metadata,1,paths,trace_mask)
                record['methods'][method+'/'+variant]=result
                if variant=='base':
                    index=i+1;x=(index%3)*384;y=(index//3)*420
                    montage.paste(preview_panel(image,skeleton[0],trace_mask),(x,y+24));draw.text((x+8,y+5),method.replace('neurite_','')+' / orange: skeleton',fill='white')
                    draw.text((x+8,y+407),f"2px path support {result['trace_support']['2']['sampled_point_fraction']:.1%}",fill='white')
            print(stem,method,round(record['methods'][method+'/base']['trace_support']['2']['sampled_point_fraction'],4),flush=True)
        montage.save(out/(stem.replace("'",'')+'-comparison.png'));report['samples'].append(record);save_checkpoint()
    # Preserve the failed naive adaptive baseline as an explicit noise diagnostic.
    for record in report['samples']:
        if record['kind']!='real_sparse_2d' or 'neurite_adaptive/no_floor' in record['methods']:continue
        stem=record['source'];image=tifffile.imread(box/(stem+'_Tuj1_G_DAPI_B.tif'))[0].astype(np.float32)/255
        paths=[sampled_path(r.coordinates(),image.shape) for r in roifile.roiread(box/(stem+'_RoiSet.zip'))]
        metadata=dict(spacing=record['spacing_xyz_um'],calibrated=True)
        params=dict(method='neurite_adaptive',scope='slice',min_size=30,neurite_mode='slice',variant='no_floor',adaptive_floor=0)
        result,_=save_result(out,stem.replace("'",'')+'-neurite_adaptive-no_floor',image[None],params,metadata,1,paths)
        record['methods']['neurite_adaptive/no_floor']=result;save_checkpoint()
    for name in ('neurons_crossing_2d','neurons_crossing_3d'):
        if name in completed:continue
        directory=REPO/'examples'/'synthetic-v3'/name;truth=json.loads((directory/'truth.json').read_text());image_path=directory/(name+'.ome.tif')
        with tifffile.TiffFile(image_path) as f:
            a=f.series[0].asarray();axes=f.series[0].axes
        if axes=='YX':a=a[None]
        elif axes=='ZYX':pass
        elif axes=='CYX':a=a[None,0]
        elif axes=='ZCYX':a=a[:,0]
        else:raise ValueError(f'Unexpected fixture axes: {axes}')
        metadata=dict(spacing=truth['simulated_spacing_xyz_um'],calibrated=True)
        centers=np.unique(np.concatenate([b['samples_zyx'] for g in truth['neurite_graphs'] for b in g['branches']]),axis=0)
        record=dict(source=name,kind='synthetic',image_sha256=digest(image_path),truth_sha256=digest(directory/'truth.json'),shape=list(a.shape),spacing_xyz_um=metadata['spacing'],methods={})
        for method in METHODS:
            params=dict(method=method,scope='volume',min_size=5,ridge_sigmas=[1,2,3],neurite_mode='slice',variant='base')
            result,skeleton=save_result(out,name+'-'+method,a,params,metadata,1)
            distance=ndi.distance_transform_edt(~skeleton)
            result['known_unique_centerline_support_2_grid_px']=float(np.mean(distance[tuple(centers.T)]<=2))
            record['methods'][method]=result
        report['samples'].append(record);save_checkpoint();print(name,'completed',flush=True)
    image_path=args.root/'data'/'kelvin-20260906'/'IMOP_Tuj1_G_DAPI_B.tif'
    with tifffile.TiffFile(image_path) as f:
        a=f.series[0].asarray();axes=f.series[0].axes
    if axes=='ZCYX':a=a[:,0]
    elif axes=='CZYX':a=a[0]
    else:raise ValueError(f'Unexpected iMOP axes: {axes}')
    a=block_reduce(a,(1,2,2),np.mean).astype(np.float32)
    record=dict(source='iMOP_native14Z',kind='real_untraced_3d',image_sha256=digest(image_path),shape=list(a.shape),factor=2,methods={})
    metadata=dict(spacing=[.445661272,.445661272,1],calibrated=True)
    for method in (() if 'iMOP_native14Z' in completed else METHODS):
        params=dict(method=method,scope='volume',min_size=30,ridge_sigmas=[1,2,3],neurite_mode='slice',variant='base')
        result,_=save_result(out,'iMOP_native14Z-'+method,a,params,metadata,2)
        record['methods'][method]=result;print('iMOP_native14Z',method,result['network_measurements']['total_length_um'],flush=True)
    if 'iMOP_native14Z' not in completed:report['samples'].append(record)
    report['run_count']=sum(len(s['methods']) for s in report['samples']);save_checkpoint()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# Neurite technique comparison','',f"Completed {report['run_count']} local runs with the studio processing code.",'',report['metric'],'',report['limitation'],'',
        '| Traced field | Technique | Base support at 2px | Lower threshold | Background + smoothing | Base network length (µm) |','|---|---|---:|---:|---:|---:|']
    for sample in report['samples'][:3]:
        for method in METHODS:
            results=[sample['methods'][method+'/'+v] for v in ['base','lower_threshold','background']]
            percentages=[r['trace_support']['2']['sampled_point_fraction'] for r in results]
            lines.append(f"| {sample['source']} | {method} | {percentages[0]:.1%} | {percentages[1]:.1%} | {percentages[2]:.1%} | {results[0]['network_measurements']['total_length_um']:.1f} |")
    lines += ['','Lengths describe all candidate network skeletons, whereas the workbook lengths describe only the supplied sparse paths; their totals have different denominators and must not be treated as agreement/error. The fixed sensitivity settings are exploratory, with no held-out biological validation.','',
        'The initial adaptive threshold without a global contrast floor labeled 33–55% of the real traced fields. Its high path support also included substantial additional noise, so it was not accepted as evidence of accuracy. The implemented adaptive default requires signal above 0.25×global Otsu as well as the local threshold. The full report retains each no-floor run as a diagnostic.','',
        'ImageJ TIFF XY resolution tags define Box calibration; ROI polyline lengths were recomputed and reconciled to the supplied workbook. Simulation spacing is artificial. The real 14Z field retains every acquired plane at 2× XY reduction, filtering each XY slice then skeletonizing the acquired volume.','',
        'Baseline skeleton TIFFs, per-network CSVs and per-branch CSVs are included. Orange overlays show algorithm skeletons; cyan shows the supplied sparse paths. The report records exact source hashes, settings, elapsed times, threshold, foreground fraction, branches, endpoints, junctions, calibration and 1/2/3px path-support sensitivity.','',
        'Reproduce with `microscopy-studio/.venv/bin/python microscopy-studio/tools/compare_neurites.py` from the parent workspace.','',
        '[Ridge-filter implementation reference](https://scikit-image.org/docs/stable/api/skimage.filters.html) and [skeletonize reference](https://scikit-image.org/docs/stable/api/skimage.morphology.html#skimage.morphology.skeletonize).']
    (out/'README.md').write_text('\n'.join(lines)+'\n')
    comparison_rows=[]
    for sample in report['samples']:
        for name,result in sample['methods'].items():
            summary=result['network_measurements']
            comparison_rows.append(dict(source=sample['source'],kind=sample['kind'],method=name,threshold=result['threshold'],foreground_fraction=result['foreground_fraction'],
                length_um=summary['total_length_um'],skeleton_voxels=summary['skeleton_voxels'],branches=summary['branches'],endpoints=summary['endpoints'],junctions=summary['junctions'],
                sparse_trace_support_2px=result.get('trace_support',{}).get('2',{}).get('sampled_point_fraction'),
                simulated_centerline_support_2_grid_px=result.get('known_unique_centerline_support_2_grid_px')))
    (out/'comparison.csv').write_bytes(csv_bytes(comparison_rows,list(comparison_rows[0])))
    table=''.join('<tr>'+''.join('<td>'+html.escape(cell.strip())+'</td>' for cell in line.strip('|').split('|'))+'</tr>' for line in lines if line.startswith('|') and not line.startswith('|---'))
    images=''.join('<figure><img width="1152" src="'+stem.replace("'",'')+'-comparison.png"><figcaption>'+html.escape(stem)+'</figcaption></figure>' for stem in ['iMOP_D7_neuron',"Sox11_5'dCas9","Sox11_5'mecp2"])
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>FIELD neurite comparison</title><style>body{background:#10151b;color:#dfe8ee;font:16px system-ui;margin:32px}table{border-collapse:collapse}td{border:1px solid #465461;padding:8px}img{max-width:100%}a{color:#99c9ff}</style><h1>Neurite techniques: '+str(report['run_count'])+' local runs</h1><p>'+html.escape(report['metric'])+'</p><p>'+html.escape(report['limitation'])+'</p><table>'+table+'</table>'+images+'<p><a href="report.json">Full measurements and provenance</a></p>')


if __name__=='__main__':main()
