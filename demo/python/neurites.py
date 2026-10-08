"""Candidate neurite signal and calibrated digital-skeleton measurements.

Connected signal is a network component, never an inferred neuron identity. Graph
edges use native spacing. Corner shortcuts are removed when an occupied axial
intermediate already connects the two voxels, avoiding diagonal double counting.
"""
from itertools import product, combinations
from functools import lru_cache
from pathlib import Path
import csv
import io
import numpy as np
from scipy import ndimage as ndi
from skimage.filters import sato, frangi, meijering, threshold_otsu, threshold_local
from skimage.morphology import skeletonize, remove_small_objects

METHODS = ('neurite_otsu', 'neurite_adaptive', 'neurite_sato', 'neurite_frangi', 'neurite_meijering')
RIDGE_METHODS = ('sato', 'neurite_sato', 'neurite_frangi', 'neurite_meijering')


def finite(value, low, high, name):
    value = float(value)
    if not np.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value


def ridge_settings(params, metadata, factor, effective):
    mode = params.get('neurite_mode', 'slice')
    if mode not in ('slice', 'volume'):
        raise ValueError('Neurite ridge mode must be slice or volume')
    physical = params.get('units') == 'physical'
    scales = params.get('ridge_scales_um') if physical else params.get('ridge_sigmas')
    if scales is None:
        scales = [1, 2, 3]
        if physical:
            scales = [v * metadata['spacing'][0] * factor for v in scales]
    if not isinstance(scales, (list, tuple)) or not 1 <= len(scales) <= 8:
        raise ValueError('Choose 1–8 ridge scales')
    scales = [finite(v, .05, 32 if not physical else 100, 'Ridge scale') for v in scales]
    if physical:
        if not metadata.get('calibrated'):
            raise ValueError('Physical ridge scales require calibrated source spacing')
        sx, sy, sz = metadata['spacing']
        if not np.isclose(sx, sy):
            raise ValueError('Physical ridge scales require equal XY spacing; use grid scales')
        if mode == 'volume' and not np.isclose(sz, sx * factor):
            raise ValueError('Physical volume ridge scales require isotropic spacing; choose slice filtering')
        scales = [v / (sx * factor) for v in scales]
        if max(scales) > 32:
            raise ValueError('Ridge scale exceeds 32 working pixels; reduce the scale or XY resolution')
    effective.update(neurite_mode=mode, ridge_sigmas=scales,
                     ridge_scale_units='working pixels',
                     neurite_min_branch_length=finite(params.get('neurite_min_branch_length_um' if physical else 'neurite_min_branch_length', 0), 0, 10000, 'Minimum branch length'),
                     neurite_soma_radius=finite(params.get('neurite_soma_radius_um' if physical else 'neurite_soma_radius', 0), 0, 1000, 'Soma exclusion radius'))
    effective['neurite_length_units'] = 'µm' if metadata.get('calibrated') else 'working pixels'
    effective['neurite_pruning_units'] = 'µm' if physical else 'working pixels'
    return mode, scales


def segment(array, params, metadata, factor, effective):
    mode, scales = ridge_settings(params, metadata, factor, effective)
    method = params['method']
    x = array if len(array) > 1 else array[0]
    if method in ('neurite_sato', 'neurite_frangi', 'neurite_meijering'):
        function = {'neurite_sato': sato, 'neurite_frangi': frangi, 'neurite_meijering': meijering}[method]
        score = np.stack([function(p, sigmas=scales, black_ridges=False) for p in x]) if x.ndim == 3 and mode == 'slice' else function(x, sigmas=scales, black_ridges=False)
    else:
        score = x
    multiplier = finite(params.get('threshold', 1), .1, 4, 'Threshold multiplier')
    if method == 'neurite_adaptive':
        block = finite(params.get('adaptive_block_size', 31), 3, 255, 'Adaptive window')
        if block != int(block) or int(block) % 2 != 1:
            raise ValueError('Adaptive window must be an odd integer')
        offset = finite(params.get('adaptive_offset', 0), -10000, 10000, 'Adaptive offset')
        floor = finite(params.get('adaptive_floor', .25), 0, 2, 'Adaptive signal floor')
        floor_value = max(0., float(threshold_otsu(score.ravel())) * floor)
        threshold = None
        local = np.stack([threshold_local(p, int(block), offset=offset) for p in x]) if x.ndim == 3 else threshold_local(x, int(block), offset=offset)
        # Strictly exclude zero signal even when local offset lowers the threshold.
        mask = (score > local * multiplier) & (score > floor_value)
        effective.update(adaptive_block_size=int(block), adaptive_offset=offset,
                         adaptive_floor=floor, adaptive_floor_value=floor_value)
    else:
        threshold = float(threshold_otsu(score.ravel())) * multiplier
        mask = score > threshold
    radius = effective['neurite_soma_radius']
    if radius:
        sampling = effective['spacing_zyx'][1:] if params.get('units') == 'physical' else None
        # A 2D width estimate is deliberate: a short Z stack is not evidence of a thin soma.
        planes = mask if mask.ndim == 3 else mask[None]
        cores = [ndi.distance_transform_edt(p, sampling=sampling) >= radius for p in planes]
        excluded = np.stack([ndi.distance_transform_edt(~core, sampling=sampling) <= radius if core.any() else core for core in cores])
        mask = mask & ~(excluded if mask.ndim == 3 else excluded[0])
    mask = remove_small_objects(mask, min_size=effective['min_size'], connectivity=mask.ndim)
    labels = ndi.label(mask, structure=np.ones((3,) * mask.ndim, bool))[0].astype(np.uint32)
    return labels if labels.ndim == 3 else labels[None], score if score.ndim == 3 else score[None], threshold


def _graph(skeleton, spacing):
    coordinates = np.argwhere(skeleton)
    if len(coordinates) > 600000:
        raise ValueError('Neurite graph exceeds 600,000 skeleton voxels; choose a region or lower resolution')
    points = {tuple(p): i for i, p in enumerate(coordinates)}
    adjacency = [[] for _ in coordinates]
    offsets = [o for o in product((-1, 0, 1), repeat=skeleton.ndim) if any(o) and next(v for v in o if v) > 0]
    spacing = np.asarray(spacing, float)
    for point, i in points.items():
        for delta in offsets:
            other = tuple(p + v for p, v in zip(point, delta))
            j = points.get(other)
            if j is None:
                continue
            axes = [axis for axis, v in enumerate(delta) if v]
            shortcut = False
            if len(axes) > 1:
                for size in range(1, len(axes)):
                    for subset in combinations(axes, size):
                        intermediate = tuple(point[k] + (delta[k] if k in subset else 0) for k in range(skeleton.ndim))
                        if intermediate in points:
                            shortcut = True
                            break
                    if shortcut:
                        break
            if shortcut:
                continue
            length = float(np.linalg.norm(np.asarray(delta) * spacing))
            adjacency[i].append((j, length)); adjacency[j].append((i, length))
    return coordinates, adjacency


def skeleton_graph(skeleton, spacing):
    """Collapse adjacent junction voxels; trace each remaining graph edge once."""
    skeleton = np.asarray(skeleton, bool)
    spacing = np.asarray(spacing, float)
    if spacing.shape != (skeleton.ndim,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError('Skeleton spacing must be finite and positive')
    coordinates, adjacency = _graph(skeleton, spacing)
    degree = np.asarray([len(a) for a in adjacency])
    junction_nodes = set(np.flatnonzero(degree >= 3))
    junction_ids = {}
    junction_count = 0
    for seed in sorted(junction_nodes):
        if seed in junction_ids:
            continue
        junction_count += 1; stack = [seed]; junction_ids[seed] = junction_count
        while stack:
            for neighbour, _ in adjacency[stack.pop()]:
                if neighbour in junction_nodes and neighbour not in junction_ids:
                    junction_ids[neighbour] = junction_count; stack.append(neighbour)
    visited = set()
    total = sum(weight for i, a in enumerate(adjacency) for j, weight in a if i < j)
    pairs = np.asarray([(i, j) for i, a in enumerate(adjacency) for j, _ in a if i < j], dtype=int)
    grid_length = float(np.linalg.norm(coordinates[pairs[:, 0]] - coordinates[pairs[:, 1]], axis=1).sum()) if len(pairs) else 0.
    junction_length = 0.
    for i in junction_nodes:
        for j, weight in adjacency[i]:
            if j in junction_nodes:
                visited.add(tuple(sorted((i, j))))
                if i < j:
                    junction_length += weight
    branches = []
    def walk(start, next_node, first_length):
        path = [start, next_node]; length = first_length
        visited.add(tuple(sorted((start, next_node))))
        previous, node = start, next_node
        while degree[node] == 2 and node != start:
            nxt, weight = next((j, w) for j, w in adjacency[node] if j != previous)
            edge = tuple(sorted((node, nxt)))
            if edge in visited:
                break
            visited.add(edge); path.append(nxt); length += weight
            previous, node = node, nxt
        ends = [path[0], path[-1]]
        endpoint_count = sum(degree[v] == 1 for v in ends)
        kind = 'loop' if path[-1] == start else 'isolated path' if endpoint_count == 2 else 'terminal' if endpoint_count else 'junction link'
        delta = (coordinates[path[-1]] - coordinates[start]) * spacing
        straight = float(np.linalg.norm(delta))
        branches.append(dict(length=float(length), kind=kind, endpoints=int(endpoint_count),
                             tortuosity=float(length / straight) if straight > 0 else None,
                             nodes=path, start=coordinates[start].tolist(), end=coordinates[path[-1]].tolist()))
    for i in np.flatnonzero(degree != 2):
        for j, weight in adjacency[i]:
            if tuple(sorted((int(i), j))) not in visited:
                walk(int(i), j, weight)
    for i, a in enumerate(adjacency):
        for j, weight in a:
            if tuple(sorted((i, j))) not in visited:
                walk(i, j, weight)
    return dict(length=float(total), grid_length=grid_length, branches=branches, endpoints=int(np.sum(degree == 1)),
                junctions=junction_count, junction_length=float(junction_length), isolated_voxels=int(np.sum(degree == 0)),
                skeleton_voxels=len(coordinates), coordinates=coordinates, degree=degree)


def prune(skeleton, spacing, minimum):
    result = skeleton.copy()
    if not minimum:
        return result
    for _ in range(8):
        graph = skeleton_graph(result, spacing); remove = set()
        for branch in graph['branches']:
            if branch['length'] < minimum and branch['kind'] in ('terminal', 'isolated path'):
                path = branch['nodes']
                if branch['kind'] == 'isolated path':
                    remove.update(path)
                else:
                    # Keep the junction endpoint; remove only the terminal spur.
                    remove.update(v for v in path if graph['degree'][v] < 3)
        if not remove:
            break
        result[tuple(graph['coordinates'][sorted(remove)].T)] = False
    return result


def measure(labels, spacing_zyx, calibrated=True, minimum_branch_length=0, pruning_physical=False):
    """Measure each connected labeled network; lengths exclude no inferred soma by default."""
    labels = np.asarray(labels)
    if labels.ndim != 3:
        raise ValueError('Neurite labels must be ZYX')
    is2d = labels.shape[0] == 1
    mask = labels[0] > 0 if is2d else labels > 0
    skeleton = skeletonize(mask)
    measured_spacing = spacing_zyx[1:] if is2d else spacing_zyx
    if not calibrated:
        measured_spacing = [1.] * skeleton.ndim
    pruning_spacing = measured_spacing if pruning_physical else [1.] * skeleton.ndim
    skeleton = prune(skeleton, pruning_spacing, minimum_branch_length)
    sid = labels[0] if is2d else labels
    rows, branch_rows = [], []
    # Bounding boxes avoid rescanning the full image for each small disconnected object.
    objects = ndi.find_objects(labels)
    for network, box3 in enumerate(objects, 1):
        if box3 is None:
            continue
        box = box3[1:] if is2d else box3
        local = skeleton[box] & (sid[box] == network)
        graph = skeleton_graph(local, measured_spacing)
        physical_length = graph['length'] if calibrated else None
        row = dict(id=network, skeleton_voxels=graph['skeleton_voxels'], length_um=physical_length,
                   length_grid=graph['grid_length'],
                   branches=len(graph['branches']), endpoints=graph['endpoints'], junctions=graph['junctions'],
                   junction_internal_length=graph['junction_length'], mean_branch_length=float(np.mean([v['length'] for v in graph['branches']])) if graph['branches'] else 0,
                   maximum_branch_length=max([v['length'] for v in graph['branches']], default=0),
                   isolated_voxels=graph['isolated_voxels'], units='µm' if calibrated else 'working pixels', status='candidate')
        rows.append(row)
        for branch_id, branch in enumerate(graph['branches'], 1):
            origin = np.asarray([b.start for b in box])
            start, end = np.asarray(branch['start']) + origin, np.asarray(branch['end']) + origin
            if is2d:
                start = np.r_[0, start]; end = np.r_[0, end]
            branch_rows.append(dict(network_id=network, branch_id=branch_id, kind=branch['kind'],
                                    length=branch['length'], units='µm' if calibrated else 'working pixels',
                                    tortuosity=branch['tortuosity'], start_zyx=start.tolist(), end_zyx=end.tolist()))
    summary = dict(networks=len(rows), skeleton_voxels=int(skeleton.sum()), total_length_um=sum(r['length_um'] for r in rows) if calibrated else None,
                   total_length_grid=sum(r['length_grid'] for r in rows), branches=sum(r['branches'] for r in rows),
                   endpoints=sum(r['endpoints'] for r in rows), junctions=sum(r['junctions'] for r in rows),
                   length_units='µm' if calibrated else 'working pixels', spacing_zyx=list(spacing_zyx), calibrated=calibrated,
                   dimensionality='2D projection/slice' if is2d else '3D acquired volume',
                   meaning='Candidate network geometry; crossing fibers and somas can join. Not neuron ownership or validated biological length.',
                   length_definition='Sum of unique skeleton-center edges with occupied-intermediate corner shortcuts removed. Junction voxels are grouped; branches exclude internal junction edges.',
                   pruning_minimum=minimum_branch_length, pruning_units='µm' if pruning_physical else 'working pixels')
    return skeleton[None] if is2d else skeleton, rows, branch_rows, summary


def csv_bytes(rows, fieldnames):
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader(); writer.writerows(rows)
    return output.getvalue().encode()

NETWORK_FIELDS = ['id', 'skeleton_voxels', 'length_um', 'length_grid', 'branches', 'endpoints', 'junctions', 'junction_internal_length', 'mean_branch_length', 'maximum_branch_length', 'isolated_voxels', 'units', 'status']
BRANCH_FIELDS = ['network_id', 'branch_id', 'kind', 'length', 'units', 'tortuosity', 'start_zyx', 'end_zyx']


@lru_cache(maxsize=4)
def network_measurements(folder):
    """Read immutable saved network measurements, keyed by candidate label ID."""
    path = Path(folder) / 'neurites.csv'
    if not path.is_file():
        return {}
    measurements = {}
    integer_fields = {'id', 'skeleton_voxels', 'branches', 'endpoints', 'junctions', 'isolated_voxels'}
    with path.open() as handle:
        for row in csv.DictReader(handle):
            value = {}
            for name in NETWORK_FIELDS:
                raw = row.get(name, '')
                value[name] = raw if name in {'units', 'status'} else None if raw == '' else int(raw) if name in integer_fields else float(raw)
            measurements[value['id']] = value
    return measurements
