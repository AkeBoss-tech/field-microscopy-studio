"""Import externally generated 3D instance masks as immutable review runs."""
from __future__ import annotations

import csv
import hashlib
import io
import os
import shutil
import time
import uuid

import numpy as np
import tifffile
from scipy import ndimage as ndi
from skimage.measure import block_reduce


def _read_labels(raw, axes, source_shape):
    with tifffile.TiffFile(io.BytesIO(raw)) as file:
        series = file.series[0]
        declared = axes or series.axes
        if declared not in ('YX', 'ZYX') or len(declared) != len(series.shape):
            raise ValueError('Choose YX for one plane or ZYX for a 3D instance TIFF')
        if not np.issubdtype(series.dtype, np.integer):
            raise ValueError('Instance masks must contain nonnegative integer IDs; zero is background')
        shape = (1, *series.shape) if declared == 'YX' else series.shape
        nz, _, ny, nx = source_shape
        if shape[0] != nz or not shape[1] or not shape[2]:
            raise ValueError('Mask Z must match all acquired source planes')
        fy, fx = ny / shape[1], nx / shape[2]
        if fy != fx or fy not in (1, 2, 4):
            raise ValueError('Mask XY must match native, 2×, or 4× source grid with no crop or shift')
        if np.prod(shape, dtype=np.int64) > int(os.environ.get('STUDIO_LABEL_VOXELS', '50000000')):
            raise ValueError('Mask exceeds the instance import voxel limit')
        labels = series.asarray()
        if np.issubdtype(labels.dtype, np.signedinteger) and np.any(labels < 0):
            raise ValueError('Instance masks must contain nonnegative integer IDs; zero is background')
    if labels.ndim == 2:
        labels = labels[None]
    ids, inverse = np.unique(labels, return_inverse=True)
    object_ids = ids[ids != 0]
    if len(object_ids) > 100000:
        raise ValueError('Mask has too many distinct instance IDs')
    # Review and geometry indexing use compact positive IDs. Keep the original
    # IDs in a sidecar rather than interpreting a sparse maximum as a count.
    normalized = inverse.reshape(labels.shape).astype(np.uint32)
    if ids[0] != 0:
        normalized += 1
    mapping = {str(i + 1): int(value) for i, value in enumerate(object_ids)}
    return normalized, int(fy), mapping, declared


def import_labels(q, raw):
    import server as s

    key = q.get('dataset', '')
    if key not in s.DATA:
        raise ValueError('Choose a source image before importing masks')
    if q.get('alignment_confirmed') != 'yes':
        raise ValueError('Confirm the mask belongs to this exact source image and channel')
    d = s.metadata(key)
    channel = int(s.number(q.get('channel', 0), 0, d['shape'][1] - 1))
    name = str(q.get('name', 'instances.tif')).strip()
    if not name.lower().endswith(('.tif', '.tiff')):
        raise ValueError('Import an instance TIFF')
    algorithm = str(q.get('algorithm', '')).strip()
    target = str(q.get('target', '')).strip()
    if not algorithm or len(algorithm) > 100 or not target or len(target) > 100:
        raise ValueError('Name the algorithm and its biological target (up to 100 characters each)')
    labels, factor, mapping, axes = _read_labels(raw, q.get('axes', ''), d['shape'])
    run_id = uuid.uuid4().hex
    folder = s.STORE / 'runs' / run_id
    spacing = [d['spacing'][0] * factor, d['spacing'][1] * factor, d['spacing'][2]]
    source = s.volume(key)[:, channel].astype(np.float32)
    if factor > 1:
        source = block_reduce(source, (1, factor, factor), np.mean).astype(np.float32)
    if source.shape != labels.shape:
        raise ValueError('Mask and source processing grids disagree')
    counts = np.bincount(labels.ravel())
    boxes = ndi.find_objects(labels)
    rows = []
    for object_id, box in enumerate(boxes, 1):
        if box is None:
            continue
        z, y, x = box
        rows.append(dict(id=object_id, original_id=mapping[str(object_id)], voxels=int(counts[object_id]),
                         x=(x.start + x.stop - 1) * factor / 2, y=(y.start + y.stop - 1) * factor / 2,
                         z=(z.start + z.stop - 1) / 2, status='candidate'))
    created = time.time()
    record = dict(id=run_id, title=algorithm, dataset=key, source=s.DATA[key]['path'],
                  sha256=s.checksum(key), created=created, parameters=None, effective_parameters=None,
                  parent=None, channel=channel, factor=factor, scope='volume', z=0,
                  method='external', target=target, objects=len(rows), threshold=None, seconds=0,
                  meaning='Imported candidate instances; source alignment confirmed by user, not independently verified',
                  calibrated=d.get('calibrated', False), spacing=spacing, shape=list(labels.shape),
                  source_shape=d['shape'], transform={'scale': [factor, factor, 1],
                                                     'xy_translation': [(factor - 1) / 2] * 2},
                  external=dict(filename=name[:200], algorithm=algorithm, target=target,
                                input_sha256=hashlib.sha256(raw).hexdigest(), axes=axes,
                                original_ids='original-ids.json', source_alignment='user-confirmed'),
                  software={'numpy': np.__version__, 'tifffile': tifffile.__version__})
    try:
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'submitted-labels.tif').write_bytes(raw)
        tifffile.imwrite(folder / 'processed.tif', source, ome=True, photometric='minisblack', metadata={'axes': 'ZYX'})
        tifffile.imwrite(folder / 'labels.tif', labels, ome=True, photometric='minisblack', metadata={'axes': 'ZYX'})
        s.atomic(folder / 'original-ids.json', mapping)
        with (folder / 'objects.csv').open('w', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=['id', 'original_id', 'voxels', 'x', 'y', 'z', 'status'])
            writer.writeheader()
            writer.writerows(rows)
        s.atomic(folder / 'run.json', record)
        s.persist(s.STORE, [folder])
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return record
