"""
02_extract_semantic.py  --  semantic layer (stand-in for the ifcOWL/SPARQL
WebServer query of Use Case 3088).
Produces output/cut_job_semantic.json: the *intended* fabrication job
(what the BIM author designed), with all values converted to metres.

Usage:  python src/02_extract_semantic.py data/BIMROS.ifc
"""
import sys

import ifcopenshell.util.element as ue

from bimros_common import banner, open_ifc, unit_scale, save_json

path = sys.argv[1] if len(sys.argv) > 1 else "data/BIMROS.ifc"
banner("STEP 02 | SEMANTIC EXTRACTION  ->  cut_job_semantic.json")
model, declared, _ = open_ifc(path, verbose=False)
s = unit_scale(model)

wall = model.by_type("IfcWallStandardCase")[0]
ps = ue.get_psets(wall)
wtype = ue.get_type(wall)
storey = ue.get_container(wall)

layers = []
mat = ue.get_material(wall)
layer_set = getattr(mat, "ForLayerSet", None) or mat
for lyr in getattr(layer_set, "MaterialLayers", []):
    layers.append({"material": lyr.Material.Name, "thickness_m": round(lyr.LayerThickness * s, 4)})


def profile_dims(opening):
    """Width/height of the extruded rectangular void profile (metres)."""
    for rep in opening.Representation.Representations:
        for item in rep.Items:
            if item.is_a("IfcExtrudedAreaSolid") and item.SweptArea.is_a("IfcRectangleProfileDef"):
                p = item.SweptArea
                return round(p.XDim * s, 4), round(p.YDim * s, 4)
    return None, None


openings = []
for rel in wall.HasOpenings:
    op = rel.RelatedOpeningElement
    fills = [r.RelatedBuildingElement for r in op.HasFillings]
    a, b = profile_dims(op)
    if fills and fills[0].is_a("IfcDoor"):
        role = "DoorOpening"
        dps = ue.get_psets(ue.get_type(fills[0]) or fills[0]).get("Dimensions", {})
        # nominal leaf size from the door type (36" x 84"), rough opening = void profile
        width = round(dps.get("Width", fills[0].OverallWidth) * s, 4)
        height = round(dps.get("Height", fills[0].OverallHeight) * s, 4)
    else:
        role = "WindowOpening"                       # unfilled rectangular wall opening
        width, height = max(a, b), min(a, b)
    openings.append({
        "role": role,
        "global_id": op.GlobalId,
        "revit_category": ue.get_psets(op).get("Other", {}).get("Category"),
        "filled_by": {"ifc_class": fills[0].is_a(), "global_id": fills[0].GlobalId} if fills else None,
        "nominal_width_m": width,
        "nominal_height_m": height,
        "void_profile_m": [a, b],
    })

job = {
    "source": {"file": path, "declared_schema": declared, "unit_scale_m": s},
    "wall": {
        "global_id": wall.GlobalId,
        "ifc_class": wall.is_a(),
        "type_name": wtype.Name if wtype else None,
        "storey": storey.Name if storey else None,
        "length_m": round(ps["Dimensions"]["Length"] * s, 4),
        "height_m": round(ps["Constraints"]["Unconnected Height"] * s, 4),
        "thickness_m": round(ps["Construction"]["Width"] * s, 4) if "Construction" in ps
                       else round(sum(l["thickness_m"] for l in layers), 4),
        "is_external": ps.get("Pset_WallCommon", {}).get("IsExternal"),
        "load_bearing": ps.get("Pset_WallCommon", {}).get("LoadBearing"),
        "material_layers": layers,
    },
    "openings": openings,
    "opening_count": len(openings),
}
# thickness from type pset if instance pset lacks it
if wtype:
    tps = ue.get_psets(wtype)
    if "Construction" in tps and "Width" in tps["Construction"]:
        job["wall"]["thickness_m"] = round(tps["Construction"]["Width"] * s, 4)

p = save_json(job, "cut_job_semantic.json")
w = job["wall"]
print(f"wall {w['global_id']}  {w['type_name']}")
print(f"  L x H x T = {w['length_m']} x {w['height_m']} x {w['thickness_m']} m   storey={w['storey']}")
print(f"  layers    = " + ", ".join(f"{l['material']} {l['thickness_m']} m" for l in layers))
for o in openings:
    print(f"  {o['role']:<14} {o['global_id']}  {o['nominal_width_m']} x {o['nominal_height_m']} m"
          f"  fill={o['filled_by']['ifc_class'] if o['filled_by'] else 'None'}")
print(f"\nRESULT: semantic job written -> {p.name}  (opening_count = {job['opening_count']})")
