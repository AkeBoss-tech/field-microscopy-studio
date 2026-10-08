"""Deterministic explanations of saved evidence; never infer biological accuracy."""
from measurements import table

METHODS = {
    'preprocess': 'Intensity preparation only; no candidate detection',
    'adaptive_regions': 'Per-XY Gaussian local threshold with a global Otsu signal floor, followed by connected-region labeling',
    'prominence_watershed': 'Otsu foreground followed by distance watershed seeded with prominence-filtered maxima; isolated unseeded regions retain one maximum',
    'otsu': 'Otsu intensity threshold followed by connected-region labeling',
    'watershed': 'Selected bright foreground with Otsu thresholding, then used distance-based seeds and watershed to separate touching regions',
    'sato': 'Sato ridge enhancement, Otsu threshold and connected-region labeling',
    'neurite_otsu': 'Otsu threshold followed by skeleton-network measurement',
    'neurite_adaptive': 'Local adaptive threshold with signal floor, followed by skeleton-network measurement',
    'neurite_sato': 'Sato ridge enhancement followed by thresholding and skeleton-network measurement',
    'neurite_frangi': 'Frangi ridge enhancement followed by thresholding and skeleton-network measurement',
    'neurite_meijering': 'Meijering ridge enhancement followed by thresholding and skeleton-network measurement',
}


def preparation(run):
    p = run.get('parameters') or {}
    e = run.get('effective_parameters') or {}
    if not e:
        return 'Preparation settings were not recorded; consult the original method provenance.'
    steps = []
    def width(key, values):
        if e.get('units') == 'physical' and key in p:
            return f"σ {float(p[key]):.5g} µm"
        return 'σ Y/X '+', '.join(f'{float(v):.5g}' for v in values)+' working pixels'
    if any(e.get('sigma_yx', [])):
        steps.append('Reduced small intensity fluctuations using XY Gaussian smoothing ('+width('sigma_um', e['sigma_yx'])+'); acquired Z planes were not blurred together')
    else:
        steps.append('Smoothing off')
    if any(e.get('background_yx', [])):
        steps.append('subtracted a broad XY Gaussian background ('+width('background_um', e['background_yx'])+'), clipping negative values to zero')
    else:
        steps.append('background subtraction off')
    if p.get('normalize'):
        steps.append('applied 1st–99.5th percentile normalization to 0–1, with clipping')
    else:
        steps.append('percentile normalization off')
    return '; '.join(steps)+'.' if any(e.get('sigma_yx', [])) or any(e.get('background_yx', [])) or p.get('normalize') else 'Smoothing, background subtraction and percentile normalization were all off.'



def explain(q):
    import server as s
    r, folder = s.getrun(q.get('run', ''))
    d = s.metadata(r['dataset'])
    if q.get('dataset') != r['dataset']:
        raise ValueError('Choose a run from this image')
    p = r.get('parameters') or {}
    e = r.get('effective_parameters') or {}
    bounds = r.get('region_bounds')
    scope = (f'Selected {bounds[3]-bounds[0]} × {bounds[4]-bounds[1]} native-pixel region, acquired Z planes {bounds[2]+1}–{bounds[5]} (1-based)' if bounds else
             'Full acquired 3D stack' if r['scope'] == 'volume' else
             'Acquired Z plane '+str(r.get('z', 0)+1) if r['scope'] == 'slice' else
             '2D maximum Z projection' if p else '2D projection (projection settings not recorded)')
    source = f"{d['name']}; channel {r['channel']+1}: {d['channels'][r['channel']]}. {scope}. XY reduction {r['factor']}×."
    source += (' Native XYZ spacing: '+', '.join(f'{float(v):.5g}' for v in d['spacing'])+' µm.' if d.get('calibrated') else ' Source is uncalibrated.')
    stages = [dict(run=r['id'], preparation=preparation(r), parameters=p, effective_parameters=e)]
    parent = r.get('parent'); seen = {r['id']}
    while parent:
        if parent in seen or len(seen) >= 100:
            raise ValueError('Invalid parent-run lineage')
        seen.add(parent); prior, _ = s.getrun(parent)
        stages.insert(0, dict(run=parent, preparation=preparation(prior), parameters=prior.get('parameters'), effective_parameters=prior.get('effective_parameters')))
        parent = prior.get('parent')
    prep = ' '.join(('Stage '+str(i+1)+' ('+stage['run']+'): ' if len(stages)>1 else '')+stage['preparation'] for i, stage in enumerate(stages))
    algorithm = METHODS.get(r['method'], 'Imported or historical output; consult original method provenance')
    if r.get('threshold') is not None:
        label = "Global Otsu reference (before floor multiplier)" if r["method"] == "adaptive_regions" else "Applied threshold"
        algorithm += f". {label}: {r['threshold']:.6g}"
    if r['method']!='preprocess' and 'min_size' in e:
        algorithm += f". Minimum foreground: {e['min_size']} working pixels/voxels; minimum final object: {e.get('min_final_size', 0)}"
    if r['method'] == 'watershed':
        algorithm += f". Seed separation: {e.get('seed_distance')} ({'µm' if e.get('units')=='physical' else 'working pixels'})"
    if r['method'] == 'adaptive_regions':
        algorithm += f". Local window: {e.get('local_window')} working pixels; offset: {e.get('local_offset')}; global floor multiplier: {e.get('local_floor')}"
    if r['method'] == 'prominence_watershed':
        algorithm += f". Peak prominence: {e.get('peak_prominence')} ({'µm' if e.get('units')=='physical' else 'working pixels'})"
    review = None
    if not r.get('historical') and r['scope']=='volume' and r['method']!='preprocess':
        review = table(dict(run=r['id'], dataset=r['dataset'], channel=r['channel'], limit=1))
    network = r['method'].startswith('neurite_') or r['method']=='sato'
    noun = 'connected networks' if network else 'candidate regions'
    output = ('Prepared intensity image; no cells were counted.' if r['method']=='preprocess' else
              f"Original algorithm output: {r.get('objects', 'unrecorded')} {noun}.")
    if review:
        counts=review['counts']; count=review['count']
        review_text=f"Current label layer: {review['total']} {noun}; {counts['accepted']} accepted, {counts['rejected']} rejected, {counts['unreviewed']} unreviewed and {counts['needs_review']} needing review."
        review_text += (f" Reviewed count under saved rules: {count['reviewed_count']} {count['target']}; edge policy: {count['edge_policy']}." if count['ready'] else ' A final reviewed cell count is not established.')
        review_text += (f" {count['excluded_edge_candidates']} candidates excluded by the saved edge rule." if review['protocol_revision'] else ' Count rules have not been saved.')
    else:
        review_text='Object review/count status is unavailable for this result type.'
    validation='Independent reference accuracy is not established by this run. Missed cells, extra detections and merge/split errors require matched expert annotations.'
    if network:
        validation='Connected networks do not establish individual neuron identities. Independent reference accuracy is not established by this run.'
    caveats=['Display contrast and colors do not change the saved measurements.',
             'Regions and projections can truncate or combine structures; inspect acquired Z planes.',
             'A reviewed candidate tally is not independent biological validation.']
    if any((stage.get('parameters') or {}).get('normalize') for stage in stages):
        caveats.append('Normalized intensities are unsuitable for direct absolute fluorescence comparisons across independently normalized images.')
    sections=dict(Input=source,Preparation=prep,Detection=algorithm,Output=output,Review=review_text,Validation=validation)
    methods=f"We analyzed {source} Preparation: {prep} Detection: {algorithm}. {output} {review_text} {validation}"
    text='\n\n'.join(k+': '+v for k,v in sections.items())
    return dict(run=r['id'],sections=sections,methods=methods,text=text,caveats=caveats,
                provenance=dict(source_sha256=r.get('sha256'),source_shape=d['shape'],region_bounds=bounds,context_bounds=r.get('context_bounds'),spacing_xyz=d['spacing'],calibrated=d.get('calibrated',False),channel=r['channel'],parameters=p,effective_parameters=e,parent_stages=stages,
                                label_revision=review['label_revision'] if review else None,
                                review_revision=review['revision'] if review else None,
                                protocol_revision=review['protocol_revision'] if review else None))
