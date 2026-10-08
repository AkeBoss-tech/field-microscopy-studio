"""Shared processing for saved runs and bounded, unsaved ROI experiments."""
import math
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.feature import peak_local_max
from skimage.filters import threshold_otsu, threshold_local, sato
from skimage.morphology import remove_small_objects, h_maxima
from skimage.segmentation import watershed
from neurites import METHODS as NEURITE_METHODS, segment as neurite_segment

INSTANCE_METHODS = ('otsu', 'watershed', 'adaptive_regions', 'prominence_watershed', 'external')
METHODS = ('preprocess', *INSTANCE_METHODS[:-1], 'sato', *NEURITE_METHODS)


def number(value, low, high):
    n = float(value)
    if not np.isfinite(n) or not low <= n <= high:
        raise ValueError('Parameter out of range')
    return n


def settings(params, metadata, factor, ndim):
    physical = params.get('units') == 'physical'
    if physical and not metadata.get('calibrated'):
        raise ValueError('Physical controls require calibrated source spacing')
    sx, sy, sz = metadata['spacing']
    voxel = sx * sy * factor**2 * (sz if ndim == 3 else 1)
    if physical:
        sigma = number(params.get('sigma_um', 0), 0, 100)
        background = number(params.get('background_um', 0), 0, 500)
        sigmas = [sigma / (sy*factor), sigma / (sx*factor)]
        backgrounds = [background / (sy*factor), background / (sx*factor)]
        minimum = max(1, math.ceil(number(params.get('min_size_physical', 0), 0, 1e9) / voxel))
        final = math.ceil(number(params.get('min_final_physical', 0), 0, 1e9) / voxel)
        distance = number(params.get('seed_distance_um', 2), .001, 1000)
    else:
        sigmas = [number(params.get('sigma', 0), 0, 5)] * 2
        backgrounds = [number(params.get('background', 0), 0, 64)] * 2
        minimum = int(number(params.get('min_size', 30), 1, 1000000))
        final = int(number(params.get('min_final_size', 0), 0, 1000000))
        distance = int(number(params.get('distance', 5), 1, 100))
    return dict(units='physical' if physical else 'grid', sigma_yx=sigmas,
                background_yx=backgrounds, min_size=minimum, min_final_size=final,
                seed_distance=distance, spacing_zyx=[sz, sy*factor, sx*factor])


def physical_peaks(distance, mask, spacing, separation):
    # Candidate maxima are ranked by distance, then greedily suppressed in µm.
    peaks = peak_local_max(distance, min_distance=1, labels=mask, exclude_border=False)
    if not len(peaks):
        return peaks
    peaks = peaks[np.argsort(-distance[tuple(peaks.T)], kind='stable')]
    coords = peaks * np.asarray(spacing)
    tree = cKDTree(coords)
    suppressed = np.zeros(len(peaks), bool)
    chosen = []
    for i in range(len(peaks)):
        if not suppressed[i]:
            chosen.append(i)
            suppressed[tree.query_ball_point(coords[i], separation)] = True
    return peaks[chosen]


def process(array, params, metadata, factor, cancelled=None):
    a = array.astype(np.float32, copy=True)
    dimensionality = 3 if a.shape[0] > 1 else 2
    effective = settings(params, metadata, factor, 3 if params.get("scope", "volume") == "volume" else 2)
    if any(effective['sigma_yx']):
        a = ndi.gaussian_filter(a, [0, *effective['sigma_yx']])
    if any(effective['background_yx']):
        a = np.maximum(a - ndi.gaussian_filter(a, [0, *effective['background_yx']]), 0)
    if params.get('normalize', False):
        low, high = np.percentile(a, [1, 99.5])
        a = np.clip((a-low) / max(high-low, 1e-12), 0, 1)
    method = params.get('method', 'otsu')
    if method not in METHODS:
        raise ValueError('Unknown algorithm')
    labels = np.zeros(a.shape, np.uint32)
    threshold = None
    score = a
    if cancelled and cancelled():
        return a, labels, score, threshold, effective
    if method != 'preprocess':
        x = a if dimensionality == 3 else a[0]
        sato_mode = params.get('sato_mode', 'volume')
        if method in NEURITE_METHODS:
            labels, score, threshold = neurite_segment(a, params, metadata, factor, effective)
        elif method == 'sato':
            if sato_mode not in ['slice', 'volume']:
                raise ValueError('Invalid Sato dimensional mode')
            score = np.stack([sato(p, sigmas=[1, 2], black_ridges=False) for p in x]) if x.ndim == 3 and sato_mode == 'slice' else sato(x, sigmas=[1, 2], black_ridges=False)
        else:
            score = x
        if method not in NEURITE_METHODS:
            threshold = float(threshold_otsu(score)) * number(params.get('threshold', 1), .1, 4)
            mask = score > threshold
            if method == 'adaptive_regions':
                block = int(number(params.get('local_window', 31), 3, 511))
                if block % 2 == 0:
                    raise ValueError('Local window must be odd')
                offset = number(params.get('local_offset', 0), -10000, 10000)
                floor = number(params.get('local_floor', .5), 0, 2)
                local = np.stack([threshold_local(plane, block, offset=offset) for plane in a])
                if dimensionality == 2:
                    local = local[0]
                mask = (score > local) & (score > threshold * floor)
                effective.update(local_window=block, local_offset=offset, local_floor=floor,
                                 threshold_kind='per-XY Gaussian local threshold plus global Otsu floor')
            mask = remove_small_objects(mask, min_size=effective['min_size'])
        if method in ('watershed', 'prominence_watershed'):
            spacing = effective['spacing_zyx'] if dimensionality == 3 else effective['spacing_zyx'][1:]
            dist = ndi.distance_transform_edt(mask, sampling=spacing if effective['units'] == 'physical' else None)
            markers = np.zeros(mask.shape, np.int32)
            if method == 'watershed':
                peaks = physical_peaks(dist, mask, spacing, effective['seed_distance']) if effective['units'] == 'physical' else peak_local_max(dist, min_distance=effective['seed_distance'], labels=mask, exclude_border=False)
                if len(peaks):
                    markers[tuple(peaks.T)] = np.arange(1, len(peaks)+1)
            if method == 'prominence_watershed':
                prominence = number(params.get('peak_prominence', .5), .001, 1000)
                effective['peak_prominence'] = prominence
                markers = ndi.label(h_maxima(dist, prominence) & mask)[0] if mask.any() else np.zeros(mask.shape, np.int32)
                # Keep foreground components even when none of their peaks reaches h.
                components, count = ndi.label(mask)
                seeded = set(np.unique(components[markers > 0]))
                next_id = int(markers.max())
                for component, region in enumerate(ndi.find_objects(components), 1):
                    if region is not None and component not in seeded:
                        local_mask = components[region] == component
                        position = np.unravel_index(np.argmax(np.where(local_mask, dist[region], -1)), local_mask.shape)
                        next_id += 1
                        markers[region][position] = next_id
            labels = watershed(-dist, markers, mask=mask).astype(np.uint32)
        elif method not in NEURITE_METHODS:
            labels = ndi.label(mask)[0].astype(np.uint32)
        if effective['min_final_size']:
            sizes = np.bincount(labels.ravel())
            keep = sizes >= effective['min_final_size']; keep[0] = False
            mapping = np.cumsum(keep, dtype=np.uint32); mapping[~keep] = 0
            labels = mapping[labels]
        if labels.ndim == 2:
            labels = labels[None]
    if score.ndim == 2:
        score = score[None]
    return a, labels, score, threshold, effective
