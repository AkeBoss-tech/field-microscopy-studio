"""Exercise import -> preview -> run -> review -> export on a running native FIELD server.

Use an isolated STUDIO_STORE. This writes six imported datasets and six runs.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.synthetic_benchmark import score_instances


def request(base: str, path: str, body=None, binary=False):
    headers = {"X-Studio-Request": "1"}
    data = None
    if body is not None:
        if isinstance(body, bytes):
            data = body
            headers["Content-Type"] = "application/octet-stream"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as response:
        result = response.read()
    return result if binary else json.loads(result)


def verify(base: str, suite: Path, tuning: Path) -> list[dict]:
    manifest = json.loads((suite / "manifest.json").read_text())
    selected = json.loads(tuning.read_text())["dimensions"]
    rows = []
    for record in manifest["cases"]:
        directory = Path(record["path"])
        source = directory / f"{record['case']}.ome.tif"
        truth = tifffile.imread(directory / "body_instances.tif")
        with tifffile.TiffFile(source) as tf:
            axes = tf.series[0].axes
        query = urllib.parse.urlencode({"name": source.name, "axes": axes,
                                        "xy": 1, "z": 2})
        imported = request(base, "/api/import-source?" + query, source.read_bytes())
        key = imported["id"]
        nz, nc, ny, nx = imported["shape"]
        assert (nz, nc, ny, nx) == ((truth.shape[0], 1, *truth.shape[1:])
                                     if truth.ndim == 3 else (1, 1, *truth.shape)), record["case"]
        params = {**selected[record["dimension"]]["selected_recipe"], "factor": 1}
        preview = request(base, "/api/preview", {"dataset": key, "channel": 0,
            "parameters": params, "bounds": [16, 16, 0, nx - 16, ny - 16, nz], "margin": 8})
        assert preview["preview"] and len(preview["planes"]) == nz
        job = request(base, "/api/run", {"dataset": key, "channel": 0, **params})
        deadline = time.monotonic() + 180
        while True:
            state = next(j for j in request(base, "/api/jobs") if j["id"] == job["id"])
            if state["status"] in ("completed", "failed", "canceled"):
                break
            if time.monotonic() > deadline:
                raise TimeoutError(record["case"])
            time.sleep(.25)
        if state["status"] != "completed":
            raise RuntimeError(f"{record['case']}: {state}")
        run_id = job["id"]
        exported = tifffile.imread(io.BytesIO(request(base,
            "/api/result-file?" + urllib.parse.urlencode({"run": run_id, "kind": "labels"}),
            binary=True)))
        if exported.ndim == 2:
            exported = exported[None]
        if truth.ndim == 2:
            truth = truth[None]
        assert exported.shape == truth.shape, record["case"]
        review = request(base, "/api/review?" + urllib.parse.urlencode({
            "dataset": key, "channel": 0, "run": run_id,
            "x": nx // 2, "y": ny // 2, "z": nz // 2}))
        assert all(review["planes"][axis]["png"] for axis in ("raw", "xy", "xz", "yz"))
        score = score_instances(truth, exported)
        rows.append({"case": record["case"], "dataset": key, "run": run_id,
                     "preview_planes": len(preview["planes"]),
                     "review_planes": 4, "export_shape": list(exported.shape), **score})
        print(record["case"], "workflow OK", "candidates", score["candidate_count"],
              "truth", score["truth_count"], "F1", round(score["f1_iou_0_3"], 3))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8877")
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--tuning", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.base_url.rstrip("/"), args.suite, args.tuning)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
