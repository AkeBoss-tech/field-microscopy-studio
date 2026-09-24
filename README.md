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

Bring your own model output through **Import masks** (full-stack instance TIFF), review its calibrated 3D boxes, and tag 3D neurite traces to candidate cells across channels. The [external algorithm and 3D workflow](docs/external-algorithms-and-3d.md) specifies the file contract and scientific limits. The [scaled two-modality benchmark](docs/scaled-modalities.md) records native/2×/4× synthetic checks against both starter scan intensity styles.

## Free browser demo

Hugging Face rejected a free Docker Space on this account with HTTP 402: Docker/Gradio CPU hosting requires PRO. Static hosting is free. This demo therefore uses Pyodide 0.28.3 with real NumPy/SciPy/scikit-image processing in a worker; first startup downloads the scientific runtime.

Browser memory limits uploads to 100 MB and 200 million scalar samples; individual processing jobs are capped at 8 million samples (choose a lower working XY resolution or a slice for larger volumes). TIFF and supported CZI stacks are normalized to Z/C/Y/X. Some proprietary compressed CZI codecs are unavailable in WebAssembly; export those scans as uncompressed OME-TIFF. Time-series and arbitrary scan modalities are not supported. Only the first TIFF series is imported, disclosed in the preview.

## Inspect a volume result

Select a completed full-volume run, then **Review volume**. Raw XY, result XY, XZ and YZ share one native-voxel crosshair. Click any plane, use its arrow keys, or type X/Y/Z coordinates to inspect a candidate. The inspector shows its processing-grid voxel count, calibrated volume, native bounds and processed-volume boundary contacts. These are candidate measurements, not biological validation or accepted counts.

The **Image layer** selector separates raw source, processed intensity and Sato ridge response. Label style and opacity are independent. Preprocessing results open their processed intensity automatically and export the image rather than empty labels. Switching channels clears incompatible selected runs. The context line identifies the displayed run; the Process form is explicitly a draft for the next run.

Review uses single-channel grayscale and acquired planes. It starts with physical proportions; optional Z expansion is labeled as display-only. Zoom centers on the crosshair. Auto contrast windows each intensity layer separately; choose **Use raw window for both** for a fixed-window comparison. Display interpolation never changes exported pixels or measurements. Projection, single-plane and historical geometry results remain in Explore because they do not provide a registered 3-D label volume. Manual annotation tools remain in Annotate; Review does not edit labels or accept candidates.

The staged improvement roadmap and acceptance criteria are in [docs/interface-roadmap.md](docs/interface-roadmap.md).

## Build and compare experiments

Use **Start a task** to choose cell bodies, nuclei, neurites, or intensity preparation. Process keeps channel, crop preview, and full run visible; **Settings** opens the detailed recipe in a dialog. The summary chip shows the active algorithm, scope, and XY resolution. Field tips explain less common controls. Blue, mint, violet, and amber accents distinguish source, preparation, processing, and candidates without relying on color alone. Review's queue filters also open in a dialog. Secondary source/grid comparisons live under Display; **A / B Compare runs** opens an explicit same-channel comparison.

Use **Choose preview region** to draw an XY rectangle or enter native bounds and a Z range. **Preview this region** computes an unsaved acquired-volume crop at the selected working resolution. Its source, processed/ridge and outline panels share a preview-Z slider. Edits mark the displayed snapshot as stale until refreshed. Context margins are in native XY pixels. Limits are 512 × 512 native pixels, 64 planes and up to 2 million working voxels including context (or the configured lower limit). Projection and slice recipes can still run, but do not offer this volume preview. Thresholds, normalization and connectivity depend on the crop/context; a preview is not a promise of identical full-volume labels. Previews and A/B selections are session-only; saved runs and recipes retain the existing persistence behavior.

Calibrated sources offer smoothing/background widths and watershed seed separation in µm, plus foreground/final-object thresholds in µm³ for volumes or µm² for 2-D scopes. XY Gaussian widths are converted independently using X/Y spacing. Physical watershed seed suppression uses calibrated Euclidean distance across the active dimensions. The final-object filter runs **after** segmentation, independently of the pre-split foreground filter. Saved runs include the requested recipe and derived grid parameters. Existing recipes without a units field replay with legacy grid semantics. Sato ridge scales remain 1 and 2 working pixels and are explicitly disclosed.

A/B comparisons use two current full-volume runs from the active image/channel, the same acquired Z, a selected intensity layer, shared or independent windows, candidate outlines and a recorded-parameter diff. Selecting a completed result from Process opens Review volume (or Explore for 2-D results). No object correction or biological acceptance is implied.

For repeatable method checks, [generate a synthetic counting dataset](docs/synthetic-benchmark.md) with exact 2D/3D body truth and neurite ownership. The generator can set image intensity ranges from the supplied TUBB3 and iMOP neuron scans, then score the classical methods. Synthetic scores do not establish biological accuracy.

[Download eleven procedural scenes and exact truth](examples/synthetic-v3/README.md) to reproduce the import, preview, run and review workflow. The five added stress controls expose false positives on empty fields. The original [v2 examples](examples/synthetic-v2/README.md) remain available.

Review now offers previewed Add, Delete, Split and Merge corrections in a separate, versioned label layer. Original algorithm labels and source pixels remain immutable. Explicit count rules record target, channel meaning, and edge policy; a reviewed candidate count appears only after every included object has a decision. Export pins label, decision, and count-rule revisions and includes corrected TIFF, candidate CSV, and count JSON. The split is a straight plane and Add is an ellipsoid, so each correction requires inspection in acquired XY/XZ/YZ views. These reviewer assessments are not independent biological ground truth. Follow the [real-image validation protocol](docs/real-validation-protocol.md) before using counts as a scientific result.

[Visually reviewed point examples for both starter images](examples/visual-point-examples/README.md) include annotated PNGs, native-coordinate JSON and ImageJ ROI ZIPs. Their eight points confidently locate distinct bright structures on specified planes; they are not complete biological cell counts or validated neuron identities.

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
## Candidate review and measurement

Open a registered full-volume segmentation run in **Review volume**, then choose **Candidates ↓**. The table lists actual label IDs, processing-grid voxel counts, calibrated volumes and volume-edge flags. Sort by size or ID, filter by decision/edge policy, and select a candidate to synchronize the acquired XY/XZ/YZ views at a real labeled voxel. The inspector's **Review candidate** dialog saves an Unreviewed, Accepted, Rejected or Needs review decision with a note.

Decisions are separate from immutable labels and manual annotations. Each save creates a review revision under the run; conflicting native-server saves are rejected with a reload option, and failed shared persistence rolls back the latest pointer. The browser-only app retains its existing single-workspace-tab lock and saves review files in browser storage. Use **Back up workspace** for a portable copy. This is a local review workflow, not authenticated reviewer attribution or biological validation.

**Export selection** previews the complete filtered set across all pages, pins its review revision, and downloads a CSV with run/source hash, channel, object ID, decision/note, grid count, calibrated volume, native bounds and explicit boundary policy. It rejects a download if decisions changed after the preview. Uncalibrated volumes stay blank. The original run's Objects CSV remains a frozen algorithm output; use the new export for current review decisions. Split/merge corrections, shape/intensity distributions and revised label measurements remain future work.
