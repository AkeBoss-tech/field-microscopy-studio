"""Frozen-method stress check on procedural scenes styled from both starter scans.

Intensity statistics come from each source channel. Geometry is procedural;
these scores are not biological accuracy estimates.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import tifffile
from skimage.measure import block_reduce

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.processing import process
from tools.synthetic_benchmark import CASES, make_scene, score_instances


def style_for(path: Path, channel: int) -> dict:
    with tifffile.TiffFile(path) as file:
        series = file.series[0]
        if series.axes != 'ZCYX':
            raise ValueError('Expected the packaged ZCYX starter stack')
        volume = series.asarray(out='memmap')
        sample = np.asarray(volume[::max(1, volume.shape[0] // 8), channel, ::8, ::8],
                            dtype=np.float32).ravel()
    low, high = np.percentile(sample, [20, 99.5])
    return dict(background=float(low), signal=float(max(5, high-low)),
                read_noise=float(max(1, (high-low)*.015)))


def evaluate(out: Path) -> dict:
    # One held-out procedural seed; all recipes are fixed before scoring.
    families = {'imop_dapi': ('imop.ome.tif', 1), 'hair_channel_1': ('hair-control.ome.tif', 0)}
    methods = {
        'otsu': dict(method='otsu', distance=5),
        'watershed_5': dict(method='watershed', distance=5),
        'watershed_9': dict(method='watershed', distance=9),
        'sato_slice': dict(method='sato', sato_mode='slice', distance=5),
    }
    cases = [c for c in CASES if c[0] in ('cells_touching_3d', 'neurons_crossing_3d',
                                           'cells_empty_3d', 'cells_edge_3d',
                                           'cells_attenuated_3d')]
    rows = []
    for family, (filename, channel) in families.items():
        style = style_for(ROOT/'starter'/filename, channel)
        for index, (name, shape, count, challenge, neurons) in enumerate(cases):
            image, labels, _, _ = make_scene(shape, count, challenge, neurons, 530+index, style)
            for factor in (1, 2, 4):
                # The same block average as the app; center sampling makes an
                # exact truth mask on the coarser grid without inventing IDs.
                observed = block_reduce(image.astype(np.float32), (1, factor, factor), np.mean)
                truth = labels[:, factor//2::factor, factor//2::factor]
                if truth.shape != observed.shape:
                    raise ValueError('Scaled truth and intensity grid disagree')
                for method, overrides in methods.items():
                    recipe = dict(scope='volume', units='grid', sigma=.5, background=0,
                                  threshold=1, min_size=15, min_final_size=10,
                                  **overrides)
                    _, predicted, _, _, _ = process(observed, recipe,
                        {'spacing': [1, 1, 2], 'calibrated': True}, factor)
                    rows.append(dict(family=family, scene=name, factor=factor,
                                     method=method, **score_instances(truth, predicted)))
    summary = []
    for family in families:
        for factor in (1, 2, 4):
            for method in methods:
                selected = [r for r in rows if r['family']==family and r['factor']==factor
                            and r['method']==method]
                summary.append(dict(family=family, factor=factor, method=method,
                    macro_f1=round(float(np.mean([r['f1_iou_0_3'] for r in selected])), 3),
                    mean_absolute_count_error=round(float(np.mean([abs(r['count_error']) for r in selected])), 2),
                    empty_false_positives=next(r['false_positive_objects'] for r in selected
                                               if r['scene']=='cells_empty_3d')))
    result = dict(seed=530, source='packaged starter channel intensity quantiles',
                  warning='Procedural morphology and one held-out seed. Not expert real-image truth.',
                  methods=methods, summary=summary, rows=rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    result = evaluate(parser.parse_args().out)
    for row in result['summary']:
        print(row)
