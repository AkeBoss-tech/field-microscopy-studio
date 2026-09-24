# Synthetic counting benchmark

Run `tools/synthetic_benchmark.py` from the repository root. The generator creates six small TIFF scenes with exact soma/body instance masks, center coordinates, and, for the neuron scenes, separate owner masks and branch graphs. It includes isolated, touching, dim, crossing, 2D, and 3D cases. Seeds make each scene reproducible. The reference scans set **intensity ranges only**; their cells and labels are not copied into the generated scenes.

```sh
.venv/bin/python tools/synthetic_benchmark.py \
  --out ../outputs/field-synthetic-v2 \
  --reference '/Users/akashdubey/Downloads/TF1_011526_Tubb3_40X_C4_F2_MMStack_Default.ome.tif' \
  --reference-3d starter/imop.ome.tif \
  --evaluate
```

Each case contains a descriptively named `<case>.ome.tif` for import into FIELD, `body_instances.tif` with IDs 1 through N, and `truth.json` with exact centers and source hash. Neuron cases also contain `neurite_owners.tif`, whose first axis is owner ID. The generator checks every instance ID and center, body separation or contact as promised by the case name, 2D projected crossings and distinct 3D crossing depths, and graph samples against owner masks. `manifest.json` records source files and seeds. `scores.csv` runs the app's shared preprocessing, Otsu, watershed, and Sato code at native XY resolution, including both XY and legacy 3D-grid Sato on volumes. Body candidate masks are matched one-to-one to truth at IoU ≥ 0.3, with signed count error, precision, recall, and F1. Preprocessing has no count score. Sato scores are diagnostic overlap only: its connected networks are **not** neuron counts.

To tune a body-count recipe without reusing the same generated fields for selection and reporting:

```sh
.venv/bin/python tools/tune_synthetic.py \
  --out ../outputs/field-synthetic-v2/tuning.json \
  --reference '/Users/akashdubey/Downloads/TF1_011526_Tubb3_40X_C4_F2_MMStack_Default.ome.tif' \
  --reference-3d starter/imop.ome.tif
```

The tuner searches Otsu/watershed smoothing, threshold, and watershed seed spacing on development seeds 17 and 31. It freezes one 2D and one 3D recipe, then reports instance F1 and signed count errors on seed 53. Never select parameters on the holdout result. Tune the real workflow next by defining the biological count target and edge rule, obtaining expert marks on independent fields, previewing representative sparse/touching/dim areas, checking A/B overlays at the same channel, Z, and working resolution, and selecting parameters on the development fields. Lock the recipe before evaluating an entire held-out specimen. Review algorithm candidate IDs separately from accepted biological counts.

To test the **native app workflow** against all six generated files, start a local server with an isolated `STUDIO_STORE`, then run:

```sh
.venv/bin/python tools/verify_synthetic_workflow.py \
  --suite ../outputs/field-synthetic-v2 \
  --tuning ../outputs/field-synthetic-v2/tuning.json \
  --out ../outputs/field-synthetic-v2/workflow.json
```

This checks import axes/shape, unsaved crop preview, completed full-volume run, exported label dimensions, and raw/XY/XZ/YZ review panels for every scene. The six stages can all pass while some candidate counts are wrong. On the checked seed-17 suite, 2D cases each matched exact body counts, while the 3D touching scene produced 9 candidates for 8 bodies with the tuned recipe. On the independent seed-53 suite the 3D crossing scene produced 6 candidates for 5 bodies; macro F1 was 0.955 versus 0.798 with the earlier default spacing. These scores describe this small phantom family only.

To check the browser flow, import one `<case>.ome.tif`, choose a count task, preview a crop, run the full volume, and inspect its XY/XZ/YZ planes in Review. Do not import `body_instances.tif` as if it were the raw image. The generated scenes are uncalibrated in the app unless you deliberately supply the *simulated* spacing (1 µm XY, 2 µm Z); that spacing is illustrative and was not measured from the reference scans.

The current renderer uses ellipsoids, graph lines, Gaussian blur, field shading, and approximate shot/read noise. It does not yet measure a point-spread function, bleaching, bleedthrough, or z-dependent attenuation from the microscope. It also lacks edge-truncated and zero-cell controls. Before using synthetic scores for method selection, add those stress cases and validate the renderer's appearance against held-out real images. Then freeze parameters on synthetic development cases and score on expert-reviewed real fields, grouping all crops/augmentations from one source specimen in the same split. The supplied TUBB3 frame is one 2D specimen; its transformed copies are not independent test images. Existing compact IDs require biological meaning to be confirmed before treating them as real soma truth.

The benchmark checks processing behavior and failure modes. It does not certify counts, cell identities, or neurite ownership in real tissue.
