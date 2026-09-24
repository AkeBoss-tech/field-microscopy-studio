# Visually reviewed point examples

These are small, reproducible examples on the two public starter scans. Each PNG shows four numbered native-coordinate marks on distinct bright signal in **one acquired plane**. The JSON records source hash, zero-based channel/Z, coordinates, and the exact confidence scope. The ImageJ `RoiSet.zip` files import into FIELD's annotation workspace; the app's importer was checked to recover all eight channel/Z/XY coordinates exactly.

| Source | Reviewed plane | Marked feature | Image | Coordinates | Import |
|---|---|---|---|---|---|
| iMOP | C2, acquired Z 8 of 14 | Distinct DAPI-channel bright foci; DAPI name is presumed | [PNG](imop.png) | [JSON](imop.json) | [ROI ZIP](imop-RoiSet.zip) |
| Hair control | C1, acquired Z 30 of 40 | Distinct bright apical caps; stain identity is unconfirmed | [PNG](hair-control.png) | [JSON](hair-control.json) | [ROI ZIP](hair-control-RoiSet.zip) |

The marks are **not** exhaustive counts or verified cell/neuron identities. Boundaries and process ownership remain unresolved. In particular, the iMOP TUJ1-rich crossing area does not support confident assignment of a neurite to one soma from these planes. A biological ground-truth annotation set needs an expert channel map, inclusion/boundary rules, and independent review across the acquired Z stack.

Regenerate from the unchanged starter scans with `.venv/bin/python tools/make_visual_point_examples.py`, then visually inspect the PNGs before using the ROIs.
