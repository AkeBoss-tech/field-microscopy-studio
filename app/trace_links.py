"""Revision-pinned, reviewer-assessed links from 3D neurite traces to cells."""
from __future__ import annotations

import numpy as np


def _run(key, run_id):
    import server as s
    run, folder = s.getrun(run_id)
    if run['dataset'] != key or run.get('historical') or run['scope'] != 'volume' or run['method'] not in ('otsu', 'watershed', 'external'):
        raise ValueError('Choose a full-volume body or nucleus candidate run on this image')
    return run, folder


def validate_owner(key, item):
    import server as s
    from corrections import current as correction_current
    from measurements import geometry

    owner = item.get('owner')
    if owner is None:
        return
    if item['type'] != 'polyline' or item['domain'] != 'volume':
        raise ValueError('Only a 3D neurite trace can link to a 3D candidate')
    if not isinstance(owner, dict) or owner.get('assessment') not in ('tentative', 'reviewer_assessed'):
        raise ValueError('Choose tentative or reviewer-assessed ownership')
    run, folder = _run(key, str(owner.get('run_id', '')))
    snapshot = correction_current(folder)
    if owner.get('label_revision') != snapshot['revision']:
        raise ValueError('The linked cell mask changed. Inspect and link this trace again.')
    try:
        object_id = int(owner.get('object_id'))
    except (ValueError, TypeError):
        raise ValueError('Choose a cell candidate ID') from None
    if object_id < 1 or object_id not in {o['id'] for o in geometry(str(s.STORE), run['id'], snapshot['revision'])}:
        raise ValueError('The linked cell candidate no longer exists')
    item['owner'] = dict(run_id=run['id'], object_id=object_id, channel_0based=run['channel'],
                         label_revision=snapshot['revision'],
                         object_version=snapshot.get('versions', {}).get(str(object_id)),
                         assessment=owner['assessment'],
                         target=run.get('target', 'reviewer-defined body or nucleus candidate'))


def nearby(q):
    import server as s
    from corrections import current as correction_current
    from measurements import geometry

    key = str(q.get('dataset', ''))
    if key not in s.DATA:
        raise ValueError('Unknown image')
    run, folder = _run(key, str(q.get('run', '')))
    d = s.metadata(key)
    nz, _, ny, nx = d['shape']
    points = []
    for suffix in ('', '2'):
        points.append(np.array([s.number(q.get('x'+suffix), 0, nx-1),
                                s.number(q.get('y'+suffix), 0, ny-1),
                                s.number(q.get('z'+suffix), 0, nz-1)], dtype=float))
    snapshot = correction_current(folder)
    spacing = np.array(d['spacing'] if d.get('calibrated', False) else [1, 1, 1])
    results = []
    for item in geometry(str(s.STORE), run['id'], snapshot['revision']):
        lo, hi = np.asarray(item['bounds_native'], dtype=float)
        distances = [float(np.linalg.norm(np.maximum(np.maximum(lo-point, point-(hi-1)), 0)*spacing))
                     for point in points]
        results.append(dict(object_id=item['id'], distance=round(min(distances), 3),
                            bounds_xyz_end_exclusive=item['bounds_native'],
                            boundary_faces=item['boundary_faces']))
    results.sort(key=lambda item: (item['distance'], item['object_id']))
    return dict(run_id=run['id'], channel_0based=run['channel'],
                target=run.get('target', ''), label_revision=snapshot['revision'],
                distance_unit='µm' if d.get('calibrated', False) else 'source pixels',
                candidates=results[:8],
                caveat='Proximity to either trace endpoint is a navigation aid, not evidence of neurite ownership.')
