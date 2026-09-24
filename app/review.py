"""Read-only, native-coordinate volume inspection shared by server and Pyodide."""
import base64
import io
from functools import lru_cache

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def _integer(value, upper, label):
    number = float(value)
    if not np.isfinite(number) or number != int(number) or not 0 <= number < upper:
        raise ValueError(f'{label} must be an integer from 0 to {upper - 1}')
    return int(number)


def plane(array, axis, cursor, factor=1):
    """Return exact acquired planes; a native XY voxel maps to its block index."""
    x, y, z = cursor
    if axis == 'xy':
        return array[z]
    if axis == 'xz':
        return array[:, y // factor, :]
    if axis == 'yz':
        return array[:, :, x // factor]
    raise ValueError('Unknown plane')


def encode_plane(intensity, labels, size, limits, style, opacity, selected=0):
    low, high = limits
    gray = np.uint8(np.clip((intensity.astype(np.float32) - low) / max(high - low, 1e-9), 0, 1) * 255)
    image = Image.fromarray(gray).resize(size, Image.Resampling.BILINEAR).convert('RGB')
    if labels is not None and style != 'none':
        ids = np.asarray(Image.fromarray(labels.astype(np.int32), 'I').resize(size, Image.Resampling.NEAREST))
        valid = ids > 0
        if style == 'outline':
            # Include edges against background and adjacent labels.
            border = np.zeros_like(valid)
            border[:-1] |= ids[:-1] != ids[1:]
            border[1:] |= ids[1:] != ids[:-1]
            border[:, :-1] |= ids[:, :-1] != ids[:, 1:]
            border[:, 1:] |= ids[:, 1:] != ids[:, :-1]
            valid &= border
        color = np.stack([ids * 67 % 160 + 80, ids * 113 % 160 + 80, ids * 41 % 160 + 80], -1)
        if selected:
            color[ids == selected] = [255, 215, 100]
        rgb = np.asarray(image).astype(np.float32)
        rgb[valid] = rgb[valid] * (1 - opacity) + color[valid] * opacity
        image = Image.fromarray(rgb.astype(np.uint8))
    output = io.BytesIO()
    image.save(output, format='PNG')
    return base64.b64encode(output.getvalue()).decode('ascii')


@lru_cache(maxsize=8)
def object_index(store, run_id):
    # Completed runs are immutable. Cache compact metrics, never another label volume.
    import server as s
    labels = s.run_array(run_id, 'labels')
    sizes = np.bincount(labels.ravel())
    boxes = ndi.find_objects(labels)
    edge_ids = {}
    for name, face in [('Z start', labels[0]), ('Z end', labels[-1]),
                       ('Y start', labels[:, 0]), ('Y end', labels[:, -1]),
                       ('X start', labels[:, :, 0]), ('X end', labels[:, :, -1])]:
        for value in np.unique(face):
            if value:
                edge_ids.setdefault(int(value), []).append(name)
    return sizes, boxes, edge_ids


@lru_cache(maxsize=16)
def display_window(dataset, channel, run_id, layer):
    import server as s
    array, _ = s.array_for(dataset, channel, run_id or None, layer)
    low, high = np.percentile(array, [1, 99.7])
    return float(low), max(float(high), float(low) + 1e-9)


def inspect_volume(q):
    import server as s
    key = q.get('dataset')
    if key not in s.DATA:
        raise ValueError('Unknown dataset; choose an available image')
    d = s.metadata(key)
    nz, nc, ny, nx = d['shape']
    channel = _integer(q.get('channel', 0), nc, 'Channel')
    cursor = [_integer(q.get('x', nx // 2), nx, 'X'),
              _integer(q.get('y', ny // 2), ny, 'Y'),
              _integer(q.get('z', nz // 2), nz, 'Z')]
    run_id = q.get('run') or None
    layer = q.get('layer', 'raw')
    if layer not in ['raw', 'processed', 'ridge-response']:
        raise ValueError('Unknown intensity layer')
    style = q.get('overlay', 'outline')
    if style not in ['none', 'outline', 'fill']:
        raise ValueError('Unknown mask style')
    opacity = s.number(q.get('opacity', .5), 0, 1)
    contrast = q.get('contrast', 'auto')
    if contrast not in ['auto', 'raw']:
        raise ValueError('Unknown contrast window')
    r = None
    labels = None
    factor = 1
    if run_id:
        r, _ = s.getrun(run_id)
        if r['dataset'] != key or r['channel'] != channel:
            raise ValueError('Choose a run from the active image and channel')
        if r['scope'] != 'volume' or r.get('historical'):
            raise ValueError('Orthogonal review needs a registered volume run; use Explore for this saved result')
        factor = r['factor']
        expected = (nz, ny // factor, nx // factor)
        if tuple(r['shape']) != expected:
            raise ValueError('Run dimensions do not match the source coordinate grid')
        if r['method'] != 'preprocess':
            labels = s.run_array(run_id, 'labels')
    if layer != 'raw' and not r:
        raise ValueError('Choose a processing run for this intensity layer')
    if layer == 'ridge-response' and not r.get('ridge_response'):
        raise ValueError('This run has no ridge response')
    source = s.volume(key)[:, channel]
    intensity = source if layer == 'raw' else s.run_array(run_id, layer)
    intensity_factor = 1 if layer == 'raw' else factor
    source_window = display_window(key, channel, '', 'processed')
    result_window = source_window if layer == 'raw' or contrast == 'raw' else display_window(key, channel, run_id, layer)
    x, y, z = cursor
    object_id = int(labels[z, y // factor, x // factor]) if labels is not None else 0
    obj = None
    if object_id:
        sizes, boxes, edges = object_index(str(s.STORE), run_id)
        zz, yy, xx = boxes[object_id - 1]
        voxels = int(sizes[object_id])
        sx, sy, sz = d['spacing']
        obj = dict(id=object_id, voxels=voxels,
                   volume_um3=voxels * sx * sy * sz * factor ** 2 if d.get('calibrated') else None,
                   bounds_native=[[xx.start * factor, yy.start * factor, zz.start],
                                  [min(nx, xx.stop * factor), min(ny, yy.stop * factor), zz.stop]],
                   boundary_faces=edges.get(object_id, []), status='unreviewed', run=run_id)
        from measurements import current
        with s.LOCK:
            snapshot = current(s.STORE / 'runs' / run_id)
        decision = snapshot['decisions'].get(str(object_id), {})
        obj.update(status=decision.get('status', 'unreviewed'), note=decision.get('note', ''), review_revision=snapshot['revision'])
    planes = {}
    for axis, size in [('xy', (nx, ny)), ('xz', (nx, nz)), ('yz', (ny, nz))]:
        a = plane(intensity, axis, cursor, intensity_factor)
        lab = plane(labels, axis, cursor, factor) if labels is not None else None
        planes[axis] = dict(png=encode_plane(a, lab, size, result_window, style, opacity, object_id), size=list(size))
    planes['raw'] = dict(png=encode_plane(source[z], None, (nx, ny), source_window, 'none', 0), size=[nx, ny])
    return dict(dataset=key, channel=channel, run=run_id, layer=layer, cursor=cursor,
                shape=[nz, ny, nx], spacing=d['spacing'], calibrated=bool(d.get('calibrated')),
                factor=factor, source_window=source_window, result_window=result_window,
                planes=planes, object=obj, source_intensity=float(source[z, y, x]),
                result_value=float(intensity[z, y // intensity_factor, x // intensity_factor]),
                objects=int(r['objects']) if r else 0,
                meaning=r['meaning'] if r else 'Source intensity; no segmentation')
