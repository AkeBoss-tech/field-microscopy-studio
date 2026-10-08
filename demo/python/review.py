"""Read-only, native-coordinate volume inspection shared by server and Pyodide."""
import base64
import io
from functools import lru_cache

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull, QhullError
from skimage.measure import find_contours


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
def object_index(store, run_id, label_revision=None):
    # Cache geometry by immutable label revision, not by the mutable latest pointer.
    from corrections import label_array
    labels = label_array(run_id, label_revision)
    sizes = np.bincount(labels.ravel())
    boxes = ndi.find_objects(labels)
    edge_ids = {}
    for name, face in [('Z start', labels[0]), ('Z end', labels[-1]),
                       ('Y start', labels[:, 0]), ('Y end', labels[:, -1]),
                       ('X start', labels[:, :, 0]), ('X end', labels[:, :, -1])]:
        for value in np.unique(face):
            if value:
                edge_ids.setdefault(int(value), []).append(name)
    import server as s
    run, _ = s.getrun(run_id)
    bounds = run.get('region_bounds')
    if bounds:
        x0, y0, z0, x1, y1, z1 = bounds
        factor = run['factor']
        x0, y0, x1, y1 = x0//factor, y0//factor, x1//factor, y1//factor
        # The processing service stores full-size arrays but labels only the
        # chosen region. Its faces can truncate an object before volume edges.
        faces = [('Region Z start', z0 > 0, labels[z0, y0:y1, x0:x1]),
                 ('Region Z end', z1 < labels.shape[0], labels[z1-1, y0:y1, x0:x1]),
                 ('Region Y start', y0 > 0, labels[z0:z1, y0, x0:x1]),
                 ('Region Y end', y1 < labels.shape[1], labels[z0:z1, y1-1, x0:x1]),
                 ('Region X start', x0 > 0, labels[z0:z1, y0:y1, x0]),
                 ('Region X end', x1 < labels.shape[2], labels[z0:z1, y0:y1, x1-1])]
        for name, internal, face in faces:
            if not internal:
                continue
            for value in np.unique(face):
                if value:
                    edge_ids.setdefault(int(value), []).append(name)
    return sizes, boxes, edge_ids


def footprint_morphology(mask, spacing_xy=(1., 1.)):
    """Shape of an object's XY footprint (union across Z), never 3D sphericity.

    Area counts occupied pixels. Perimeter and circularity use padded half-pixel
    marching-squares polygons, including holes, in the same XY coordinate units.
    Circularity uses polygon area so isolated pixels do not exceed one. All
    descriptors describe the saved processing grid and depend on its resolution.
    """
    footprint = np.any(mask, axis=0) if mask.ndim == 3 else np.asarray(mask, bool)
    sx, sy = map(float, spacing_xy)
    count = int(np.count_nonzero(footprint))
    if not count:
        return {}
    contours = find_contours(np.pad(footprint, 1).astype(float), .5)
    perimeter = 0.
    signed_area = 0.
    outlines = []
    for contour in contours:
        points = contour[:, [1, 0]] * [sx, sy]
        perimeter += float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
        signed_area += float(np.sum(points[:-1, 0]*points[1:, 1] - points[1:, 0]*points[:-1, 1])/2)
        outlines.append(points[:-1])
    contour_area = abs(signed_area)
    area = count*sx*sy
    solidity = None
    try:
        hull_area = float(ConvexHull(np.concatenate(outlines)).volume)
        solidity = min(1., contour_area/hull_area) if hull_area else None
    except QhullError:
        pass
    # Pixel centers plus the within-pixel variance give stable axes for even a
    # one-pixel candidate; physical anisotropy is included, not assumed away.
    coords = np.column_stack(np.nonzero(footprint))[:, [1, 0]].astype(float)*[sx, sy]
    centered = coords-coords.mean(axis=0)
    covariance = centered.T@centered/count + np.diag([sx*sx, sy*sy])/12
    minor, major = np.maximum(0., np.linalg.eigvalsh(covariance))
    major_axis, minor_axis = 4*np.sqrt(major), 4*np.sqrt(minor)
    return dict(xy_area=area, xy_contour_area=contour_area, xy_perimeter=perimeter,
                xy_circularity=float(4*np.pi*contour_area/perimeter**2) if perimeter else None,
                xy_solidity=solidity, xy_eccentricity=float(np.sqrt(1-minor/major)) if major else 0.,
                xy_aspect_ratio=float(major_axis/minor_axis) if minor_axis else None,
                xy_major_axis=float(major_axis), xy_minor_axis=float(minor_axis),
                xy_equivalent_diameter=float(np.sqrt(4*area/np.pi)))


@lru_cache(maxsize=8)
def morphology_index(store, run_id, label_revision, spacing_xyz, calibrated):
    from corrections import label_array
    labels = label_array(run_id, label_revision)
    _, boxes, _ = object_index(store, run_id, label_revision)
    result = {}
    for object_id, box in enumerate(boxes, 1):
        if box is None:
            continue
        mask = labels[box] == object_id
        metrics = footprint_morphology(mask, spacing_xyz[:2])
        metrics.update(morphology_basis='XY footprint: union of labeled voxels across acquired Z',
                       morphology_units='µm' if calibrated else 'native px',
                       bbox_extent_3d=float(np.count_nonzero(mask)/mask.size),
                       xy_area_um2=metrics['xy_area'] if calibrated else None,
                       xy_perimeter_um=metrics['xy_perimeter'] if calibrated else None)
        result[object_id] = metrics
    return result


@lru_cache(maxsize=8)
def network_index(store, run_id, label_revision, spacing_xyz, calibrated):
    """Network metrics always follow the inspected immutable label revision."""
    import server as s
    run, folder = s.getrun(run_id)
    if not run.get('neurites'):
        return {}
    from neurites import network_measurements, measure
    if label_revision is None:
        rows = network_measurements(folder)
    else:
        from corrections import label_array
        summary = run['neurites']
        _, measured, _, _ = measure(label_array(run_id, label_revision), spacing_xyz[::-1], calibrated,
                                     summary.get('pruning_minimum', 0), summary.get('pruning_units') == 'µm')
        rows = {row['id']:row for row in measured}
    return {object_id:dict(network_length_um=row['length_um'], network_length_grid=row['length_grid'],
                           network_branches=row['branches'], network_endpoints=row['endpoints'],
                           network_junctions=row['junctions'],
                           network_metrics_basis='Skeleton of current label revision; connected network, not neuron ownership')
            for object_id, row in rows.items()}


@lru_cache(maxsize=16)
def display_window(dataset, channel, run_id, layer):
    import server as s
    if layer == 'skeleton':
        return 0., 1.
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
    if layer not in ['raw', 'processed', 'ridge-response', 'skeleton']:
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
    label_revision = None
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
            from corrections import active
            labels, correction = active(run_id)
            label_revision = correction['revision']
    if layer != 'raw' and not r:
        raise ValueError('Choose a processing run for this intensity layer')
    if layer == 'ridge-response' and not r.get('ridge_response'):
        raise ValueError('This run has no ridge response')
    if layer == 'skeleton' and not r.get('neurites'):
        raise ValueError('This run has no measured neurite centerline')
    calibrated = bool(r.get('calibrated', d.get('calibrated', False))) if r else bool(d.get('calibrated'))
    source_spacing = ([r['spacing'][0]/factor, r['spacing'][1]/factor, r['spacing'][2]]
                      if r and r.get('spacing') else d['spacing'])
    source = s.volume(key)[:, channel]
    intensity = source if layer == 'raw' else s.run_array(run_id, layer)
    intensity_factor = 1 if layer == 'raw' else factor
    source_window = display_window(key, channel, '', 'processed')
    result_window = ((0., 1.) if layer == 'skeleton' else
                     source_window if layer == 'raw' or contrast == 'raw' else display_window(key, channel, run_id, layer))
    x, y, z = cursor
    object_id = int(labels[z, y // factor, x // factor]) if labels is not None else 0
    obj = None
    if object_id:
        sizes, boxes, edges = object_index(str(s.STORE), run_id, label_revision)
        zz, yy, xx = boxes[object_id - 1]
        voxels = int(sizes[object_id])
        sx, sy, sz = source_spacing
        obj = dict(id=object_id, voxels=voxels,
                   volume_um3=voxels * sx * sy * sz * factor ** 2 if calibrated else None,
                   bounds_native=[[xx.start * factor, yy.start * factor, zz.start],
                                  [min(nx, xx.stop * factor), min(ny, yy.stop * factor), zz.stop]],
                   boundary_faces=edges.get(object_id, []), status='unreviewed', run=run_id)
        working_spacing = (sx*factor, sy*factor, sz) if calibrated else (factor, factor, 1.)
        obj.update(morphology_index(str(s.STORE), run_id, label_revision,
                                    working_spacing, calibrated)[object_id])
        obj.update(network_index(str(s.STORE), run_id, label_revision,
                                 working_spacing, calibrated).get(object_id, {}))
        from measurements import current, decision_for
        from corrections import current as correction_current
        with s.LOCK:
            snapshot = current(s.STORE / 'runs' / run_id)
            correction = correction_current(s.STORE / 'runs' / run_id)
        decision = decision_for(snapshot, correction, object_id)
        obj.update(status=decision.get('status', 'unreviewed'), note=decision.get('note', ''),
                   review_revision=snapshot['revision'], label_revision=label_revision)
    planes = {}
    for axis, size in [('xy', (nx, ny)), ('xz', (nx, nz)), ('yz', (ny, nz))]:
        a = plane(intensity, axis, cursor, intensity_factor)
        lab = plane(labels, axis, cursor, factor) if labels is not None else None
        planes[axis] = dict(png=encode_plane(a, lab, size, result_window, style, opacity, object_id), size=list(size))
    planes['raw'] = dict(png=encode_plane(source[z], None, (nx, ny), source_window, 'none', 0), size=[nx, ny])
    return dict(dataset=key, channel=channel, run=run_id, layer=layer, cursor=cursor,
                shape=[nz, ny, nx], spacing=source_spacing, calibrated=calibrated,
                factor=factor, source_window=source_window, result_window=result_window,
                planes=planes, object=obj, source_intensity=float(source[z, y, x]),
                result_value=float(intensity[z, y // intensity_factor, x // intensity_factor]),
                objects=int(np.count_nonzero(np.unique(labels))) if labels is not None else 0,
                label_revision=label_revision,
                meaning=r['meaning'] if r else 'Source intensity; no segmentation')
