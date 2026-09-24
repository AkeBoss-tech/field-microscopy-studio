"""Unsaved ROI previews and explicit same-channel, full-volume A/B comparisons."""
import os
import numpy as np
from skimage.measure import block_reduce
from processing import process
from review import _integer, encode_plane, display_window


def source(body):
    import server as s
    key = body.get('dataset')
    if key not in s.DATA:
        raise ValueError('Choose an available image')
    d = s.metadata(key)
    ch = _integer(body.get('channel', 0), d['shape'][1], 'Channel')
    return key, d, ch


def window(a):
    lo, hi = np.percentile(a, [1, 99.7])
    return [float(lo), max(float(hi), float(lo)+1e-9)]


def preview(body):
    import server as s
    key, d, ch = source(body)
    nz, _, ny, nx = d['shape']
    params = dict(body.get('parameters', {}))
    if params.get('scope', 'volume') != 'volume':
        raise ValueError('ROI preview uses acquired Z volumes; choose Full Z volume scope')
    factor = _integer(params.get('factor', 1), 5, 'XY reduction')
    if factor not in [1, 2, 4]:
        raise ValueError('XY reduction must be 1, 2 or 4')
    bounds = body.get('bounds', [])
    if len(bounds) != 6:
        raise ValueError('Choose an XY region and Z range')
    x0, y0, z0, x1, y1, z1 = [_integer(v, limit, 'Region bound') for v, limit in zip(bounds, [nx, ny, nz, nx+1, ny+1, nz+1])]
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError('Region end must be after its start')
    if nx % factor or ny % factor:
        raise ValueError('Image extent not divisible by reduction')
    # Align to the same globally anchored block-mean grid as a full run.
    x0, y0 = x0//factor*factor, y0//factor*factor
    x1, y1 = min(nx, (x1+factor-1)//factor*factor), min(ny, (y1+factor-1)//factor*factor)
    if x1-x0 > 512 or y1-y0 > 512 or z1-z0 > 64:
        raise ValueError('Preview region limit: 512 × 512 native pixels and 64 Z planes')
    margin = _integer(body.get('margin', 16), 513, 'Context margin')
    halo = (margin+factor-1)//factor*factor
    hx0, hy0, hx1, hy1 = max(0,x0-halo), max(0,y0-halo), min(nx,x1+halo), min(ny,y1+halo)
    samples = (z1-z0)*((hy1-hy0)//factor)*((hx1-hx0)//factor)
    limit = min(2_000_000, int(os.environ.get('STUDIO_PROCESS_VOXELS','268435456')))
    if samples > limit:
        raise ValueError(f'Preview including context exceeds {limit:,} working voxels; reduce the region or Z range')
    parent = params.get('parent')
    if parent:
        old, _ = s.getrun(parent)
        if old['dataset'] != key or old['channel'] != ch or old['scope'] != 'volume' or old['factor'] != factor or old.get('historical'):
            raise ValueError('Parent must match image, channel, XY reduction and full-volume scope')
        a = s.run_array(parent,'processed')[z0:z1,hy0//factor:hy1//factor,hx0//factor:hx1//factor]
    else:
        a = s.volume(key)[z0:z1,ch,hy0:hy1,hx0:hx1]
        if factor > 1:
            a = block_reduce(a,(1,factor,factor),np.mean)
    # Preview always processes the selected acquired Z slab, never a projection.
    params['scope'] = 'volume'
    processed, labels, score, threshold, effective = process(a, params, d, factor)
    cut = (slice(None), slice((y0-hy0)//factor,(y1-hy0)//factor), slice((x0-hx0)//factor,(x1-hx0)//factor))
    processed, labels, score = processed[cut], labels[cut], score[cut]
    raw = s.volume(key)[z0:z1,ch,y0:y1,x0:x1]
    raw_window = window(raw)
    mode = body.get('contrast','auto')
    if mode not in ['auto','raw']:
        raise ValueError('Unknown intensity window')
    method = params.get('method','otsu')
    result = score if method == 'sato' else processed
    result_window = raw_window if mode == 'raw' else window(result)
    size = (x1-x0,y1-y0)
    planes = []
    for i in range(z1-z0):
        planes.append(dict(z=z0+i,raw=encode_plane(raw[i],None,size,raw_window,'none',0),
                           result=encode_plane(result[i],None,size,result_window,'none',0),
                           labels=encode_plane(raw[i],None if method=='preprocess' else labels[i],size,raw_window,'outline',.9)))
    return dict(dataset=key,channel=ch,bounds=[x0,y0,z0,x1,y1,z1],context_bounds=[hx0,hy0,z0,hx1,hy1,z1],factor=factor,
                parameters=params,effective_parameters=effective,threshold=threshold,working_voxels=samples,
                candidates=int(np.count_nonzero(np.unique(labels))),foreground_fraction=float(np.mean(labels>0)),
                source_window=raw_window,result_window=result_window,planes=planes,
                result_layer='Ridge response' if method=='sato' else 'Processed intensity',preview=True,
                note='Unsaved crop experiment. Thresholds and connected regions depend on this context; a full run can differ. Labels may be cut by the region or Z limits.')


def compare(body):
    import server as s
    key, d, ch = source(body)
    z = _integer(body.get('z',0),d['shape'][0],'Z')
    layer = body.get('layer','raw')
    if layer not in ['raw','processed','ridge-response']:
        raise ValueError('Unknown intensity layer')
    contrast = body.get('contrast','shared')
    if contrast not in ['shared','auto']:
        raise ValueError('Unknown comparison window')
    runs, arrays, masks = [], [], []
    for name in ['a','b']:
        run, _ = s.getrun(body.get(name,''))
        if run['dataset']!=key or run['channel']!=ch or run['scope']!='volume' or run.get('historical'):
            raise ValueError('Compare two current full-volume runs from the active image and channel')
        if layer=='ridge-response' and not run.get('ridge_response'):
            raise ValueError('Ridge comparison needs two Sato runs; choose another image layer')
        a, _ = s.array_for(key,ch,run['id'] if layer!='raw' else None,layer if layer!='raw' else 'processed')
        arrays.append(a[z]); masks.append(None if run['method']=='preprocess' else s.run_array(run['id'],'labels')[z]); runs.append(run)
    windows = [window(a) for a in arrays]
    if layer == 'raw':
        windows = [list(display_window(key,ch,'','processed'))]*2
    elif contrast=='shared':
        shared = [min(w[0] for w in windows),max(w[1] for w in windows)]
        windows = [shared,shared]
    panes = []
    size = (d['shape'][3],d['shape'][2])
    for r,a,mask,limits in zip(runs,arrays,masks,windows):
        panes.append(dict(run=r['id'],title=r.get('title') or r['method'],method=r['method'],factor=r['factor'],objects=r['objects'],
                          foreground_fraction=float(np.mean(mask>0)) if mask is not None else None,
                          window=limits,png=encode_plane(a,mask,size,limits,'outline',.9)))
    keys = sorted(set(runs[0]['parameters']) | set(runs[1]['parameters']))
    # Full-volume runs process every acquired plane; their saved starting Z is UI context.
    differences = [dict(parameter=k,a=runs[0]['parameters'].get(k),b=runs[1]['parameters'].get(k)) for k in keys if runs[0]['parameters'].get(k)!=runs[1]['parameters'].get(k) and k not in ['dataset','channel','recipe_name','z']]
    return dict(z=z,panes=panes,differences=differences,layer=layer,contrast=contrast)
