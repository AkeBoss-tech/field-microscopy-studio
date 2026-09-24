"""Score adjudicated real-field instance masks without mixing specimen splits.

The manifest contract is documented in docs/real-validation-protocol.md. This
tool cannot decide whether a human label is biologically correct; it checks
provenance and geometry before scoring independently supplied truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.synthetic_benchmark import score_instances


def _path(manifest: Path, value: str) -> Path:
    path = (manifest.parent / value).resolve()
    if not path.is_file():
        raise ValueError(f'Missing benchmark artifact: {value}')
    return path


def _array(path: Path) -> np.ndarray:
    array = tifffile.imread(path)
    if array.ndim == 2:
        array = array[None]
    if array.ndim != 3 or not np.issubdtype(array.dtype, np.integer) or np.any(array < 0):
        raise ValueError(f'Expected a nonnegative ZYX instance mask: {path}')
    return array


def score(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('version') != 1 or not manifest.get('fields'):
        raise ValueError('Manifest requires version 1 and at least one expert-reviewed field')
    specimen_splits = {}
    seen = set()
    rows = []
    for field in manifest['fields']:
        identifier = str(field.get('id', '')).strip()
        specimen = str(field.get('specimen_id', '')).strip()
        split = field.get('split')
        if not identifier or identifier in seen or not specimen or split not in ('development', 'holdout'):
            raise ValueError('Each field needs a unique ID, specimen ID, and development/holdout split')
        seen.add(identifier)
        specimen_splits.setdefault(specimen, set()).add(split)
        if len(specimen_splits[specimen]) > 1:
            raise ValueError(f'Specimen {specimen} appears in both development and holdout')
        reviewers = field.get('expert_reviewers')
        if field.get('truth_status') != 'expert_adjudicated' or not isinstance(reviewers, list) or not reviewers:
            raise ValueError(f'{identifier}: provide adjudicated expert truth and reviewer provenance')
        run = json.loads(_path(manifest_path, field['run_json']).read_text())
        summary = json.loads(_path(manifest_path, field['count_summary_json']).read_text())
        if run.get('method') not in ('otsu', 'watershed', 'external') or run.get('scope') != 'volume':
            raise ValueError(f'{identifier}: only registered body/nucleus volume runs can be scored')
        if not summary.get('count', {}).get('ready'):
            raise ValueError(f'{identifier}: complete the reviewed count before scoring')
        if summary.get('run_id') != run.get('id') or summary.get('source_sha256') != run.get('sha256'):
            raise ValueError(f'{identifier}: run and count summary refer to different sources')
        if field.get('source_sha256') != run.get('sha256') or field.get('channel_0based') != run.get('channel'):
            raise ValueError(f'{identifier}: source hash or channel does not match the run')
        if field.get('count_target') != summary.get('count', {}).get('target') or field.get('edge_policy') != summary.get('count', {}).get('edge_policy'):
            raise ValueError(f'{identifier}: count target or edge rule does not match reviewed output')
        prediction_path = _path(manifest_path, field['corrected_labels'])
        truth_path = _path(manifest_path, field['expert_labels'])
        expected_hash = summary.get('label_sha256')
        if expected_hash and hashlib.sha256(prediction_path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f'{identifier}: corrected label bytes differ from exported revision')
        prediction, truth = _array(prediction_path), _array(truth_path)
        if prediction.shape != truth.shape or tuple(run.get('shape', [])) != prediction.shape:
            raise ValueError(f'{identifier}: masks and run must share the same ZYX grid')
        roi = field.get('roi_zyx')
        if roi is not None:
            if not isinstance(roi, list) or len(roi) != 6 or any(not isinstance(v, int) for v in roi):
                raise ValueError(f'{identifier}: ROI must be six integer processing-grid coordinates')
            z0, y0, x0, z1, y1, x1 = roi
            if not (0 <= z0 < z1 <= truth.shape[0] and 0 <= y0 < y1 <= truth.shape[1]
                    and 0 <= x0 < x1 <= truth.shape[2]):
                raise ValueError(f'{identifier}: ROI is outside the label grid')
            prediction = prediction[z0:z1, y0:y1, x0:x1]
            truth = truth[z0:z1, y0:y1, x0:x1]
        result = score_instances(truth, prediction)
        rows.append(dict(id=identifier, specimen_id=specimen, split=split,
                         target=field['count_target'], edge_policy=field['edge_policy'],
                         source_sha256=run['sha256'], run_id=run['id'],
                         label_revision=summary.get('label_revision'), roi_zyx=roi,
                         expert_reviewers=reviewers, **result))
    splits = {}
    for split in ('development', 'holdout'):
        group = [row for row in rows if row['split'] == split]
        if group:
            splits[split] = dict(fields=len(group), specimens=len({row['specimen_id'] for row in group}),
                                 macro_f1_iou_0_3=float(np.mean([row['f1_iou_0_3'] for row in group])),
                                 mean_absolute_count_error=float(np.mean([abs(row['count_error']) for row in group])),
                                 total_signed_count_error=int(sum(row['count_error'] for row in group)))
    return dict(fields=rows, splits=splits,
                caveat='Expert status is declared in the manifest; this tool verifies provenance and mask agreement, not biological truth.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = score(args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Scored {len(result['fields'])} adjudicated fields; splits: {', '.join(result['splits'])}")
