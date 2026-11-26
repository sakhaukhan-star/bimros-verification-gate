"""
json_to_sdf_converter.py  --  SYSTEM A (Non-LLM deterministic baseline)

Reconstruction, for reproducibility, of the rule-based JSON -> SDF step used
in the BIM-ROS Use Case 3088 pipeline. It deliberately keeps the three
behaviours observed when auditing the original script:
  (1) closed-world key lookup  : only the key "DoorOpening" is ever read,
                                 so any other opening is silently ignored;
  (2) schema-drift fallback     : wall size is read from payload["wall"]
                                 ["length"/"height"/"thickness"]; when those
                                 keys are absent a hard-coded default
                                 (3.5 x 2.8 x 0.2 m) is substituted;
  (3) silent exception handling : errors are swallowed, a syntactically valid
                                 .sdf is always written and exit code is 0.

Usage:  python src/json_to_sdf_converter.py [payload.json] [out.sdf]   (run from the repository root)
"""
import json
import sys
from pathlib import Path

DEFAULT_L, DEFAULT_H, DEFAULT_T = 3.5, 2.8, 0.2       # hard-coded fallbacks


def box_link(name, cx, cy, cz, sx, sy, sz):
    size = f"{sx:.4f} {sy:.4f} {sz:.4f}"
    return f"""    <link name="{name}">
      <pose>{cx:.4f} {cy:.4f} {cz:.4f} 0 0 0</pose>
      <collision name="c"><geometry><box><size>{size}</size></box></geometry></collision>
      <visual name="v"><geometry><box><size>{size}</size></box></geometry></visual>
    </link>"""


def convert(payload: dict) -> tuple[str, list[str]]:
    log = []
    try:
        L = payload["wall"]["length"]
        H = payload["wall"]["height"]
        T = payload["wall"]["thickness"]
    except Exception:                                   # silent fallback
        L, H, T = DEFAULT_L, DEFAULT_H, DEFAULT_T
        log.append("wall dims not found -> using defaults")
    links = []
    door = payload.get("openings", {}).get("DoorOpening")   # closed-world lookup
    if door:
        try:
            x0 = door["bbox"]["min"][0] - payload["wall"]["bbox"]["min"][0]
            dw = door["bbox"]["max"][0] - door["bbox"]["min"][0]
            dh = door["bbox"]["max"][2] - door["bbox"]["min"][2]
            x1 = min(x0 + dw, L)                            # silently clamped
            links.append(box_link("wall_left", x0 / 2, 0, H / 2, max(x0, 0), T, H))
            links.append(box_link("wall_right", (x1 + L) / 2, 0, H / 2, max(L - x1, 0), T, H))
            links.append(box_link("wall_header", (x0 + x1) / 2, 0, (dh + H) / 2, x1 - x0, T, H - dh))
        except Exception:
            links = []
    if not links:
        links.append(box_link("wall", L / 2, 0, H / 2, L, T, H))
    sdf = ('<?xml version="1.0"?>\n<sdf version="1.7">\n  <model name="fabricated_component">\n'
           '    <static>true</static>\n' + "\n".join(links) + "\n  </model>\n</sdf>\n")
    return sdf, log


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "output/ros_fabrication_payload.json")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "output/fabricated_component_baseline.sdf")
    print("=" * 72 + "\n SYSTEM A | json_to_sdf_converter.py (non-LLM baseline)\n" + "=" * 72)
    payload = json.loads(src.read_text())
    sdf, _log = convert(payload)          # _log is never surfaced to the user
    dst.write_text(sdf)
    n_links = sdf.count("<link ")
    print(f"input  : {src.name}  (openings in payload: {list(payload.get('openings', {}).keys())})")
    print(f"output : {dst.name}  ({n_links} <link> boxes)")
    print("status : SUCCESS  exit code 0")
