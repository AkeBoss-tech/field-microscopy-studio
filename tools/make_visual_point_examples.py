"""Render source-coordinate, visually reviewed point examples from public starters.

These marks identify distinct bright structures in specified acquired planes.
They are deliberately not exhaustive cell counts or expert biological labels.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import tifffile
import roifile
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "visual-point-examples"
EXAMPLES = {
    "imop": {
        "source": "starter/imop.ome.tif", "channel": 1, "z": 7,
        "crop_xyxy": [150, 270, 370, 455],
        "points_xy": [[243, 314], [211, 368], [255, 411], [347, 363]],
        "label": "Distinct DAPI-channel bright focus (stain name presumed)",
    },
    "hair-control": {
        "source": "starter/hair-control.ome.tif", "channel": 0, "z": 29,
        "crop_xyxy": [160, 460, 390, 615],
        "points_xy": [[190, 527], [250, 527], [307, 527], [361, 527]],
        "label": "Distinct Channel 1 apical bright cap (stain identity unconfirmed)",
    },
}


def render(name: str, spec: dict) -> dict:
    source = ROOT / spec["source"]
    with tifffile.TiffFile(source) as tf:
        axes = tf.series[0].axes
        if axes != "ZCYX":
            raise ValueError(f"Unexpected axes for {name}: {axes}")
        stack = tf.asarray()
    z, channel = spec["z"], spec["channel"]
    x0, y0, x1, y1 = spec["crop_xyxy"]
    plane = stack[z, channel]
    low, high = np.percentile(stack[:, channel, ::8, ::8], [1, 99.8])
    crop = plane[y0:y1, x0:x1]
    gray = np.uint8(np.clip((crop - low) / max(high - low, 1), 0, 1) * 255)
    image = Image.fromarray(gray).convert("RGB")
    scale = 3
    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (image.width, image.height + 64), "#101c28")
    canvas.paste(image, (0, 64))
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 12), f"{name}  |  C{channel + 1}  |  acquired Z {z + 1}", fill="#e7f6ff")
    draw.text((16, 35), "Numbered centers of distinct visible signal; native XY coordinates", fill="#a9c6d8")
    for index, (x, y) in enumerate(spec["points_xy"], 1):
        px, py = (x - x0) * scale, (y - y0) * scale + 64
        draw.ellipse((px - 14, py - 14, px + 14, py + 14), outline="#ffce69", width=4)
        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill="#ffce69")
        draw.text((px + 16, py - 20), str(index), fill="#ffce69", stroke_width=2, stroke_fill="#1c2733")
    OUT.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT / f"{name}.png")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    document = {
        "source": spec["source"], "source_sha256": digest, "source_axes": axes,
        "source_shape_zcyx": list(stack.shape), "channel_zero_based": channel,
        "z_zero_based": z, "crop_xyxy_native": spec["crop_xyxy"],
        "confidence_scope": "High visual confidence in a distinct bright focus at each point in this one acquired plane. No cell type, neuron identity, count completeness, or full boundary is asserted.",
        "points": [{"index": i, "x": x, "y": y, "label": spec["label"]}
                   for i, (x, y) in enumerate(spec["points_xy"], 1)],
    }
    rois = []
    for i, (x, y) in enumerate(spec["points_xy"], 1):
        roi = roifile.ImagejRoi.frompoints(np.asarray([[x, y]], np.float32),
                                           name=f"{name}_visible_focus_{i:02d}",
                                           c=channel, z=z, t=0)
        roi.roitype = roifile.ROI_TYPE.POINT
        rois.append(roi)
    roifile.roiwrite(OUT / f"{name}-RoiSet.zip", rois, mode="w")
    (OUT / f"{name}.json").write_text(json.dumps(document, indent=2) + "\n")
    return document


if __name__ == "__main__":
    for key, value in EXAMPLES.items():
        result = render(key, value)
        print(f"{key}: {len(result['points'])} visible signal points")
