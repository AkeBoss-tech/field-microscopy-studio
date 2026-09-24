"""Generate small, reproducible microscopy phantoms with exact instance truth.

Usage: python tools/synthetic_benchmark.py --out /tmp/field-synthetic --evaluate
Optional --reference and --reference-3d TIFFs calibrate 2D and 3D intensity
ranges without copying their cells.
The output is a method check, not a biological accuracy claim.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment


CASES = (
    ("cells_isolated_2d", (1, 128, 128), 9, "isolated", False),
    ("cells_touching_2d", (1, 128, 128), 10, "touching", False),
    ("cells_dim_2d", (1, 128, 128), 8, "dim", False),
    ("neurons_crossing_2d", (1, 128, 128), 5, "crossing", True),
    ("cells_touching_3d", (12, 128, 128), 8, "touching", False),
    ("neurons_crossing_3d", (12, 128, 128), 5, "crossing", True),
)


def reference_style(path: Path | None) -> dict:
    if path is None:
        return {"background": 1200.0, "signal": 10000.0, "read_noise": 120.0, "source_sha256": None}
    with tifffile.TiffFile(path) as tf:
        array = tf.asarray(out="memmap")
        axes = tf.series[0].axes
        if "C" in axes:
            array = np.take(array, 0, axis=axes.index("C"))
        stride = max(1, int(np.ceil(array.size / 500_000)))
        sample = np.asarray(array).reshape(-1)[::stride].astype(np.float32)
    sample = sample[np.isfinite(sample)]
    if sample.size < 100:
        raise ValueError("Reference TIFF has too few finite pixels")
    low, high = np.percentile(sample, [20, 99.5])
    if high <= low:
        high = low + 1000
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    return {"background": float(low), "signal": float(high - low),
            "read_noise": float(max(10, (high - low) * .015)), "source_sha256": digest}


def _paint_line(mask: np.ndarray, start: np.ndarray, end: np.ndarray) -> list[list[int]]:
    distance = int(np.ceil(np.max(np.abs(end - start)) * 2)) + 1
    coords = np.rint(np.linspace(start, end, distance)).astype(int)
    coords = np.clip(coords, 0, np.asarray(mask.shape) - 1)
    mask[tuple(coords.T)] = True
    return coords.tolist()


def make_scene(shape: tuple[int, int, int], count: int, challenge: str,
               neurons: bool, seed: int, style: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Return image, body labels, owner masks, and exact graph/center truth."""
    rng = np.random.default_rng(seed)
    nz, ny, nx = shape
    if min(ny, nx) < 128 or nz not in (1, 12) or count < 2:
        raise ValueError("Scene layout requires at least 128 × 128 and either 1 or 12 Z planes")
    labels = np.zeros(shape, np.uint16)
    owners = np.zeros((count, *shape), bool)
    centers: list[list[float]] = []
    radii: list[list[float]] = []
    graphs = []
    zz, yy, xx = np.ogrid[:nz, :ny, :nx]

    def body_mask(center, radius):
        cz, cy, cx = center
        rz, ry, rx = radius
        return (((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 +
                (((zz - cz) / rz) ** 2 if nz > 1 else 0)) <= 1

    occupied = np.zeros(shape, bool)
    pair_anchors = [(28, 26), (28, 78), (59, 26), (59, 78), (91, 26)]
    for i in range(count):
        ry, rx = rng.uniform(5, 9, 2)
        rz = rng.uniform(1.4, 2.5) if nz > 1 else 1.0
        radius = [float(rz), float(ry), float(rx)]
        if challenge == "touching":
            if i // 2 >= len(pair_anchors):
                raise ValueError("Too many touching pairs for this scene")
            ay, ax = pair_anchors[i // 2]
            cz = float(3 + (i // 2) % 3 * 3) if nz > 1 else 0.0
            cy = float(ay)
            cx = float(ax if i % 2 == 0 else ax + radii[-1][2] + rx - .5)
        elif challenge == "crossing" and i in (0, 1):
            cz = float((3, 8)[i]) if nz > 1 else 0.0
            cy, cx = ((64.0, 28.0), (28.0, 64.0))[i]
        else:
            for _ in range(500):
                cz = float(rng.integers(3, nz - 3)) if nz > 4 else 0.0
                cy = float(rng.integers(14, ny - 14))
                cx = float(rng.integers(14, nx - 14))
                candidate = body_mask([cz, cy, cx], radius)
                if not np.any(ndi.binary_dilation(candidate, iterations=3) & occupied):
                    break
            else:
                raise ValueError("Could not place separated bodies with this seed")
        center = [cz, cy, cx]
        centers.append(center)
        radii.append(radius)
        ellipsoid = body_mask(center, radius)
        # At touching pairs the labels share a boundary while each ID keeps its center.
        labels[ellipsoid & (labels == 0)] = i + 1
        occupied |= ellipsoid
        if neurons:
            skeleton = owners[i]
            root = np.asarray(center)
            branches = []
            for branch in range(2):
                if challenge == "crossing" and i in (0, 1) and branch == 0:
                    depth = cz
                    elbow = np.asarray([depth, 64.0, 64.0])
                    end = np.asarray([depth, 64.0, 104.0] if i == 0 else
                                     [depth, 104.0, 64.0])
                else:
                    direction = rng.normal(size=3)
                    if nz == 1:
                        direction[0] = 0
                    else:
                        direction[0] *= .12  # anisotropic acquisition
                    direction /= np.linalg.norm(direction)
                    elbow = np.clip(root + direction * rng.uniform(15, 25), [0, 3, 3],
                                    [nz - 1, ny - 4, nx - 4])
                    end = np.clip(elbow + direction * rng.uniform(12, 27) + rng.normal(0, 5, 3),
                                  [0, 3, 3], [nz - 1, ny - 4, nx - 4])
                branches.append({"root_zyx": root.tolist(), "elbow_zyx": elbow.tolist(),
                                 "end_zyx": end.tolist(),
                                 "samples_zyx": _paint_line(skeleton, root, elbow) +
                                                _paint_line(skeleton, elbow, end)})
            graphs.append({"body_id": i + 1, "branches": branches})
    # Render each owner independently; crossings retain separate graph identity.
    field = ndi.gaussian_filter((labels > 0).astype(np.float32), (0 if nz == 1 else .8, 1.2, 1.2))
    if neurons:
        neurites = np.any(owners, axis=0)
        field += .65 * ndi.gaussian_filter(neurites.astype(np.float32),
                                            (0 if nz == 1 else .6, .8, .8))
    field = np.clip(field, 0, 1.5)
    if challenge == "dim":
        field *= .45
    low = style["background"]
    signal = style["signal"]
    shading = ndi.gaussian_filter(rng.normal(size=shape).astype(np.float32),
                                 (0 if nz == 1 else 2, 22, 22))
    shading /= max(float(shading.std()), 1e-6)
    image = low + signal * field + shading * signal * .025
    image += rng.normal(0, style["read_noise"], shape)
    image += rng.normal(0, np.sqrt(np.maximum(image, 0)) * .25, shape)
    image = np.clip(image, 0, 65535).astype(np.uint16)
    truth = {"shape_zyx": list(shape), "body_count": count,
             "body_centers_zyx": [{"id": i + 1, "center": center, "radii_zyx": radii[i]}
                                   for i, center in enumerate(centers)],
             "neurite_graphs": graphs, "challenge": challenge,
             "notes": "Procedural truth; crossings in a 2D projection do not establish neuron ownership."}
    validate_scene(labels, owners, truth)
    return image, labels, owners, truth


def validate_scene(labels: np.ndarray, owners: np.ndarray, truth: dict) -> None:
    """Fail closed when a generated scene does not satisfy its named truth."""
    count = truth["body_count"]
    if labels.shape != tuple(truth["shape_zyx"]) or owners.shape != (count, *labels.shape):
        raise ValueError("Image truth dimensions disagree")
    if not np.array_equal(np.unique(labels), np.arange(count + 1)):
        raise ValueError("A body instance is missing or IDs are not contiguous")
    for item in truth["body_centers_zyx"]:
        center = tuple(np.rint(item["center"]).astype(int))
        if labels[center] != item["id"]:
            raise ValueError("A body center is outside its own instance")
    if truth["challenge"] in ("isolated", "dim"):
        for i in range(1, count + 1):
            if np.any(ndi.binary_dilation(labels == i, iterations=2) &
                      ((labels > 0) & (labels != i))):
                raise ValueError("An isolated body touches another body")
    if truth["challenge"] == "touching":
        for first in range(1, count + 1, 2):
            if not np.any(ndi.binary_dilation(labels == first) & (labels == first + 1)):
                raise ValueError("A promised touching pair does not touch")
    if truth["challenge"] == "crossing":
        xy = (64, 64)
        if not np.all(np.any(owners[:2, :, xy[0], xy[1]], axis=1)):
            raise ValueError("The two neurites do not cross in XY")
        if labels.shape[0] > 1 and np.any(owners[0, :, xy[0], xy[1]] &
                                          owners[1, :, xy[0], xy[1]]):
            raise ValueError("A projected 3D crossing merged at the same voxel")
        if labels.shape[0] == 1 and not np.any(owners[0] & owners[1]):
            raise ValueError("The 2D owner masks do not share their crossing pixel")
    for graph in truth["neurite_graphs"]:
        mask = owners[graph["body_id"] - 1]
        for branch in graph["branches"]:
            for point in branch["samples_zyx"]:
                if not mask[tuple(point)]:
                    raise ValueError("A graph sample is absent from its owner mask")


def score_instances(truth: np.ndarray, predicted: np.ndarray) -> dict:
    true_ids = np.unique(truth); true_ids = true_ids[true_ids > 0]
    pred_ids = np.unique(predicted); pred_ids = pred_ids[pred_ids > 0]
    overlap = np.zeros((len(true_ids), len(pred_ids)), np.float64)
    for i, tid in enumerate(true_ids):
        target = truth == tid
        for j, pid in enumerate(pred_ids):
            candidate = predicted == pid
            union = np.count_nonzero(target | candidate)
            overlap[i, j] = np.count_nonzero(target & candidate) / union if union else 0
    if overlap.size:
        # Maximize valid one-to-one matches first, then their summed IoU.
        # Raw-IoU assignment can choose one excellent pair over two pairs
        # that both pass the reporting threshold.
        valid = overlap >= .3
        reward = valid * (min(overlap.shape) + 1) + overlap
        rows, cols = linear_sum_assignment(-reward)
        matched = int(np.count_nonzero(overlap[rows, cols] >= .3))
    else:
        matched = 0
    precision = matched / len(pred_ids) if len(pred_ids) else 0.0
    recall = matched / len(true_ids) if len(true_ids) else 0.0
    return {"truth_count": len(true_ids), "candidate_count": len(pred_ids),
            "count_error": int(len(pred_ids) - len(true_ids)), "matched_iou_0_3": matched,
            "precision_iou_0_3": precision, "recall_iou_0_3": recall,
            "f1_iou_0_3": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def generate(out: Path, seed: int = 17, reference: Path | None = None,
             reference_3d: Path | None = None, evaluate: bool = False) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    styles = {"2D": reference_style(reference), "3D": reference_style(reference_3d or reference)}
    records = []
    for index, (name, shape, count, challenge, neurons) in enumerate(CASES):
        dimension = "3D" if shape[0] > 1 else "2D"
        style = styles[dimension]
        image, labels, owners, truth = make_scene(shape, count, challenge, neurons,
                                                   seed + index, style)
        directory = out / name
        directory.mkdir(exist_ok=True)
        image_name = name + ".ome.tif"
        axes = "ZYX" if shape[0] > 1 else "YX"
        tifffile.imwrite(directory / image_name, image if shape[0] > 1 else image[0],
                         metadata={"axes": axes})
        tifffile.imwrite(directory / "body_instances.tif", labels if shape[0] > 1 else labels[0],
                         metadata={"axes": axes})
        if neurons:
            tifffile.imwrite(directory / "neurite_owners.tif", owners.astype(np.uint8),
                             metadata={"axes": "CZYX"})
        truth.update({"seed": seed + index, "image": image_name,
                      "body_instances": "body_instances.tif",
                      "neurite_owners": "neurite_owners.tif" if neurons else None,
                      "style_reference_sha256": style["source_sha256"],
                      "simulated_spacing_xyz_um": [1.0, 1.0, 2.0],
                      "calibration_note": "Illustrative simulated spacing; not measured from the reference image."})
        (directory / "truth.json").write_text(json.dumps(truth, indent=2))
        records.append({"case": name, "dimension": "3D" if shape[0] > 1 else "2D",
                        "challenge": challenge, "body_count": count, "path": str(directory)})
    (out / "manifest.json").write_text(json.dumps({"generator": "synthetic_benchmark.py",
       "seed": seed, "reference_2d": str(reference) if reference else None,
       "reference_3d": str(reference_3d or reference) if reference_3d or reference else None,
       "style_reference_sha256": {key: value["source_sha256"] for key, value in styles.items()},
       "cases": records,
       "warning": "Synthetic performance is a regression check, not biological validation."}, indent=2))
    if evaluate:
        evaluate_suite(out)
    return records


def evaluate_suite(out: Path) -> list[dict]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.processing import process
    results = []
    for record in json.loads((out / "manifest.json").read_text())["cases"]:
        directory = Path(record["path"])
        image = tifffile.imread(directory / (record["case"] + ".ome.tif"))
        labels = tifffile.imread(directory / "body_instances.tif")
        if image.ndim == 2:
            image, labels = image[None], labels[None]
        metadata = {"spacing": [1.0, 1.0, 2.0], "calibrated": True}
        variants = [("preprocess", "slice"), ("otsu", "slice"),
                    ("watershed", "slice"), ("sato", "slice")]
        if image.shape[0] > 1:
            variants.append(("sato", "volume"))
        for method, mode in variants:
            params = {"method": method, "scope": "volume", "units": "grid",
                      "sigma": .5, "background": 0, "min_size": 15,
                      "min_final_size": 10, "distance": 5, "threshold": 1,
                      "sato_mode": mode}
            _, predicted, _, _, _ = process(image, params, metadata, 1)
            scores = score_instances(labels, predicted) if method != "preprocess" else {
                "truth_count": len(np.unique(labels)) - 1, "candidate_count": 0,
                "count_error": "", "matched_iou_0_3": "", "precision_iou_0_3": "",
                "recall_iou_0_3": "", "f1_iou_0_3": ""}
            results.append({"case": record["case"],
                            "algorithm": method + ("_3d_grid" if method == "sato" and mode == "volume" else "_xy" if method == "sato" else ""),
                            "interpretation": "intensity only; no count" if method == "preprocess" else "network components; not body counts" if method == "sato" else "body candidates",
                            **scores})
    with (out / "scores.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0]))
        writer.writeheader(); writer.writerows(results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-3d", type=Path)
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    cases = generate(args.out, args.seed, args.reference, args.reference_3d, args.evaluate)
    print(f"Wrote {len(cases)} scenes to {args.out}")
    if args.evaluate:
        print(f"Wrote algorithm scores to {args.out / 'scores.csv'}")
