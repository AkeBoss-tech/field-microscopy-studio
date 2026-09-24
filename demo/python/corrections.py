"""Versioned manual label corrections. Original algorithm labels stay immutable."""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from functools import lru_cache

import numpy as np
import tifffile
from scipy import ndimage as ndi


def current(folder):
    path = folder / 'corrections' / 'latest.json'
    return json.loads(path.read_text()) if path.exists() else {
        'revision': None, 'parent': None, 'versions': {}, 'next_id': None}


@lru_cache(maxsize=3)
def label_array(run_id, revision):
    import server as s
    if revision is None:
        return s.run_array(run_id, 'labels')
    _, folder = s.getrun(run_id)
    path = folder / 'corrections' / (revision + '.tif')
    if not path.is_file():
        raise ValueError('Corrected label revision is missing')
    array = tifffile.imread(path)
    return array[None] if array.ndim == 2 else array


def active(run_id):
    import server as s
    _, folder = s.getrun(run_id)
    snapshot = current(folder)
    return label_array(run_id, snapshot['revision']), snapshot


def _integer(value, upper, name):
    from review import _integer as check
    return check(value, upper, name)


def _simulate(q, run, labels, snapshot):
    """Return a new array and changed IDs, with no persistent side effects."""
    action = q.get('action')
    if action not in ('add', 'delete', 'merge', 'split', 'undo'):
        raise ValueError('Choose Add, Delete, Merge, Split, or Undo')
    if action == 'undo':
        if not snapshot['revision']:
            raise ValueError('No correction to undo')
        import server as s
        _, folder = s.getrun(run['id'])
        parent = snapshot['parent']
        prior = (json.loads((folder / 'corrections' / (parent + '.json')).read_text())
                 if parent else {'versions': {}})
        restored = label_array(run['id'], parent).copy()
        return restored, [], dict(prior['versions']), snapshot['next_id'], 'Restore previous labels'
    new = labels.copy()
    present = np.unique(labels)
    present = present[present > 0]
    object_id = None
    if action != 'add':
        object_id = _integer(q.get('object'), int(labels.max()) + 1, 'Candidate ID')
        if object_id == 0 or object_id not in present:
            raise ValueError('Select an existing candidate')
    changed = []
    next_id = snapshot['next_id'] or int(labels.max()) + 1
    description = ''
    if action == 'delete':
        new[labels == object_id] = 0
        changed = [object_id]
        description = f'Delete candidate #{object_id}'
    elif action == 'merge':
        target = _integer(q.get('target'), int(labels.max()) + 1, 'Merge target')
        if target == 0 or target == object_id or target not in present:
            raise ValueError('Choose a different existing merge target')
        new[labels == object_id] = target
        changed = [object_id, target]
        description = f'Merge #{object_id} into #{target}'
    elif action == 'split':
        axis = q.get('axis')
        if axis not in ('x', 'y', 'z'):
            raise ValueError('Choose an X, Y, or Z split plane')
        index = {'z': 0, 'y': 1, 'x': 2}[axis]
        factor = run['factor'] if axis != 'z' else 1
        coordinate = _integer(q.get('coordinate'), labels.shape[index] * factor, 'Split coordinate')
        grid = coordinate // factor
        if grid < 1 or grid >= labels.shape[index]:
            raise ValueError('Split plane must pass through the candidate')
        before = [slice(None)] * 3
        before[index] = slice(0, grid)
        after = [slice(None)] * 3
        after[index] = slice(grid, None)
        left = int(np.count_nonzero(labels[tuple(before)] == object_id))
        right = int(np.count_nonzero(labels[tuple(after)] == object_id))
        if min(left, right) < 2:
            raise ValueError('Split must leave at least two voxels on each side')
        if next_id > np.iinfo(labels.dtype).max:
            new = new.astype(np.uint32)
        region = new[tuple(after)]
        region[region == object_id] = next_id
        changed = [object_id, next_id]
        description = f'Split #{object_id} at {axis.upper()} {coordinate}; new #{next_id}'
        next_id += 1
    elif action == 'add':
        factor = run['factor']
        x = _integer(q.get('x'), labels.shape[2] * factor, 'X') // factor
        y = _integer(q.get('y'), labels.shape[1] * factor, 'Y') // factor
        z = _integer(q.get('z'), labels.shape[0], 'Z')
        if labels[z, y, x]:
            raise ValueError('The cursor is inside an existing candidate; choose background')
        radius_xy = float(q.get('radius_xy', 5))
        radius_z = float(q.get('radius_z', 1 if labels.shape[0] > 1 else 0))
        if not np.isfinite(radius_xy) or not 1 <= radius_xy <= 50 or not np.isfinite(radius_z) or not 0 <= radius_z <= 10:
            raise ValueError('Choose an XY radius from 1–50 and a Z radius from 0–10')
        ry = rx = max(radius_xy / factor, .5)
        rz = max(radius_z, .5)
        z0, z1 = max(0, z - int(np.ceil(radius_z))), min(labels.shape[0], z + int(np.ceil(radius_z)) + 1)
        y0, y1 = max(0, y - int(np.ceil(ry))), min(labels.shape[1], y + int(np.ceil(ry)) + 1)
        x0, x1 = max(0, x - int(np.ceil(rx))), min(labels.shape[2], x + int(np.ceil(rx)) + 1)
        zz, yy, xx = np.ogrid[z0:z1, y0:y1, x0:x1]
        mask = (((xx-x)/rx)**2 + ((yy-y)/ry)**2 + ((zz-z)/rz)**2 <= 1)
        region = new[z0:z1, y0:y1, x0:x1]
        mask &= region == 0
        components, _ = ndi.label(mask)
        mask &= components == components[z-z0, y-y0, x-x0]
        if not np.any(mask):
            raise ValueError('No background voxels available at cursor')
        if next_id > np.iinfo(labels.dtype).max:
            new = new.astype(np.uint32)
            region = new[z0:z1, y0:y1, x0:x1]
        region[mask] = next_id
        changed = [next_id]
        description = f'Add candidate #{next_id} at X{x*factor}, Y{y*factor}, Z{z}'
        next_id += 1
    versions = dict(snapshot.get('versions', {}))
    for identifier in changed:
        versions[str(identifier)] = '__new__'
    return new, changed, versions, next_id, description


def _prepare(q):
    import server as s
    from measurements import context
    run, folder, _ = context(q)
    with s.LOCK:
        snapshot = current(folder)
        if q.get('expected_label_revision') != snapshot['revision']:
            raise ValueError('Labels changed elsewhere. Reload Review and preview the correction again.')
        labels = label_array(run['id'], snapshot['revision'])
        new, changed, versions, next_id, description = _simulate(q, run, labels, snapshot)
    affected = int(np.count_nonzero(new != labels))
    if not affected:
        raise ValueError('This correction makes no change')
    return run, folder, snapshot, labels, new, changed, versions, next_id, description, affected


def preview(q):
    import server as s
    from review import encode_plane, plane, display_window
    run, _, snapshot, old, new, changed, _, _, description, affected = _prepare(q)
    d = s.metadata(run['dataset'])
    nz, _, ny, nx = d['shape']
    cursor = [_integer(q.get('x', nx//2), nx, 'X'), _integer(q.get('y', ny//2), ny, 'Y'),
              _integer(q.get('z', nz//2), nz, 'Z')]
    intensity = s.volume(run['dataset'])[:, run['channel']]
    window = display_window(run['dataset'], run['channel'], '', 'processed')
    planes = {}
    for axis, size in (('xy', (nx, ny)), ('xz', (nx, nz)), ('yz', (ny, nz))):
        base = plane(intensity, axis, cursor, 1)
        corrected = plane(new, axis, cursor, run['factor'])
        planes[axis] = encode_plane(base, corrected, size, window, 'outline', .9,
                                    changed[-1] if changed else 0)
    return {'label_revision': snapshot['revision'], 'description': description,
            'changed_ids': changed, 'affected_voxels': affected,
            'candidate_count': int(np.count_nonzero(np.unique(new))), 'planes': planes}


def save(q):
    import server as s
    from measurements import context
    run, folder, _ = context(q)
    with s.LOCK:
        snapshot = current(folder)
        if q.get('expected_label_revision') != snapshot['revision']:
            raise ValueError('Labels changed elsewhere. Reload Review and preview the correction again.')
        labels = label_array(run['id'], snapshot['revision'])
        new, changed, versions, next_id, description = _simulate(q, run, labels, snapshot)
        affected = int(np.count_nonzero(new != labels))
        if not affected:
            raise ValueError('This correction makes no change')
        revision = uuid.uuid4().hex
        for identifier in changed:
            versions[str(identifier)] = revision
        target = folder / 'corrections'
        target.mkdir(exist_ok=True)
        image_path = target / (revision + '.tif')
        tmp = target / (revision + '.tmp.tif')
        tifffile.imwrite(tmp, new, compression='zlib', metadata={'axes': 'ZYX'})
        os.replace(tmp, image_path)
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        record = {'revision': revision, 'parent': snapshot['revision'], 'run': run['id'],
                  'dataset': run['dataset'], 'channel': run['channel'], 'action': q['action'],
                  'description': description, 'affected_voxels': affected,
                  'changed_ids': changed, 'versions': versions, 'next_id': next_id,
                  'label_sha256': digest, 'created': time.time()}
        record_path = target / (revision + '.json')
        s.atomic(record_path, record)
        latest = target / 'latest.json'
        old_bytes = latest.read_bytes() if latest.exists() else None
        s.atomic(latest, record)
        try:
            s.persist(s.STORE, [image_path, record_path, latest])
        except Exception:
            if old_bytes is None:
                latest.unlink(missing_ok=True)
            else:
                latest.write_bytes(old_bytes)
            image_path.unlink(missing_ok=True)
            record_path.unlink(missing_ok=True)
            raise
        label_array.cache_clear()
    return {'label_revision': revision, 'parent': snapshot['revision'],
            'description': description, 'affected_voxels': affected,
            'candidate_count': int(np.count_nonzero(np.unique(new)))}
