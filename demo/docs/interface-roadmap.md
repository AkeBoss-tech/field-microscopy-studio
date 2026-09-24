# FIELD interface improvement roadmap

Prepared 2026-09-19 from the deployed-app audit and real iMOP/hair-cell processing. Historical milestone notes below describe the state on their dates. The latest implementation status is recorded at the end of this document.

The target workflow is **Inspect → Prepare → Find candidates → Review/correct → Measure/export**. Each step should expose its input, output and evidence in the same image workspace.

| Area | Change | Acceptance criterion / status |
|---|---|---|
| Layers and result selection | Explicit raw, processed intensity and ridge response; independent labels; useful preprocessing exports. | Implemented. Preprocessing opens processed intensity and has no label actions. |
| Volume review | Linked raw XY/result XY/XZ/YZ; calibrated aspect, crosshair, zoom and object inspector. | Implemented for registered full-volume runs. Physical depth is the default; expansion is explicit. |
| Result provenance | Visible image/channel/run/scope/resolution; draft processing form distinguished from selected output. | Implemented. Incompatible channel overlays are cleared and rejected by the API. |
| Import and startup | Axes/series/calibration preview, channel thumbnails, progress/recovery and storage status. | Next: users can confirm source dimensions and units before processing. |
| Preprocessing | Ordered stages with bypass, crop preview, histogram/difference and visible parent lineage. | Next: compare original and processed pixels in a shared window before committing a full run. |
| ROI and algorithm controls | XY ROI plus Z range; native-resolution preview with context margin; physical-unit parameters and separate pre/post-watershed size policies. | Next: preserve crop origin and physical intent across resolution changes. A preview must never look like a full-field result. |
| Experiments and comparison | User-pinned A/B runs, parameter differences, shared ROI and contrast, size/edge/foreground diagnostics. | Next: isolate one hypothesis without silently comparing different channels or scopes. |
| Annotation and correction | Keep manual points/outlines/traces; add a separate object review queue and previewed split/merge/refinement. | Later: corrections produce immutable revised label volumes and update measurements. A drawn 2-D outline is not a 3-D mask. |
| Measurements | Linked sortable object table, distributions, review states, inclusion/edge policy and export preview. | Later: accepted measurements can be reproduced from specific source/run/revision/object IDs. |
| Neurites and agents | Raw/ridge/path views; soma/branch graph; alternative connections and explicit uncertainty at crossings. | Later: accepted traces retain native coordinates and provenance; ambiguous crossings allow abstention. |
| Compute and storage | Incremental local-toolkit imports, explicit browser/local/shared save status, lab worker for larger jobs and models. | Later: no destructive workspace reset to add agent results; compute availability and persistence are accurately represented. |

## Implementation boundary

The first milestone adds `app/review.py` and `app/web/review.js` with a shared native/Pyodide API, plus small integrations into the existing UI. It intentionally preserves current processing algorithms. Full-volume label inspection does not imply that the segmentation is correct: the audit showed joined neurite networks, watershed fragmentation and boundary-truncated candidates. Existing grid-valued parameters still depend on processing resolution.

The next engineering increment should establish a crop/scale/channel artifact contract before adding ROI previews or toolkit corrections. Tests must cover crop origin, context halo, native mapping, anisotropic spacing and exact exported revised labels. Then reduce the existing render-wrapper chain into explicit modules as those boundaries are touched; a framework rewrite is not required for this milestone.

## Verification of the first milestone

- Fifteen Python tests pass, including six focused volume-review tests: exact plane extraction, factors 1/2/4, native bounds, calibrated/uncalibrated metrics, boundary faces, channel/scope/layer guards and separate ridge intensity.
- Syntax checks pass for the changed JavaScript; static bundle rebuilt and `git diff --check` passes.
- Native app visually checked on iMOP Sato and hair watershed. Hair candidate 32 at native (513, 513, 30) reports 613 processing-grid voxels and 238.63 µm³ at XY reduction 4.
- Actual browser-only Pyodide build ran Otsu, watershed, Sato and preprocessing on the real iMOP stack, all 14 Z planes at XY reduction 2. Runs survived reload, and both ridge and intensity-only review rendered successfully.
- Annotation transition, draft protection, finish, undo/redo, save and reload exercised in an isolated QA store.
- Claude provided two read-only reviews. Confirmed channel and async risks were addressed. Global layer controls are deliberate; bounded caches are deliberate. Large imported-volume interaction latency remains to be profiled.

Evidence and screenshots are saved outside the repository under `outputs/studio-build-20260919/`. The earlier audit, 17 native runs, seven hosted operations, and full per-area recommendations are under `outputs/studio-ux-audit-20260918/` in the enclosing workspace. Those folders contain local evidence, not a hosted release.

## Experiment and design increment — 2026-09-19

Implemented locally after the first milestone: structured processing panel with fixed action area; semantic accent colors, numbered navigation and focused task/region/comparison dialogs; unsaved XY/Z crop previews with an explicit snapshot/stale state; calibrated XY preprocessing and Euclidean watershed seed suppression; separate final-object filtering; recorded derived parameters; parent/channel compatibility; and explicit A/B full-volume comparison. Saved recipe parents are preserved when compatible and otherwise visibly reset to source.

This updates the earlier “Next” status for these bounded pieces. Still outstanding: full ordered/bypassable stage stacks, difference/histogram previews, persistent pinned comparisons, cropped full-run artifacts, algorithm-scale controls for Sato, segmentation correction and linked object tables. The preview supports acquired volume scope only; comparison currently uses full-field acquired XY planes.

Verification: 23 Python tests pass. Actual native iMOP Sato crop and hair watershed crop previews were inspected. The real browser-only Pyodide build completed a physical watershed preview and full run, retained that run after reload, and opened it in linked volume review. Claude performed a read-only review; scope/unit ambiguity and limit wording were corrected. Desktop and narrow layouts were inspected; dialogs retain native keyboard focus/Escape behavior. Evidence is in the enclosing workspace at `outputs/studio-experiments-20260919/`. No deployment or commit is included.

## Candidate review and measurement increment — 2026-09-19

Implemented: paginated candidate table linked to actual labeled voxels in acquired planes; size sorting, exact-ID lookup, decision and volume-edge filters; calibrated volume/native bounds; color-coded decision badges and a focused review dialog; separate immutable decision snapshots with optimistic concurrency; filtered export preview and revision-pinned CSV. A save preserves the active table page, and shrinking selections clamp to a valid page. Existing algorithm label files and original run CSVs are unchanged.

31 tests pass, including eight candidate-measurement tests covering sparse IDs, physical geometry, filters, pagination, actual-voxel location, concurrent saves, persistence rollback, immutable labels, cross-run isolation and exact export selection/provenance. Native and browser-only workflows were exercised on real saved runs. Claude provided design and code reviews; pagination findings were fixed and verified in the browser. Evidence is in `outputs/studio-measurements-20260919/` in the enclosing workspace.

Next milestone: previewed segmentation corrections with immutable label revisions, updated object identities and recalculated measurements. This requires explicit split/merge semantics, provenance from original labels to revised objects, undo/replay, and expert-reviewed fixtures. Authenticated reviewer attribution, shape/intensity distributions, advanced exports and a shared lab compute worker are still outstanding.

## Correction and count workflow — 2026-09-23

Implemented: previewed straight-plane split, merge, delete, small ellipsoid add, and undo to the preceding label state. Every saved correction writes an immutable TIFF and metadata revision while preserving the original run labels and source pixels. Review views, object table, location, edge flags, and calibrated volumes use the active corrected revision. Decisions on changed objects become unreviewed until assessed again. The count-rules popup records target, channel meaning, and edge inclusion; only a fully decided Otsu/watershed run produces a reviewed candidate count. CSV, count JSON, and corrected TIFF exports pin the label, decision, and protocol revisions.

The browser correction dialog was exercised on the synthetic touching 3D scene: a preview showed XY/XZ/YZ and split 448 voxels into 225 and 223, increasing candidates from 9 to 10. The revision and count rules survived a native-server page reload. The original algorithm result stayed at 9. This is geometry editing, not expert validation. A straight split plane and ellipsoid add cannot express arbitrary biological boundaries; a freehand/brush refinement remains future work. Shared reviewer attribution and multiuser consistency remain unavailable in the browser-only Space.

The v3 synthetic suite adds five stress controls. All eleven imported, previewed, ran, exported labels, and rendered orthogonal review on an isolated native server. The frozen watershed recipe falsely detected 34 and 134 objects in empty 2D and 3D scenes. This is a visible method failure, not a dataset integrity failure. `tools/score_expert_benchmark.py` now validates provenance and specimen-level split separation for future expert-adjudicated real masks. No expert-adjudicated whole-region masks for the two real starters are available, so real count precision and recall remain unknown.
