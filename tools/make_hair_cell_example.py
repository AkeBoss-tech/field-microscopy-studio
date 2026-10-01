"""Rebuild the assistant-curated IHC/OHC example for the Control Mid-1 starter.

Centres: OHCs from peak detection on Myo7a (C1), every candidate visually checked;
IHCs placed by hand on the row of round Myo7a bodies (the detector picked fibres below them).
Masks: 3D seeded watershed on smoothed C1, one seed column per centre, limited to the cell's
band and to its nearest seed in XY. Not expert-validated.
"""
import json
from pathlib import Path
import numpy as np
import tifffile
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from skimage.filters import threshold_otsu
from skimage.segmentation import find_boundaries, watershed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'examples' / 'hair-control-ihc-ohc'
meta = json.loads((ROOT / 'starter' / 'hair-control.json').read_text())
volume = tifffile.imread(ROOT / meta['path'])          # Z, C, Y, X
myo7a = volume[:, 0].astype(np.float32)
nz, ny, nx = myo7a.shape
sx, sy, sz = meta['spacing']
centres = json.loads((OUT / 'centers.json').read_text())
smooth = ndi.gaussian_filter(myo7a, (.7, 1.5, 1.5))
Y, X = np.mgrid[0:ny, 0:nx]


def segment(points, band, zrange, radius, fraction):
    (y0, y1), (z0, z1) = band, zrange
    region = np.zeros(myo7a.shape, bool)
    region[z0:z1, y0:y1] = True
    threshold = threshold_otsu(smooth[z0:z1, y0:y1][::2, ::2, ::2]) * fraction
    markers = np.zeros(myo7a.shape, np.int32)
    nearest = np.zeros((ny, nx), np.int32)
    best = np.full((ny, nx), np.inf)
    for i, (x, y) in enumerate(points, 1):
        profile = smooth[:, max(0, y - 3):y + 4, max(0, x - 3):x + 4].mean((1, 2))
        profile[:z0] = 0
        profile[z1:] = 0
        zs = np.where(profile > threshold)[0]
        if not len(zs):
            zs = np.array([int(np.argmax(profile))])
        disk = (X - x) ** 2 + (Y - y) ** 2 <= 9
        for z in range(zs.min(), zs.max() + 1):
            markers[z][disk] = i
        d = (X - x) ** 2 + (Y - y) ** 2
        closer = d < best
        best[closer] = d[closer]
        nearest[closer] = i
    labels = watershed(-smooth, markers, mask=region & (smooth > threshold) & (best <= radius ** 2)[None])
    labels[labels != nearest[None]] = 0
    out = np.zeros(myo7a.shape, np.uint16)
    for i in range(1, len(points) + 1):
        parts, n = ndi.label(labels == i)
        if n:
            sizes = ndi.sum(np.ones_like(parts), parts, range(1, n + 1))
            out[parts == 1 + int(np.argmax(sizes))] = i
    return out


# Order cells left to right (IHC) and by row, then left to right (OHC).
ihc_points = sorted(centres['ihc'])
ohc = np.array(centres['ohc'])
fit = np.polyfit(ohc[:, 0], ohc[:, 1], 2)
residual = ohc[:, 1] - np.polyval(fit, ohc[:, 0])
# Rows numbered anatomically: row 1 is nearest the IHCs (largest Y in this field).
rows = 3 - np.digitize(residual, [-15, 15])
order = np.lexsort((ohc[:, 0], rows))
ohc_points = [list(map(int, ohc[i])) for i in order]
ohc_rows = [int(rows[i]) for i in order]

ihc = segment(ihc_points, (492, 590), (4, 38), 28, .9)
ohc_labels = segment(ohc_points, (262, 452), (16, 40), 24, 1.0)
def block_mode(labels):
    # 2x2 XY majority vote; the in-app example uses the 2x grid to fit the browser import limit.
    blocks = labels.reshape(nz, ny // 2, 2, nx // 2, 2).transpose(0, 1, 3, 2, 4).reshape(nz, ny // 2, nx // 2, 4)
    out = np.zeros((nz, ny // 2, nx // 2), labels.dtype)
    best = np.zeros(out.shape, np.int8)
    for k in range(4):
        candidate = blocks[..., k]
        votes = (blocks == candidate[..., None]).sum(-1)
        better = (candidate > 0) & (votes > best)
        out[better] = candidate[better]
        best[better] = votes[better]
    return out
for name, labels in [('ihc', ihc), ('ohc', ohc_labels)]:
    tifffile.imwrite(OUT / f'{name}-labels-native.tif', labels, compression='zlib', metadata={'axes': 'ZYX'})
    tifffile.imwrite(OUT / f'{name}-labels.tif', block_mode(labels), compression='zlib', metadata={'axes': 'ZYX'})

rows_out, items = [], []
for kind, labels, points, extra in [('IHC', ihc, ihc_points, [None] * len(ihc_points)), ('OHC', ohc_labels, ohc_points, ohc_rows)]:
    for i, ((x, y), row) in enumerate(zip(points, extra), 1):
        zz, yy, xx = np.nonzero(labels == i)
        edge = bool(xx.min() == 0 or xx.max() == nx - 1 or zz.min() == 0 or zz.max() == nz - 1)
        z_centre = int(round(zz.mean()))
        rows_out.append(dict(type=kind, id=i, ohc_row=row, x=x, y=y, z_center=z_centre,
                             z_first=int(zz.min()), z_last=int(zz.max()), voxels=int(len(zz)),
                             volume_um3=round(len(zz) * sx * sy * sz, 1), touches_image_edge=edge))
        items.append(dict(type='point', domain='volume', channel=0, z=z_centre,
                          points=[[float(x), float(y), float(z_centre)]],
                          label=f'{kind} {i}' + (f' · row {row}' if row else '') + (' · edge' if edge else ''),
                          status='uncertain' if edge else 'unreviewed'))

with (OUT / 'cells.csv').open('w') as f:
    keys = list(rows_out[0])
    f.write(','.join(keys) + '\n')
    for r in rows_out:
        f.write(','.join('' if r[k] is None else str(r[k]) for k in keys) + '\n')
summary = dict(dataset='hair-control', source_sha256=meta.get('original_sha256'), channel_0based=0,
               channel_meaning='Myo7a (presumed C1; confirm with the lab)',
               ihc=len(ihc_points), ohc=len(ohc_points), ohc_rows={str(r): ohc_rows.count(r) for r in sorted(set(ohc_rows))},
               edge_cells={k: sum(1 for r in rows_out if r['type'] == k and r['touches_image_edge']) for k in ('IHC', 'OHC')},
               author='Assistant-curated example (not expert-validated)', items=items)
(OUT / 'annotations.json').write_text(json.dumps(summary, indent=1))

# Overview figure: Myo7a maximum projection with numbered IHC (amber) and OHC (green) outlines.
def norm(a):
    lo, hi = np.percentile(a, [1, 99.7])
    return np.clip((a - lo) / (hi - lo), 0, 1)
rgb = np.stack([norm(myo7a.max(0))] * 3, -1)
for labels, colour in [(ohc_labels.max(0), (.3, 1, .6)), (ihc.max(0), (1, .75, .2))]:
    rgb[find_boundaries(labels, mode='inner')] = colour
img = Image.fromarray(np.uint8(rgb[200:720] * 255)).convert('RGB')
draw = ImageDraw.Draw(img)
for r in rows_out:
    draw.text((r['x'] - 6, r['y'] - 200 - 6), str(r['id']), fill=(255, 210, 90) if r['type'] == 'IHC' else (150, 255, 190))
img.save(OUT / 'overview.png')
print(json.dumps({k: v for k, v in summary.items() if k != 'items'}, indent=1))
