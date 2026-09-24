# Synthetic counting benchmark

The [v3 example suite](../examples/synthetic-v3/README.md) contains **11 reproducible 2D/3D scenes** with exact body instance masks and centers. Neuron scenes also include owner-specific neurite masks and branch graphs. The first six exercise isolated, touching, dim, and crossing objects. Five stress controls add empty 2D/3D fields, edge-truncated 2D/3D bodies, and a depth-attenuated 3D field. The reference scans set intensity ranges only; no real cells or labels are copied.

```sh
.venv/bin/python tools/synthetic_benchmark.py \
  --out ../outputs/field-synthetic-v3 \
  --reference '/Users/akashdubey/Downloads/TF1_011526_Tubb3_40X_C4_F2_MMStack_Default.ome.tif' \
  --reference-3d starter/imop.ome.tif \
  --evaluate
.venv/bin/python tools/tune_synthetic.py \
  --out ../outputs/field-synthetic-v3/tuning.json \
  --reference '/Users/akashdubey/Downloads/TF1_011526_Tubb3_40X_C4_F2_MMStack_Default.ome.tif' \
  --reference-3d starter/imop.ome.tif
```

Each scene has an importable `<case>.ome.tif`, `body_instances.tif`, and `truth.json`. Neuron scenes add `neurite_owners.tif`. The generator validates IDs, centers, expected contact or separation, edge truncation, projected crossings, and owner graphs. `scores.csv` checks the shared preprocessing, Otsu, watershed, and Sato implementations. One-to-one body matches use IoU ≥ 0.3. Empty scenes report false-positive candidate count; a correctly empty scene scores F1 1 and any nonempty prediction scores F1 0. Sato component overlap is diagnostic only: connected networks are **not** neuron counts.

The tuner searches Otsu/watershed parameters on development seeds 17 and 31 of the six core scenes, freezes one 2D and one 3D recipe, and scores seed 53. The five stress controls are scored separately on the frozen recipe, so they cannot influence its selection. Never tune on the holdout scores.

To test import, crop preview, full run, label export, and linked XY/XZ/YZ review on a native server with an isolated `STUDIO_STORE`:

```sh
.venv/bin/python tools/verify_synthetic_workflow.py \
  --suite ../outputs/field-synthetic-v3 \
  --tuning ../outputs/field-synthetic-v3/tuning.json \
  --out ../outputs/field-synthetic-v3/workflow.json
```

**Observed on seed 17:** all 11/11 paths worked, but the frozen watershed recipe found 34 false objects in the empty 2D scene and 134 in the empty 3D scene. It also found 9 candidates for 8 touching 3D bodies and 7 for 6 attenuated 3D bodies. The seed-53 empty controls also failed, with 45 and 130 false objects. The original core 3D holdout macro F1 was 0.955, versus 0.798 with the earlier default seed spacing. These results expose both software correctness and a serious algorithm limitation; they do not establish biological count accuracy.

To check the browser flow, import an image TIFF, choose a count task, preview a crop, run the full volume, and inspect Review. Do not import the truth TIFF as a source image. The simulated spacing is 1 µm XY and 2 µm Z; it was not measured from a microscope.

The renderer uses ellipsoids, graph lines, Gaussian blur, field shading, approximate shot/read noise, and simple linear Z attenuation in one stress scene. It does **not** measure the microscope point-spread function, bleaching, bleedthrough, or attenuation. Before selecting a real count recipe, compare synthetic appearance with real fields and follow the [expert validation protocol](real-validation-protocol.md). All crops and augmentations from one biological specimen must stay in one split. The supplied TUBB3 frame is one 2D specimen, not an independent dataset of transformed copies.
