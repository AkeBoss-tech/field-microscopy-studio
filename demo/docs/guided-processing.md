# Guided processing and result explanations

Choose **Start a task → Count hair cells**. Confirm the hair-cell channel, select the region and acquired Z planes, and choose a working resolution. The guide explains signal selection, cleanup, detection, separation, review and reporting. It does not impose normal row counts or assign IHC/OHC identity.

## Compare preparation

In Process, choose **Compare cleanup options…**. This requires original-source intensity, 3D scope, and intensity-only, connected-region or watershed processing. Set smoothing/background widths and choose **Compare four options**. These are trial widths, not validated defaults.

The four panels compare no cleanup, smoothing only, background subtraction only, and both. All use the same crop, Z planes, resolution and original intensity window. Normalization is off throughout. Detection settings are held fixed, but Otsu recomputes its threshold for each prepared signal. Use the shared Z slider and switch between prepared intensity and outlines on the original signal. Fewer candidates does not imply greater accuracy.

**Use…** changes the preparation draft only. It does not save a run or accept any labels. Preview or run the selected region next. Compare dim, touching and extra-row examples against the original stack before choosing a recipe; freeze settings before evaluating independent specimens.

## Explain a saved result

Choose **Explain this result**, then select a saved run on the active channel. Its Input, Preparation, Detection, Output, Review and Validation sections are generated deterministically from the saved run and current review records. They do not use the unsaved recipe draft or require an AI provider.

- **Copy result explanation** copies the structured explanation.
- **Copy methods paragraph** copies a paragraph describing the recorded procedure and evidence status.
- **Download report** saves both forms plus exact parameters, calibration, source hash and label/review/count-rule revisions.

Parent runs are included in preparation lineage. Original algorithm totals remain distinct from corrected label totals. A reviewed count appears only when the existing counting protocol reports it ready. Neither candidate decisions nor matching aggregate totals establish independent biological accuracy. Historical outputs with incomplete provenance are excluded from the chooser; imported current results disclose missing preparation provenance.

The native app and static bundle share the same reporting/preview engine. Static deployment is separate from building the local bundle.
