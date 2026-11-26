"""
01_ifc_inventory.py  --  DSRM Activity 1 (Problem identification)
Opens the Revit IFC export and prints a model inventory: schema, units,
spatial hierarchy, building elements, voids and fills.

Usage:  python src/01_ifc_inventory.py data/BIMROS.ifc
"""
import sys
from collections import Counter

import ifcopenshell.util.element as ue

from bimros_common import banner, open_ifc, unit_scale, save_json

path = sys.argv[1] if len(sys.argv) > 1 else "data/BIMROS.ifc"
banner("STEP 01 | IFC MODEL INVENTORY")
model, declared, effective = open_ifc(path)

app = model.by_type("IfcApplication")[0]
print(f"file            : {path}")
print(f"authoring tool  : {app.ApplicationFullName} ({app.Version})")
print(f"declared schema : {declared}")
print(f"parsed as       : {effective}")
scale = unit_scale(model)
print(f"length unit     : 1 project unit = {scale} m  (FOOT)" if abs(scale - 0.3048) < 1e-9
      else f"length unit     : 1 project unit = {scale} m")

print("\n-- spatial hierarchy --")
for storey in model.by_type("IfcBuildingStorey"):
    contained = [e for rel in storey.ContainsElements for e in rel.RelatedElements]
    print(f"  {storey.Name:<4} elev={storey.Elevation * scale:>7.4f} m  "
          f"contains: {[f'{e.is_a()}:{e.GlobalId}' for e in contained]}")

print("\n-- element census --")
counts = Counter(e.is_a() for e in model.by_type("IfcProduct"))
for k, v in sorted(counts.items()):
    print(f"  {k:<24} {v}")

print("\n-- voids (IfcRelVoidsElement) and fills (IfcRelFillsElement) --")
inventory = {"declared_schema": declared, "parsed_schema": effective,
             "unit_scale_m": scale, "openings": []}
for rel in model.by_type("IfcRelVoidsElement"):
    op = rel.RelatedOpeningElement
    fill = [r.RelatedBuildingElement for r in op.HasFillings]
    cat = ue.get_psets(op).get("Other", {}).get("Category", "-")
    fill_txt = f"{fill[0].is_a()}:{fill[0].GlobalId}" if fill else "None (unfilled)"
    print(f"  host {rel.RelatingBuildingElement.GlobalId} <- opening {op.GlobalId}"
          f" | fill = {fill_txt} | category = {cat}")
    inventory["openings"].append({"global_id": op.GlobalId,
                                  "host": rel.RelatingBuildingElement.GlobalId,
                                  "filled_by": fill[0].GlobalId if fill else None,
                                  "category": cat})
print(f"\nRESULT: {len(inventory['openings'])} IfcOpeningElement instances found in source model")
save_json(inventory, "01_inventory.json")
