# Review and detection methods

Review starts with the source image and candidate masks. Use **Next unresolved** to cycle through unreviewed and flagged IDs, including edge contacts. Inspect XY and both depth views, then accept, reject, flag, or correct the mask. Quick decisions preserve existing notes and advance; use **Edit decision / note** to change notes or restore Unreviewed. Changed masks invalidate older decisions. Revision checks reject stale saves.

The progress bar counts accepted + rejected candidates across the whole run. Final reviewed counts use the separately saved target, channel meaning, and edge rule; excluded edge candidates may still appear in the review queue. Status cards filter the candidate table. **Enlarge XY views** hides depth views temporarily; restore all views before deciding whether touching structures are separate.

## Choosing a method

| Signal / problem | Method | Main limitation |
| --- | --- | --- |
| Bright, separated regions | Connected regions (Otsu) | Touching objects remain joined |
| Touching compact objects | Distance watershed | Seed separation can split or merge objects |
| Uneven staining or illumination | Uneven brightness · local regions | Noise can become foreground; touching objects stay joined |
| Touching objects with shallow peaks | Touching objects · prominent peaks | Excessive prominence can merge real neighbors |
| Thin processes | Neurite intensity, adaptive, Sato, Frangi, Meijering | Connected networks are not individual neurons |

Local regions use a Gaussian neighborhood threshold in each acquired XY plane, plus a global floor equal to Otsu × threshold multiplier × floor multiplier. Connected components are labeled across the stack. Window size is in working pixels, so changing XY resolution changes its physical coverage. Offset is in prepared intensity units; positive offsets admit more foreground. Minimum foreground and final object size filters remain available.

Prominent-peak watershed uses Otsu foreground, a distance transform, h-maxima seed regions and watershed. Peak prominence uses µm in physical mode and working pixels in grid mode. At least one strongest seed is retained in each isolated foreground component even when its maximum is below the requested prominence. This avoids dropping whole regions solely because the prominence setting is high. No expected row count or hair-cell arrangement is imposed. Grid-mode distance transforms now use grid spacing; physical mode uses calibrated XYZ spacing.

Both methods run locally, support bounded preview and saved runs, and preserve effective parameters in explanations and provenance. None establishes biological identity or accuracy. Compare expert annotations for the same channel, region, Z range and edge policy; report false positives, missed objects, splits and merges separately. A candidate total alone is not accuracy.

References: [scikit-image local threshold](https://scikit-image.org/docs/stable/api/skimage.filters.html#skimage.filters.threshold_local), [h-maxima](https://scikit-image.org/docs/stable/api/skimage.morphology.html#skimage.morphology.h_maxima), [watershed](https://scikit-image.org/docs/stable/api/skimage.segmentation.html#skimage.segmentation.watershed).
