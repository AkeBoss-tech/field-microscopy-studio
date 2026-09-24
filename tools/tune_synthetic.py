"""Tune body-candidate recipes on development phantoms, then score held-out seeds.

This is a reproducible software benchmark. A real expert-labeled holdout is
required before applying a selected recipe to biological counting.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.processing import process
from tools.synthetic_benchmark import CASES, CORE_CASES, make_scene, reference_style, score_instances


DEVELOPMENT_SEEDS = (17, 31)
HOLDOUT_SEED = 53
METADATA = {"spacing": [1.0, 1.0, 2.0], "calibrated": True}


def recipes() -> list[dict]:
    result = []
    for method in ("otsu", "watershed"):
        for sigma in (0.5, 1.0):
            for threshold in (0.8, 1.0, 1.2):
                distances = (5, 7, 9, 11) if method == "watershed" else (5,)
                for distance in distances:
                    result.append({"method": method, "scope": "volume", "units": "grid",
                                   "sigma": sigma, "background": 0, "threshold": threshold,
                                   "min_size": 15, "min_final_size": 10,
                                   "distance": distance})
    return result


def scenes(dimension: str, seeds: tuple[int, ...], style: dict,
           cases=CORE_CASES) -> list[tuple[str, np.ndarray, np.ndarray]]:
    items = []
    for seed in seeds:
        for index, (name, shape, count, challenge, neurons) in enumerate(CASES):
            if (name, shape, count, challenge, neurons) not in cases:
                continue
            if ("3D" if shape[0] > 1 else "2D") != dimension:
                continue
            image, labels, _, _ = make_scene(shape, count, challenge, neurons,
                                              seed + index, style)
            items.append((f"{name}@{seed + index}", image, labels))
    return items


def evaluate(recipe: dict, items: list[tuple[str, np.ndarray, np.ndarray]]) -> dict:
    rows = []
    for name, image, truth in items:
        _, predicted, _, _, _ = process(image, recipe, METADATA, 1)
        rows.append({"scene": name, **score_instances(truth, predicted)})
    return {"macro_f1": float(np.mean([r["f1_iou_0_3"] for r in rows])),
            "mean_absolute_count_error": float(np.mean([abs(r["count_error"]) for r in rows])),
            "scenes": rows}


def tune(reference_2d: Path | None, reference_3d: Path | None) -> dict:
    styles = {"2D": reference_style(reference_2d),
              "3D": reference_style(reference_3d or reference_2d)}
    output = {"development_seeds": list(DEVELOPMENT_SEEDS), "holdout_seed": HOLDOUT_SEED,
              "source_sha256": {key: style["source_sha256"] for key, style in styles.items()},
              "objective": "Mean one-to-one body-instance F1 at IoU >= 0.3; count error breaks ties",
              "warning": "Synthetic holdout is a software regression check, not real-cell validation.",
              "dimensions": {}}
    base = next(r for r in recipes() if r["method"] == "watershed" and r["sigma"] == .5
                and r["threshold"] == 1 and r["distance"] == 5)
    for dimension in ("2D", "3D"):
        development = scenes(dimension, DEVELOPMENT_SEEDS, styles[dimension])
        holdout = scenes(dimension, (HOLDOUT_SEED,), styles[dimension])
        candidates = [(evaluate(recipe, development), recipe) for recipe in recipes()]
        candidates.sort(key=lambda pair: (-pair[0]["macro_f1"],
                                          pair[0]["mean_absolute_count_error"],
                                          abs(pair[1]["threshold"] - 1),
                                          pair[1]["sigma"], pair[1]["distance"]))
        selected = candidates[0][1]
        output["dimensions"][dimension] = {
            "selected_recipe": selected, "development": candidates[0][0],
            "holdout": evaluate(selected, holdout),
            "baseline_recipe": base, "baseline_holdout": evaluate(base, holdout),
            "stress_holdout": evaluate(selected, scenes(dimension, (HOLDOUT_SEED,),
                                                        styles[dimension], CASES[len(CORE_CASES):])),
        }
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-3d", type=Path)
    args = parser.parse_args()
    result = tune(args.reference, args.reference_3d)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    for dimension, scores in result["dimensions"].items():
        print(dimension, "selected", scores["selected_recipe"],
              "holdout F1", round(scores["holdout"]["macro_f1"], 3),
              "baseline", round(scores["baseline_holdout"]["macro_f1"], 3))
