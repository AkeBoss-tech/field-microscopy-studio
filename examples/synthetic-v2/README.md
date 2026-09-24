# Procedural 2D and 3D counting scenes

Download an image TIFF and import it into FIELD with **Add image**. Each scene's
`truth.json` and `body_instances.tif` contain exact procedural body truth; neuron
scenes also include per-owner neurite masks. Import the **image** TIFF as source,
then choose a counting task, preview, run, and inspect candidates in Review.
The simulated spacing is 1 µm XY and 2 µm Z; it is not a measured microscope
calibration. `manifest.json` lists all six scenes, `scores.csv` summarizes the
four runnable methods, and `tuning.json` records development and held-out seeds.

| Scene | Dimensions | Bodies | Import TIFF | Centers and graph | Body masks |
|---|---|---:|---|---|---|
| cells_isolated_2d | 2D | 9 | [Image](cells_isolated_2d/cells_isolated_2d.ome.tif) | [Truth](cells_isolated_2d/truth.json) | [Masks](cells_isolated_2d/body_instances.tif) |
| cells_touching_2d | 2D | 10 | [Image](cells_touching_2d/cells_touching_2d.ome.tif) | [Truth](cells_touching_2d/truth.json) | [Masks](cells_touching_2d/body_instances.tif) |
| cells_dim_2d | 2D | 8 | [Image](cells_dim_2d/cells_dim_2d.ome.tif) | [Truth](cells_dim_2d/truth.json) | [Masks](cells_dim_2d/body_instances.tif) |
| neurons_crossing_2d | 2D | 5 | [Image](neurons_crossing_2d/neurons_crossing_2d.ome.tif) | [Truth](neurons_crossing_2d/truth.json) | [Masks](neurons_crossing_2d/body_instances.tif) |
| cells_touching_3d | 3D | 8 | [Image](cells_touching_3d/cells_touching_3d.ome.tif) | [Truth](cells_touching_3d/truth.json) | [Masks](cells_touching_3d/body_instances.tif) |
| neurons_crossing_3d | 3D | 5 | [Image](neurons_crossing_3d/neurons_crossing_3d.ome.tif) | [Truth](neurons_crossing_3d/truth.json) | [Masks](neurons_crossing_3d/body_instances.tif) |

The source images are not copied into these scenes. All six files passed native
import, preview, full-volume run, label export, and linked XY/XZ/YZ review.
The algorithms are **not** 100% accurate: even the tuned seed-17 touching 3D
case gives 9 candidates for 8 true bodies. These examples check code paths and
failure modes, not biological cell counts or neuron ownership in real scans.
