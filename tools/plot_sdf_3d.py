"""
plot_sdf_3d.py  --  three-dimensional view of the two SDF files written for T01

Draws every <link> box of each SDF from its <pose> (centre x, y, z) and <size> (x, y, z);
nothing is drawn by hand:
  (a) System A: output/fabricated_component_baseline.sdf  (json_to_sdf_converter.py)
  (b) System B: output/fabricated_component.sdf            (claude_verification_gate.py, approved)

Usage:  python tools/plot_sdf_3d.py  -> output/sdf_3d_T01_systemA_vs_systemB.png
"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

OUT = Path(__file__).resolve().parents[1] / "output"   # <repo>/output


def sdf_boxes(path):
    boxes = []
    for name, body in re.findall(r"<link name=\"([^\"]+)\">(.*?)</link>", path.read_text(), flags=re.S):
        c = list(map(float, re.search(r"<pose>([^<]+)</pose>", body).group(1).split()[:3]))
        s = list(map(float, re.search(r"<size>([^<]+)</size>", body).group(1).split()))
        boxes.append((name, c, s))
    return boxes


def cuboid(c, s):
    x0, y0, z0 = (c[i] - s[i] / 2 for i in range(3))
    x1, y1, z1 = (c[i] + s[i] / 2 for i in range(3))
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]
    return [[v[i] for i in face] for face in f]


def panel(ax, boxes, title):
    for _, c, s in boxes:
        if min(s) <= 0:            # zero-width link: nothing to draw, but it is counted in the title
            continue
        ax.add_collection3d(Poly3DCollection(cuboid(c, s), facecolor="#e7dcc8", edgecolor="#3f3f46", lw=0.6))
    ax.set_xlim(0, 5.8); ax.set_ylim(-1.5, 1.5); ax.set_zlim(0, 3.4)
    ax.set_box_aspect((5.8, 3.0, 3.4))
    ax.set_xlabel("X (m)", fontsize=7); ax.set_ylabel("Y (m)", fontsize=7); ax.set_zlabel("Z (m)", fontsize=7)
    ax.tick_params(labelsize=6); ax.view_init(elev=18, azim=-60)
    ax.set_title(title, fontsize=8)


def main():
    a = sdf_boxes(OUT / "fabricated_component_baseline.sdf")
    b = sdf_boxes(OUT / "fabricated_component.sdf")
    fig = plt.figure(figsize=(9.0, 3.6), dpi=200)
    panel(fig.add_subplot(1, 2, 1, projection="3d"), a,
          f"(a) System A SDF: {len(a)} links, thickness {a[0][2][1]:.2f} m, height {a[0][2][2]:.2f} m")
    panel(fig.add_subplot(1, 2, 2, projection="3d"), b,
          f"(b) System B SDF: {len(b)} links, thickness {b[0][2][1]:.4f} m, height {b[0][2][2]:.4f} m")
    fig.tight_layout()
    fig.savefig(OUT / "sdf_3d_T01_systemA_vs_systemB.png", bbox_inches="tight")
    for label, boxes in (("System A", a), ("System B", b)):
        print(label)
        for name, c, s in boxes:
            print(f"  {name:12s} centre {c[0]:.4f} {c[1]:.4f} {c[2]:.4f}  size {s[0]:.4f} x {s[1]:.4f} x {s[2]:.4f}")


if __name__ == "__main__":
    main()
