# External algorithms and 3D review

## Bring an algorithm into the app

Run a model on the **exact selected source image and channel**, then export a single-channel integer instance TIFF. Each positive ID must represent one object consistently through all acquired Z planes; zero is background. The TIFF must use `ZYX` for a stack (`YX` for a one-plane source) and match the entire native XY grid or its 2× or 4× block-mean grid. Crops, rotations, shifted grids, probability maps and binary foreground masks with touching objects are not valid instance results. Signed integer TIFFs are accepted when every value is nonnegative.

Choose the source and channel, click **Import masks**, name the algorithm and biological target, select the TIFF, and confirm source alignment. The app checks axes, size and IDs, but equal dimensions alone cannot prove registration. It saves the original file and SHA-256, a compact internal ID map, run provenance, source-aligned intensity, instance labels and an object CSV. Browser storage currently limits imports to 12 million label voxels (the native server default is 50 million); use a 2× or 4× XY result for large stacks in the browser.

Review the imported result in linked XY, XZ and YZ planes. Correct split, merge or false candidate masks, set **Count rules**, and mark each candidate. **Export → 3D boxes JSON** supplies native XYZ pixel bounds `[start, end)` for every selected object, physical bounds when calibration exists, channel, target, original submitted ID, edge flags and pinned label/review/protocol revisions. Export each channel's run separately and join on dataset/source hash; multiple algorithms on one channel remain distinct runs. A reviewed count is a reviewer-assessed count, not independent ground truth.

In **Annotate**, draw a 3D polyline on the process channel, then click **Tag neuron**. Choose a full-volume body or nucleus result from any channel. Nearby candidate boxes aid navigation; a zero-distance endpoint does not prove ownership. Save a tentative or reviewer-assessed link. Each link records the candidate run, object, channel and label revision. Editing the candidate mask invalidates that revision and requires reassessment. A nucleus tag identifies a candidate nucleus, not automatically a biologically confirmed neuron.

## Choosing methods for the two starter images

| Target | Current starting point | Why it needs review |
| --- | --- | --- |
| iMOP presumed DAPI nuclei | Import the saved volumetric Cellpose result as a candidate, then compare with volumetric watershed. | Earlier Cellpose 3D returned 144 instances versus 188 for stitched slices; these are disagreeing candidates. DAPI positivity alone does not establish neuronal identity. |
| iMOP presumed Tuj1 neurites | Inspect Sato/hysteresis and SNT paths against raw XY/XZ/YZ; trace ambiguous branches manually and link to a reviewed body/nucleus. | A ridge component is a network, and crossings can have different owners at different depths. |
| Hair cell detection | Start with the existing HCAT Myo7a + phalloidin detections where channel identities are confirmed; import or derive a 3D instance mask for volumetric boxes. | Historical five-field point F1 was 0.967 against a pilot AI-assisted reference. It does not measure full-stack body boundaries or establish expert truth. |

The hair starter currently labels its four channels by number. Confirm stain identity and the cell-count definition with the lab before using a specific channel as a biological target. Keep detection, 3D segmentation and neurite ownership as separate evaluation tasks. Do not select an algorithm from candidate count agreement alone.

## What would establish a reliable recipe

Independently annotate sparse, dense, dim, boundary and crossing regions from both real stacks. Freeze a specimen-level train/development/holdout split before tuning. Score 3D instance precision and recall at several IoU thresholds, center detection, split/merge rate, box coverage, edge behavior and count error. For neurites, score centerline coverage, false bridges and correct owner assignment, with an explicit unknown class when evidence is insufficient. Repeat at native, 2× and 4× XY using physical-unit settings and calibrated Z spacing. Treat transformed copies of the same biological image as one split.

Synthetic results are regression checks for geometry, file interchange and predictable failure cases. They cannot make a real-image accuracy claim. See [scaled modality benchmark](scaled-modalities.md) and [expert validation protocol](real-validation-protocol.md).
