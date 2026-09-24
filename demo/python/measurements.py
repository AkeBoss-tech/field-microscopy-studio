"""Candidate measurements, review decisions, and explicit counting protocols."""
import csv
import io
import json
import time
import uuid
from functools import lru_cache

import numpy as np
from review import object_index, _integer
from corrections import current as correction_current, label_array

STATUSES = ('unreviewed', 'accepted', 'rejected', 'needs_review')


def context(q):
    import server as s
    run, folder = s.getrun(q.get('run', ''))
    if run['dataset'] != q.get('dataset') or run['channel'] != _integer(q.get('channel', 0), s.metadata(run['dataset'])['shape'][1], 'Channel'):
        raise ValueError('Choose a run from the active image and channel')
    if run.get('historical') or run['scope'] != 'volume' or run['method'] == 'preprocess':
        raise ValueError('Measurements require a registered full-volume segmentation run')
    d = s.metadata(run['dataset'])
    nz, _, ny, nx = d['shape']
    if tuple(run['shape']) != (nz, ny // run['factor'], nx // run['factor']):
        raise ValueError('Run dimensions do not match source coordinates')
    return run, folder, d


@lru_cache(maxsize=8)
def geometry(store, run_id, label_revision=None):
    import server as s
    r, _ = s.getrun(run_id)
    sizes, boxes, edges = object_index(store, run_id, label_revision)
    f = r['factor']
    result = []
    for i, box in enumerate(boxes, 1):
        if box is None:
            continue
        z, y, x = box
        result.append(dict(id=i, voxels=int(sizes[i]),
                           bounds_native=[[x.start*f, y.start*f, z.start], [x.stop*f, y.stop*f, z.stop]],
                           boundary_faces=edges.get(i, [])))
    return result


def current(folder):
    path = folder / 'reviews' / 'latest.json'
    return json.loads(path.read_text()) if path.exists() else dict(revision=None, decisions={})


def protocol_current(folder):
    path = folder / 'count-protocol' / 'latest.json'
    return json.loads(path.read_text()) if path.exists() else dict(
        revision=None, target='', channel_role='', edge_policy='', reviewer_note='')


def decision_for(review, correction, object_id):
    decision = review['decisions'].get(str(object_id), {})
    # A decision is valid only for the exact geometry the reviewer saw.
    version = correction.get('versions', {}).get(str(object_id))
    if decision.get('label_version') != version:
        return {}
    return decision


def count_summary(run, rows, protocol):
    policy = protocol.get('edge_policy', '')
    included = [o for o in rows if policy != 'exclude' or not o['boundary_faces']]
    statuses = {name: sum(o['status'] == name for o in included) for name in STATUSES}
    ready = bool(protocol.get('revision') and run['method'] in ('otsu', 'watershed', 'external')
                 and not statuses['unreviewed'] and not statuses['needs_review'])
    return dict(ready=ready, accepted_so_far=statuses['accepted'],
                reviewed_count=statuses['accepted'] if ready else None,
                unresolved=statuses['unreviewed'] + statuses['needs_review'],
                rejected=statuses['rejected'], included_candidates=len(included),
                excluded_edge_candidates=len(rows)-len(included),
                target=protocol.get('target', ''), channel_role=protocol.get('channel_role', ''),
                edge_policy=policy,
                caveat='Reviewer decisions on candidate objects; biological accuracy requires independent expert validation.')


def save_protocol(q):
    import server as s
    run, folder, _ = context(q)
    if run['method'] not in ('otsu', 'watershed', 'external'):
        raise ValueError('A body or nucleus count requires instance candidates')
    target = str(q.get('target', '')).strip()
    role = str(q.get('channel_role', '')).strip()
    note = str(q.get('reviewer_note', '')).strip()
    policy = q.get('edge_policy')
    if not target or len(target) > 100 or not role or len(role) > 100 or len(note) > 1000:
        raise ValueError('Name the count target and channel meaning (up to 100 characters each)')
    if policy not in ('include', 'exclude'):
        raise ValueError('Choose whether edge-touching candidates count')
    with s.LOCK:
        old = protocol_current(folder)
        if q.get('expected_revision') != old['revision']:
            raise ValueError('Count rules changed elsewhere. Reload before saving.')
        revision = uuid.uuid4().hex
        record = dict(revision=revision, parent=old['revision'], run=run['id'],
                      dataset=run['dataset'], channel=run['channel'], target=target,
                      channel_role=role, edge_policy=policy, reviewer_note=note,
                      created=time.time())
        target_dir = folder / 'count-protocol'
        target_dir.mkdir(exist_ok=True)
        item = target_dir / (revision + '.json')
        latest = target_dir / 'latest.json'
        old_bytes = latest.read_bytes() if latest.exists() else None
        s.atomic(item, record)
        s.atomic(latest, record)
        try:
            s.persist(s.STORE, [item, latest])
        except Exception:
            if old_bytes is None:
                latest.unlink(missing_ok=True)
            else:
                latest.write_bytes(old_bytes)
            item.unlink(missing_ok=True)
            raise
    return record


def query_rows(q):
    import server as s
    r, folder, d = context(q)
    with s.LOCK:
        snapshot = current(folder)
        correction = correction_current(folder)
        protocol = protocol_current(folder)
    spacing = r.get('spacing') or [d['spacing'][0]*r['factor'], d['spacing'][1]*r['factor'], d['spacing'][2]]
    calibrated = r.get('calibrated', d.get('calibrated', False))
    rows = []
    counts = dict.fromkeys(STATUSES, 0)
    for obj in geometry(str(s.STORE), r['id'], correction['revision']):
        decision = decision_for(snapshot, correction, obj['id'])
        status = decision.get('status', 'unreviewed')
        counts[status] += 1
        rows.append(dict(obj, status=status, note=decision.get('note', ''),
                         volume_um3=float(obj['voxels']*np.prod(spacing)) if calibrated else None))
    total = len(rows)
    count = count_summary(r, rows, protocol)
    status = q.get('status', 'all')
    if status not in ('all',) + STATUSES:
        raise ValueError('Unknown review status filter')
    boundary = q.get('boundary', 'all')
    if boundary not in ('all', 'interior', 'edge'):
        raise ValueError('Unknown boundary policy')
    search = str(q.get('search', '')).strip()
    rows = [o for o in rows if (status == 'all' or o['status'] == status)
            and (boundary == 'all' or bool(o['boundary_faces']) == (boundary == 'edge'))
            and (not search or search == str(o['id']))]
    sort = q.get('sort', 'id')
    if sort not in ('id', 'size_asc', 'size_desc'):
        raise ValueError('Unknown measurement sort')
    rows.sort(key=lambda o: ((-o['voxels'] if sort == 'size_desc' else o['voxels']), o['id']) if sort != 'id' else (o['id'],))
    return r, snapshot, correction, protocol, count, counts, total, rows


def table(q):
    r, snapshot, correction, protocol, count, counts, total, rows = query_rows(q)
    requested_offset = _integer(q.get('offset', 0), 1_000_000_000, 'Offset')
    limit = _integer(q.get('limit', 50), 201, 'Page size')
    if limit == 0:
        raise ValueError('Page size must be positive')
    # A different reviewer can shrink this selection between page requests.
    offset = min(requested_offset, ((max(1, len(rows))-1)//limit)*limit)
    sizes = [o['voxels'] for o in rows]
    return dict(run=r['id'], revision=snapshot['revision'], label_revision=correction['revision'],
                protocol_revision=protocol['revision'], protocol=protocol, count=count,
                counts=counts, total=total,
                matched=len(rows), offset=offset, rows=rows[offset:offset+limit],
                summary=dict(voxels=sum(sizes), median_voxels=float(np.median(sizes)) if sizes else None,
                             edge_count=sum(bool(o['boundary_faces']) for o in rows)),
                meaning=r['meaning'])


def locate(q):
    """Choose a real labeled voxel, since a bounding-box center can be background."""
    import server as s
    r, _, _ = context(q)
    correction = correction_current(s.STORE / 'runs' / r['id'])
    sizes, boxes, _ = object_index(str(s.STORE), r['id'], correction['revision'])
    i = _integer(q.get('object'), len(sizes), 'Object ID')
    if i == 0 or not sizes[i]:
        raise ValueError('Unknown candidate')
    zz, yy, xx = boxes[i-1]
    labels = label_array(r['id'], correction['revision'])
    middle = (zz.start+zz.stop-1)/2
    for z in sorted(range(zz.start, zz.stop), key=lambda v: abs(v-middle)):
        coords = np.argwhere(labels[z, yy, xx] == i)
        if len(coords):
            y, x = coords[len(coords)//2]
            f = r['factor']
            return dict(object=i, cursor=[int((x+xx.start)*f), int((y+yy.start)*f), z])
    raise ValueError('Candidate has no labeled voxels')


def save(q):
    import server as s
    r, folder, _ = context(q)
    correction = correction_current(folder)
    ids = {o['id'] for o in geometry(str(s.STORE), r['id'], correction['revision'])}
    value = q.get('object')
    i = _integer(value, max(ids, default=0)+1, 'Object ID')
    if i not in ids:
        raise ValueError('Unknown candidate')
    status = q.get('status')
    if status not in STATUSES:
        raise ValueError('Unknown review decision')
    note = str(q.get('note', ''))
    if len(note) > 2000:
        raise ValueError('Review note exceeds 2000 characters')
    with s.LOCK:
        old = current(folder)
        correction = correction_current(folder)
        if i not in {o['id'] for o in geometry(str(s.STORE), r['id'], correction['revision'])}:
            raise ValueError('Labels changed. Reload this candidate before reviewing.')
        if q.get('expected_label_revision', correction['revision']) != correction['revision']:
            raise ValueError('Labels changed. Reload this candidate before reviewing.')
        if 'expected_revision' not in q or q['expected_revision'] != old['revision']:
            raise ValueError('Review changed elsewhere. Reload the candidate table before saving again.')
        revision = uuid.uuid4().hex
        decisions = dict(old['decisions'])
        decisions[str(i)] = dict(status=status, note=note, updated=time.time(),
                                 label_version=correction.get('versions', {}).get(str(i)))
        snapshot = dict(revision=revision, parent=old['revision'], run=r['id'],
                        dataset=r['dataset'], channel=r['channel'], decisions=decisions)
        target = folder / 'reviews'
        target.mkdir(exist_ok=True)
        s.atomic(target / (revision+'.json'), snapshot)
        latest = target / 'latest.json'
        old_bytes = latest.read_bytes() if latest.exists() else None
        s.atomic(latest, snapshot)
        try:
            s.persist(s.STORE, [target / (revision+'.json'), latest])
        except Exception:
            if old_bytes is None:
                latest.unlink(missing_ok=True)
            else:
                latest.write_bytes(old_bytes)
            raise
    return dict(revision=revision, object=i, status=status, note=note)


def _pinned(q, snapshot, correction, protocol):
    if q.get('revision', '') != (snapshot['revision'] or '') or \
       q.get('label_revision', '') != (correction['revision'] or '') or \
       q.get('protocol_revision', '') != (protocol['revision'] or ''):
        raise ValueError('Review, labels, or count rules changed. Refresh export preview.')


def csv_export(q):
    r, snapshot, correction, protocol, _, _, _, rows = query_rows(q)
    # Pin the exact review snapshot from the export preview.
    _pinned(q, snapshot, correction, protocol)
    fields = ['run_id', 'source_sha256', 'dataset', 'channel_0based', 'review_revision',
              'label_revision', 'protocol_revision', 'count_target', 'channel_role', 'count_edge_policy',
              'included_in_count', 'object_id',
              'status', 'note', 'voxels', 'volume_um3', 'bounds_native_xyz_end_exclusive',
              'boundary_faces', 'status_filter', 'boundary_policy', 'xy_factor', 'method']
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    def cell(v):
        # Spreadsheet formula injection protection for user-supplied notes and imported names.
        return "'"+v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v
    for o in rows:
        row = dict(run_id=r['id'], source_sha256=r.get('sha256', ''), dataset=r['dataset'],
                   channel_0based=r['channel'], review_revision=snapshot['revision'] or '',
                   label_revision=correction['revision'] or '', protocol_revision=protocol['revision'] or '',
                   count_target=protocol.get('target', ''), channel_role=protocol.get('channel_role', ''),
                   count_edge_policy=protocol.get('edge_policy', ''),
                   included_in_count=bool(protocol.get('revision') and o['status']=='accepted' and
                                          (protocol['edge_policy']=='include' or not o['boundary_faces'])),
                   object_id=o['id'],
                   status=o['status'], note=o['note'], voxels=o['voxels'], volume_um3=o['volume_um3'],
                   bounds_native_xyz_end_exclusive=json.dumps(o['bounds_native']), boundary_faces='; '.join(o['boundary_faces']),
                   status_filter=q.get('status', 'all'), boundary_policy=q.get('boundary', 'all'),
                   xy_factor=r['factor'], method=r['method'])
        writer.writerow({k:cell(v) for k,v in row.items()})
    return output.getvalue().encode('utf-8-sig')


def summary_export(q):
    r, snapshot, correction, protocol, count, _, total, _ = query_rows(q)
    _pinned(q, snapshot, correction, protocol)
    result = dict(run_id=r['id'], dataset=r['dataset'], channel_0based=r['channel'],
                  source_sha256=r.get('sha256', ''), method=r['method'], xy_factor=r['factor'],
                  algorithm_candidate_count=r['objects'], corrected_candidate_count=total,
                  label_revision=correction['revision'], label_sha256=correction.get('label_sha256'),
                  review_revision=snapshot['revision'], count_protocol=protocol,
                  count=count, interpretation='Reviewer-assessed candidate count; not independent biological ground truth')
    return json.dumps(result, indent=2).encode()


def boxes_export(q):
    """Revision-pinned 3D boxes in native pixels and, when known, micrometers."""
    import server as s
    r, review, correction, protocol, count, _, _, rows = query_rows(q)
    _pinned(q, review, correction, protocol)
    mapping = {}
    if r['method'] == 'external':
        _, folder = s.getrun(r['id'])
        mapping = json.loads((folder / 'original-ids.json').read_text())
    d = s.metadata(r['dataset'])
    spacing = d['spacing']
    boxes = []
    for row in rows:
        bounds = row['bounds_native']
        boxes.append(dict(object_id=row['id'], submitted_object_id=mapping.get(str(row['id'])),
                          status=row['status'], voxels=row['voxels'],
                          bounds_xyz_end_exclusive=bounds,
                          bounds_um_xyz_end_exclusive=[
                              [bounds[side][axis] * spacing[axis] for axis in range(3)]
                              for side in range(2)] if d.get('calibrated', False) else None,
                          boundary_faces=row['boundary_faces']))
    return json.dumps(dict(dataset=r['dataset'], source_sha256=r.get('sha256'),
                           run_id=r['id'], method=r['method'], channel_0based=r['channel'],
                           target=protocol.get('target') or r.get('target', ''),
                           label_revision=correction['revision'], review_revision=review['revision'],
                           protocol_revision=protocol['revision'], count_ready=count['ready'],
                           coordinate_system='native XYZ pixels; zero-based, end-exclusive bounds',
                           boxes=boxes), indent=2).encode()
