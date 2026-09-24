# Real-image count validation

The two public starter images currently have **visual signal-point examples**, not exhaustive expert soma, cell, or neuron labels. Do not use those four points per image as accuracy ground truth. The synthetic masks test software behavior but cannot establish biological accuracy.

## Collect a usable reference

1. Confirm the acquisition channel map and define one target (for example, cell bodies or nuclei). Record whether objects touching each acquired volume edge are included. Do not count Sato connected networks as neurons.
2. Ask at least one domain expert to label complete 3D instances in several sparse, touching, dim, and boundary regions from each source. Record specimen identity and actual source SHA-256. An independent second reviewer should adjudicate ambiguous cases when available. Keep the raw source and algorithm output out of the expert's initial view when practical.
3. Keep every region from one specimen in the same **development** or **holdout** split. Freeze the recipe and XY reduction using development specimens only; do not inspect holdout scores while tuning.
4. In FIELD, set Count rules, correct each candidate through the preview, and accept or reject every included object. Export **Count JSON** and **Corrected TIFF** from the same export preview, and save the run's `run.json` through Recipe & provenance. Copy the expert instance TIFF into the same processing ZYX grid. Each truth ID must represent one body throughout Z; zero is background.
5. Score with `tools/score_expert_benchmark.py`. Inspect count error, one-to-one instance F1, missed/extra objects, and edge-specific failures before applying a recipe to another specimen.

Example manifest (paths relative to this JSON file):

```json
{
  "version": 1,
  "fields": [{
    "id": "specimen-01-region-a",
    "specimen_id": "specimen-01",
    "split": "development",
    "truth_status": "expert_adjudicated",
    "expert_reviewers": ["expert initials or lab record ID"],
    "source_sha256": "copy from run.json",
    "channel_0based": 0,
    "count_target": "cell bodies",
    "edge_policy": "exclude",
    "run_json": "run.json",
    "count_summary_json": "count.json",
    "corrected_labels": "corrected-labels.tif",
    "expert_labels": "expert-body-instances.tif",
    "roi_zyx": [0, 0, 0, 12, 128, 128]
  }]
}
```

`roi_zyx` is optional and uses **processing-grid**, end-exclusive coordinates. For a partial field, every voxel within this ROI needs an expert decision; unlabeled-but-unreviewed space cannot be treated as background. The script checks exact mask/run shape, source hash, channel, count target, edge rule, completed review status, corrected-label bytes, and specimen split separation. The `expert_adjudicated` field is an externally supplied declaration; the script cannot verify a person's expertise or the biological correctness of their masks.

```sh
.venv/bin/python tools/score_expert_benchmark.py \
  --manifest /path/to/expert-manifest.json \
  --out /path/to/real-count-scores.json
```

No such expert-adjudicated manifest is included with this repository, so real-image count accuracy remains unmeasured.
