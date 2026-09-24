"""Candidate measurements and append-only review decisions; never edits labels."""
import csv
import io
import json
import time
import uuid
from functools import lru_cache

import numpy as np
from review import object_index, _integer

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
def geometry(store, run_id):
    import server as s
    r, _ = s.getrun(run_id)
    sizes, boxes, edges = object_index(store, run_id)
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


def query_rows(q):
    import server as s
    r, folder, d = context(q)
    with s.LOCK:
        snapshot = current(folder)
    spacing = r.get('spacing') or [d['spacing'][0]*r['factor'], d['spacing'][1]*r['factor'], d['spacing'][2]]
    calibrated = r.get('calibrated', d.get('calibrated', False))
    rows = []
    counts = dict.fromkeys(STATUSES, 0)
    for obj in geometry(str(s.STORE), r['id']):
        decision = snapshot['decisions'].get(str(obj['id']), {})
        status = decision.get('status', 'unreviewed')
        counts[status] += 1
        rows.append(dict(obj, status=status, note=decision.get('note', ''),
                         volume_um3=float(obj['voxels']*np.prod(spacing)) if calibrated else None))
    total = len(rows)
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
    return r, snapshot, counts, total, rows


def table(q):
    r, snapshot, counts, total, rows = query_rows(q)
    requested_offset = _integer(q.get('offset', 0), 1_000_000_000, 'Offset')
    limit = _integer(q.get('limit', 50), 201, 'Page size')
    if limit == 0:
        raise ValueError('Page size must be positive')
    # A different reviewer can shrink this selection between page requests.
    offset = min(requested_offset, ((max(1, len(rows))-1)//limit)*limit)
    sizes = [o['voxels'] for o in rows]
    return dict(run=r['id'], revision=snapshot['revision'], counts=counts, total=total,
                matched=len(rows), offset=offset, rows=rows[offset:offset+limit],
                summary=dict(voxels=sum(sizes), median_voxels=float(np.median(sizes)) if sizes else None,
                             edge_count=sum(bool(o['boundary_faces']) for o in rows)),
                meaning=r['meaning'])


def locate(q):
    """Choose a real labeled voxel, since a bounding-box center can be background."""
    import server as s
    r, _, _ = context(q)
    sizes, boxes, _ = object_index(str(s.STORE), r['id'])
    i = _integer(q.get('object'), len(sizes), 'Object ID')
    if i == 0 or not sizes[i]:
        raise ValueError('Unknown candidate')
    zz, yy, xx = boxes[i-1]
    labels = s.run_array(r['id'], 'labels')
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
    ids = {o['id'] for o in geometry(str(s.STORE), r['id'])}
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
        if 'expected_revision' not in q or q['expected_revision'] != old['revision']:
            raise ValueError('Review changed elsewhere. Reload the candidate table before saving again.')
        revision = uuid.uuid4().hex
        decisions = dict(old['decisions'])
        decisions[str(i)] = dict(status=status, note=note, updated=time.time())
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


def csv_export(q):
    r, snapshot, _, _, rows = query_rows(q)
    # Pin the exact review snapshot from the export preview.
    if q.get('revision', '') != (snapshot['revision'] or ''):
        raise ValueError('Review changed. Refresh the export preview before downloading.')
    fields = ['run_id', 'source_sha256', 'dataset', 'channel_0based', 'review_revision', 'object_id',
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
                   channel_0based=r['channel'], review_revision=snapshot['revision'] or '', object_id=o['id'],
                   status=o['status'], note=o['note'], voxels=o['voxels'], volume_um3=o['volume_um3'],
                   bounds_native_xyz_end_exclusive=json.dumps(o['bounds_native']), boundary_faces='; '.join(o['boundary_faces']),
                   status_filter=q.get('status', 'all'), boundary_policy=q.get('boundary', 'all'),
                   xy_factor=r['factor'], method=r['method'])
        writer.writerow({k:cell(v) for k,v in row.items()})
    return output.getvalue().encode('utf-8-sig')
