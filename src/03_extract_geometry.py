"""
03_extract_geometry.py  --  geometry layer (IfcOpenShell / OpenCASCADE BREP)
Tessellates the wall (with its voids already subtracted) and each opening in
world coordinates and writes output/ros_fabrication_payload.json.

Usage:  python src/03_extract_geometry.py data/BIMROS.ifc
"""
import sys

import ifcopenshell.geom
import numpy as np

from bimros_common import banner, open_ifc, save_json, load_json

path = sys.argv[1] if len(sys.argv) > 1 else "data/BIMROS.ifc"
banner("STEP 03 | GEOMETRY EXTRACTION (IfcOpenShell BREP) -> ros_fabrication_payload.json")
model, _, _ = open_ifc(path, verbose=False)
semantic = load_json("cut_job_semantic.json")

settings = ifcopenshell.geom.settings()
settings.set("use-world-coords", True)          # metres, world frame


def verts_of(entity):
    shape = ifcopenshell.geom.create_shape(settings, entity)
    return np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)


def bbox(v):
    mn, mx = v.min(axis=0), v.max(axis=0)
    return {"min": mn.round(4).tolist(), "max": mx.round(4).tolist()}


wall = model.by_guid(semantic["wall"]["global_id"])
wv = verts_of(wall)
# de-duplicate (tessellation repeats shared vertices)
wv_unique = np.unique(wv.round(6), axis=0)

openings = {}
for o in semantic["openings"]:
    v = verts_of(model.by_guid(o["global_id"]))
    openings[o["role"]] = {"global_id": o["global_id"], "vertex_count": int(len(np.unique(v.round(6), axis=0))),
                           "bbox": bbox(v)}

payload = {
    "element_global_id": wall.GlobalId,
    "units": "m",
    "frame": "world",
    "wall": {
        "vertex_count": int(len(wv_unique)),
        "vertices": wv_unique.round(4).tolist(),
        "bbox": bbox(wv_unique),
    },
    "openings": openings,
}
p = save_json(payload, "ros_fabrication_payload.json")
print(f"wall {wall.GlobalId}: {payload['wall']['vertex_count']} unique BREP vertices "
      f"(8 outer + 8 per through-void)")
print(f"  bbox min = {payload['wall']['bbox']['min']}")
print(f"  bbox max = {payload['wall']['bbox']['max']}")
for role, o in openings.items():
    print(f"  {role:<14} {o['global_id']}  {o['vertex_count']} vertices  bbox={o['bbox']['min']} .. {o['bbox']['max']}")
print(f"\nRESULT: geometry payload written -> {p.name}  (openings serialised = {len(openings)})")
