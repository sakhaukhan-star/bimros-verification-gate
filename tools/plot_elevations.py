"""
plot_elevations.py  --  front-elevation plot of the IFC ground truth and the System A SDF

Draws two panels from the files only; nothing is drawn by hand:
  (a) ground truth: wall and opening extents computed from the BREP vertices in
      output/ros_fabrication_payload.json (written by 03_extract_geometry.py from BIMROS.ifc)
  (b) System A: every <link> box in output/fabricated_component_baseline.sdf, drawn from its
      <pose> (centre) and <size> (width, thickness, height) as seen from the front (x-z plane)

Usage:  python tools/plot_elevations.py         -> output/elevation_ground_truth_vs_systemA.png
"""
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

OUT = Path(__file__).resolve().parents[1] / "output"   # <repo>/output


def ground_truth(payload):
    v = np.asarray(payload["wall"]["vertices"], dtype=float)
    mn, mx = v.min(axis=0), v.max(axis=0)
    wall = (mx[0] - mn[0], mx[2] - mn[2])
    openings = {}
    for role, o in payload["openings"].items():
        a, b = np.asarray(o["bbox"]["min"]), np.asarray(o["bbox"]["max"])
        openings[role] = (a[0] - mn[0], a[2] - mn[2], b[0] - a[0], b[2] - a[2])   # x, z, width, height
    return wall, openings


def sdf_boxes(path):
    text = path.read_text()
    boxes = []
    for link in re.findall(r"<link name=\"([^\"]+)\">(.*?)</link>", text, flags=re.S):
        name, body = link
        cx, _, cz = map(float, re.search(r"<pose>([^<]+)</pose>", body).group(1).split()[:3])
        sx, _, sz = map(float, re.search(r"<size>([^<]+)</size>", body).group(1).split())
        boxes.append((name, cx - sx / 2, cz - sz / 2, sx, sz))
    return boxes


def main():
    payload = json.loads((OUT / "ros_fabrication_payload.json").read_text())
    (L, H), openings = ground_truth(payload)
    boxes = sdf_boxes(OUT / "fabricated_component_baseline.sdf")

    fig, axs = plt.subplots(1, 2, figsize=(9.0, 3.2), dpi=200)
    a = axs[0]
    a.add_patch(Rectangle((0, 0), L, H, fc="#e5e7eb", ec="#111827", lw=1.2))
    for role, (x, z, w, h) in openings.items():
        a.add_patch(Rectangle((x, z), w, h, fc="white", ec="#2563eb", lw=1.3))
        a.text(x + w / 2, z + h + 0.08, role.replace("Opening", ""), ha="center", fontsize=7, color="#2563eb")
    a.set_title(f"(a) Ground truth - IFC BREP\n{L:.4f} x {H:.4f} m, {len(openings)} openings", fontsize=8)

    b = axs[1]
    for name, x, z, w, h in boxes:
        b.add_patch(Rectangle((x, z), max(w, 0.01), h, fc="#dc2626", alpha=0.25, ec="#dc2626", lw=1))
    b.set_title(f"(b) System A SDF - {len(boxes)} boxes\nwindow absent, default height {max(z + h for _, _, z, _, h in boxes):.1f} m",
                fontsize=8)
    for ax in axs:
        ax.set_xlim(-0.2, 6.0); ax.set_ylim(-0.2, 3.5); ax.set_aspect("equal")
        ax.set_xlabel("x (m)", fontsize=7); ax.tick_params(labelsize=6)
        ax.spines[["top", "right"]].set_visible(False)
    axs[0].set_ylabel("z above wall base (m)", fontsize=7)
    fig.tight_layout()
    dst = OUT / "elevation_ground_truth_vs_systemA.png"
    fig.savefig(dst)
    print(f"boxes read from SDF: {[(n, round(w, 4), round(h, 4)) for n, _, _, w, h in boxes]}")
    print(f"figure -> {dst}")


if __name__ == "__main__":
    main()
