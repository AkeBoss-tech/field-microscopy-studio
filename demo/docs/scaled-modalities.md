# Scaled synthetic checks for both starter scan styles

Reproduce with:

```sh
.venv/bin/python tools/evaluate_scaled_modalities.py \
  --out ../outputs/scaled-two-modality-benchmark.json
```

The fixed test uses procedural 12-plane touching bodies, crossing neurons, an empty field, edge-truncated bodies and depth-attenuated bodies at seed 530. It measures intensity quantiles separately from the packaged iMOP DAPI and hair Channel 1 stacks. Each scene is tested at native, 2× and 4× XY block mean. Truth IDs are sampled at the corresponding grid centers. Otsu, watershed with 5 or 9 grid-pixel seed spacing, and per-plane Sato use fixed parameters; Sato components are diagnostic networks, not biological body counts. Matching is one-to-one instance IoU ≥ 0.3. This is an independent seed from the older synthetic-v3 tuning seeds, but the image generator and geometry family are related.

| Style and XY scale | Best body-candidate macro F1 among Otsu/watershed | Empty-field false objects in that setting |
| --- | ---: | ---: |
| iMOP DAPI, native | 0.800 (watershed 9) | 70 |
| iMOP DAPI, 2× | 0.787 (watershed 5) | 74 |
| iMOP DAPI, 4× | 0.533 (Otsu or watershed 5) | 4 or 10 |
| Hair Channel 1, native | 0.787 (watershed 9) | 40 |
| Hair Channel 1, 2× | 0.787 (watershed 5) | 30 |
| Hair Channel 1, 4× | 0.687 (watershed 5) | 7 |

**Interpretation:** none of these frozen recipes handles a blank field reliably. Aggressive XY reduction suppresses some false objects but also loses small bodies. Hair style here means **intensity range only**; the procedural ellipsoids do not reproduce hair-cell rows, immunostain specificity, optical point-spread function, bleedthrough or real tissue variation. These scores cannot rank HCAT against Cellpose on real hair cells or prove a best real-image algorithm. The raw JSON records every scene, method, scale, count error and match score so failures can be inspected rather than averaged away.

Next benchmark revision: build multichannel, correlated 3D hair-cell scenes with row geometry, channel-specific stains, background structures and known ownership; estimate blur/noise/attenuation from real acquisitions without copying cell shapes; validate each generated channel and cross-channel registration. Keep independent biological specimens entirely out of tuning until expert masks exist.
