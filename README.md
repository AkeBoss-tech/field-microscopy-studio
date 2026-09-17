---
title: Field Microscopy Studio
emoji: 🔬
colorFrom: green
colorTo: gray
sdk: static
app_file: demo/index.html
pinned: false
---
# FIELD · microscopy studio

A canvas-first microscopy demo for exploring Z stacks, comparing classical processing methods and saving annotations. No account is required. The free static demo processes scans in a Python/WebAssembly browser worker. **Your imported scans, recipes, results and annotations stay in this browser. They are not uploaded to a processing server or shared with other visitors.**

## Try it

Choose a real starter scan or upload a TIFF/CZI (100 MB in the cloud demo). Explore projections, acquired slices, and a rotatable sampled fluorescence preview. Process with Otsu, watershed, Sato, or preprocessing; name and reuse recipes. Method descriptions and working-size checks appear before running. Sato offers per-slice XY filtering (default for new UI runs) or legacy 3D grid filtering; the latter assumes equal voxel-axis spacing. Its connected components may span Z and are not individual neurons. New Sato runs include a downloadable calibrated ridge-response TIFF, separately from the preprocessed intensity image and thresholded labels. Annotate with count points, polygon/freehand outlines, and open neurite traces. Choose **Neurite (L)**, then **Click points** (Enter to finish) or **Freehand line** (drag and release). Live and saved lengths distinguish 2D slice/projected measurements from 3D traces; Backspace removes the last draft point. Planar traces export as ImageJ polylines, with lengths in CSV. Tracing is manual, not automatic signal following. In 3D, points and traces snap to sampled source voxels; rotate to verify depth before accepting them.

The starter scans are the user-authorized real iMOP neuron TIFF (14 Z, 2 channels, 1024²) and Set1 Control Mid-1 hair-cell CZI (40 Z, 4 channels, 1024²). They were losslessly repackaged as compressed OME-TIFF; pixel equality was checked after rereading both exports. All channels and acquired planes are retained, with original calibration and source hashes in `starter/*.json`. Only the selected volume is downloaded. Hair-cell channels remain numbered because biological channel labels require confirmation. These images and candidate outputs do not establish biological accuracy. `generate_starters.py` is retained for synthetic test fixtures, not the public starter list. Model outputs are candidate regions, not identified cells. Sato components do not establish neuron ownership. 3D is a sampled point preview, not surface segmentation or ray-cast rendering.

## Free browser demo

Hugging Face rejected a free Docker Space on this account with HTTP 402: Docker/Gradio CPU hosting requires PRO. Static hosting is free. This demo therefore uses Pyodide 0.28.3 with real NumPy/SciPy/scikit-image processing in a worker; first startup downloads the scientific runtime.

Browser memory limits uploads to 100 MB and 200 million scalar samples; individual processing jobs are capped at 8 million samples (choose a lower working XY resolution or a slice for larger volumes). TIFF and supported CZI stacks are normalized to Z/C/Y/X. Some proprietary compressed CZI codecs are unavailable in WebAssembly; export those scans as uncompressed OME-TIFF. Time-series and arbitrary scan modalities are not supported. Only the first TIFF series is imported, disclosed in the preview.

## Save behavior

Drafts autosave in the browser. Finished annotations save to immutable revisions in IndexedDB, with conflict detection. One active tab per workspace prevents stale tabs overwriting each other. Browser site-data clearing/eviction can remove this data: use **Back up workspace** to keep an independent ZIP of all imported scans, runs, recipes and annotations. Restore that ZIP in an empty workspace. Storage is specific to this origin, browser and device; it is not shared lab storage. Recipe, imported scan and completed processing artifacts are also saved. 2D annotations export to ImageJ RoiSet ZIP; all coordinates and provenance are in JSON; measurements are CSV. Volumetric points/traces are JSON/CSV only. Planar outlines are not complete volumetric cell masks.

For a future Docker/server deployment (not the free static demo), configure `HF_STATE_REPO` to a **private dataset repository**, and `HF_TOKEN` as a write-capable Space secret. Each successful save mirrors artifacts to that repository; startup restores them. The app refuses to boot in a Space without a persistence repository. A failed mirror is reported as a failed save, never a durable success. The repository is private but the running app intentionally shares its datasets and results. Do not place credentials in source or uploaded data.

The static demo computes on the visitor’s device. The optional server uses a single process/instance and a four-run waiting limit. It is not a production platform, a private clinical tool, or a GPU learned-model service. Free-tier disk/storage/API quotas still apply. Export important work as well.

## Local run

Python 3.11:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
STUDIO_ROOT="$PWD" STUDIO_STORE="$PWD/store" .venv/bin/python app/server.py --port 8777
```

## Hosting

For the free Space, run `python build_static.py` and publish the `demo/` files with `sdk: static` and `app_file: index.html`. To run a server instead, build the Dockerfile on an existing lab host or a paid Docker Space. Supply `STUDIO_HOSTS` with the exact Space hostname if the platform does not set `SPACE_HOST`. No wildcard host acceptance is used. `HF_STATE_REPO` and `HF_TOKEN` are runtime configuration, never committed. The same image can run on a lab host with persistent local storage. Changes to the lab's RStudio service are not required.

Controls: drag to pan (orbit in 3D), wheel/pinch to zoom, Shift+wheel for Z, Space+drag to navigate while drawing, P point, O outline, B freehand, L trace, S select/edit vertices, Enter finish, Escape discard unfinished drawing, Cmd/Ctrl+Z undo, Shift+Cmd/Ctrl+Z redo.

## Verification

Run `.venv/bin/python -m unittest discover -s tests`. Tests cover real classical processing, 2D ImageJ export, 3D trace lengths, invalid depth rejection, and mirror-save rollback. UI verification is separate.

### Annotation workspace

Choose **2D + 3D**, **2D only**, or **3D only** above the canvas. Labels stay at the top of the sidebar, the mark list scrolls independently, and Save stays visible. Search marks by label; use Show to select a mark and Rename to change its label. Neurite controls appear when tracing is active. Unfinished drawings have explicit Finish/Discard controls and block tool/view switching; Undo removes a draft vertex. Export, import, and annotator settings are grouped below Save.

### Channel colors

The **Channels** menu offers selected-channel color, grayscale, or an additive combined-channel view in 2D and sampled 3D. Each channel has an editable color and composite visibility toggle, saved per dataset in this browser. The active channel always remains visible and is the only channel used for processing, annotation, and 3D picking. iMOP defaults to green/blue; unnamed channels use display defaults, not inferred stain identities or recovered acquisition lookup tables. Coloring does not change source pixel values or exported scientific data.

Annotate opens in a focused 2D Point workspace. Use **Choose a tool / How to annotate** for count, neurite, and outline instructions. Shared accessible dialogs protect unfinished drawings during tool/view/tab/channel/Z changes, confirm deletion, and confirm reloading saved annotations. Escape closes dialogs without triggering canvas shortcuts.
