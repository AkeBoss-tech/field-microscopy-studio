# Candidate neurite measurements

Process offers five methods: intensity threshold, local threshold, Sato, Frangi and Meijering. Choose an analysis channel, scope and full-image or selected-region bounds, then preview. **Compare all 5 techniques** submits separate saved runs with the same region, preprocessing and working resolution.

Ridge methods can filter each acquired XY plane or an isotropic volume. Advanced controls include ridge widths, local threshold window/offset/contrast floor, terminal branch pruning and width-based soma exclusion. Physical scales require calibrated spacing; anisotropic volume ridge widths are rejected rather than silently treated as isotropic. XY filtering followed by volume skeletonization still uses every acquired Z plane.

Each saved run contains an immutable candidate mask, original measured skeleton TIFF, per-network CSV, branch CSV and summary JSON. Graph edges use axis-specific source spacing and the working XY reduction. Measurements include total centerline length, branches, endpoints, junction clusters and branch tortuosity. Adjacent junction voxels are grouped, and occupied corner shortcuts are suppressed to avoid counting both axial and diagonal connections. Terminal pruning affects the measured centerline, with its settings recorded separately from the original segmentation mask.

Review offers **Original measured centerline** as a separate image layer. Candidate tables and inspectors show current network measurements; corrected masks recompute their measurements. Original saved skeleton/CSV files remain frozen. CSV exports identify their label and review revisions. Calibrated lengths are in µm; uncalibrated results explicitly use working-grid units.

## Local comparison evidence

The implementation was exercised in 63 runs: three real fields with supplied sparse ImageJ polylines at three fixed recipes per method, five methods on each of two synthetic fixtures, five on the real native 14Z iMOP field, and three additional no-floor adaptive diagnostics. TIFF calibration and manually supplied path lengths were reconciled to the workbook. The report records source hashes, exact settings, foreground fraction, timings and support at 1/2/3 working-pixel proximity.

Adaptive thresholding's initial no-floor behavior selected 33–55% of real fields. A default global signal floor of 0.25×Otsu reduced the base foreground to 3.3–5.5%, with 60.9–71.6% of supplied sparse path samples within 2 working pixels of its skeleton. These figures are path proximity diagnostics. The provided traces do not label all negatives or every neurite, so this is not precision/recall or independent biological accuracy.

Report artifacts are in the parent workspace: `outputs/neurite-comparison-20261003/index.html`, `comparison.csv`, `report.json`, overlays and baseline skeleton/network/branch files. Reproduce from that workspace with:

```sh
microscopy-studio/.venv/bin/python microscopy-studio/tools/compare_neurites.py
```

## Interpretation

Connected signal produces connected networks. Crossings can merge different neurons, and remaining soma skeleton can add length. A volume can distinguish acquired Z positions but does not automatically assign every branch to a neuron. A projection measures projected geometry. Automated single-neuron ownership and biologically validated neurite lengths need reviewed references and remain unresolved.

Pixel reduction, threshold, region/context bounds, ridge widths, pruning and calibration affect the measurements. Compare methods on the same input and inspect acquired planes before interpreting totals. Network totals and a sparse workbook's manually drawn paths have different denominators and cannot be treated as direct agreement/error.

Implementation references: [scikit-image ridge filters](https://scikit-image.org/docs/stable/api/skimage.filters.html), [skeletonize](https://scikit-image.org/docs/stable/api/skimage.morphology.html#skimage.morphology.skeletonize).
