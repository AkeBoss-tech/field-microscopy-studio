"""Copy a validated synthetic suite into public, portable example paths."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.synthetic_benchmark import validate_scene


def package(suite: Path, out: Path) -> None:
    manifest = json.loads((suite / "manifest.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    for record in manifest["cases"]:
        name = record["case"]
        source = suite / name
        target = out / name
        target.mkdir(exist_ok=True)
        truth = json.loads((source / "truth.json").read_text())
        labels = tifffile.imread(source / "body_instances.tif")
        image = tifffile.imread(source / f"{name}.ome.tif")
        if image.ndim == 2:
            image, labels = image[None], labels[None]
        owners = (tifffile.imread(source / "neurite_owners.tif").astype(bool)
                  if truth["neurite_owners"] else np.zeros((truth["body_count"], *image.shape), bool))
        if owners.ndim == 3:
            owners = owners[:, None]
        validate_scene(labels, owners, truth)
        if image.shape != labels.shape:
            raise ValueError(f"Image and truth shapes differ for {name}")
        for filename in (f"{name}.ome.tif", "body_instances.tif", "truth.json"):
            shutil.copy2(source / filename, target / filename)
        if truth["neurite_owners"]:
            shutil.copy2(source / "neurite_owners.tif", target / "neurite_owners.tif")
        record["path"] = name
    manifest["reference_2d"] = "TUBB3 source intensity statistics; source image not included"
    manifest["reference_3d"] = "public iMOP starter intensity statistics"
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for filename in ("scores.csv", "tuning.json"):
        if (suite / filename).exists():
            shutil.copy2(suite / filename, out / filename)
    links = "\n".join(
        f"| {record['case']} | {record['dimension']} | {record['body_count']} | "
        f"[Image]({record['case']}/{record['case']}.ome.tif) | "
        f"[Truth]({record['case']}/truth.json) | "
        f"[Masks]({record['case']}/body_instances.tif) |"
        for record in manifest["cases"])
    (out / "README.md").write_text("""# Procedural 2D and 3D counting scenes

Download an image TIFF and import it into FIELD with **Add image**. Each scene's
`truth.json` and `body_instances.tif` contain exact procedural body truth; neuron
scenes also include per-owner neurite masks. Import the **image** TIFF as source,
then choose a counting task, preview, run, and inspect candidates in Review.
The simulated spacing is 1 µm XY and 2 µm Z; it is not a measured microscope
calibration. `manifest.json` lists all six scenes, `scores.csv` summarizes the
four runnable methods, and `tuning.json` records development and held-out seeds.

| Scene | Dimensions | Bodies | Import TIFF | Centers and graph | Body masks |
|---|---|---:|---|---|---|
""" + links + """

The source images are not copied into these scenes. All six files passed native
import, preview, full-volume run, label export, and linked XY/XZ/YZ review.
The algorithms are **not** 100% accurate: even the tuned seed-17 touching 3D
case gives 9 candidates for 8 true bodies. These examples check code paths and
failure modes, not biological cell counts or neuron ownership in real scans.
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    package(args.suite, args.out)
    print(f"Packaged {len(json.loads((args.out / 'manifest.json').read_text())['cases'])} scenes")
