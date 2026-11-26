"""
bimros_common.py
Shared helpers for the BIM-ROS non-LLM pipeline and the Neuro-Symbolic
Verification Gate (MSc dissertation artefact).

Responsibilities
  * open an IFC file, normalising legacy schema headers (Revit "IFC2x2"
    exports are not supported by IfcOpenShell >= 0.8)
  * unit handling (project length unit -> metres)
  * small JSON / console helpers used by every stage
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.unit as ifc_unit

OUT_DIR = Path(__file__).resolve().parents[1] / "output"   # <repo>/output
OUT_DIR.mkdir(exist_ok=True)

SUPPORTED = {"IFC2X3", "IFC4", "IFC4X3_ADD2"}


def banner(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n {title}\n{line}")


def read_header_schema(path: Path) -> str:
    """Read FILE_SCHEMA from the STEP header without parsing the model."""
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        head = fh.read(4000)
    m = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", head)
    return m.group(1) if m else "UNKNOWN"


def open_ifc(path: str | Path, verbose: bool = True):
    """Open an IFC file. If the header declares IFC2X2_FINAL (legacy Revit
    export) the header is rewritten to IFC2X3, which is upward compatible for
    the entity subset used here (walls, openings, doors, property sets).
    Returns (model, declared_schema, effective_schema)."""
    path = Path(path)
    declared = read_header_schema(path)
    target = path
    if declared not in SUPPORTED:
        if declared.startswith("IFC2X2"):
            tmp = Path(tempfile.gettempdir()) / f"{path.stem}_IFC2X3.ifc"
            text = path.read_text(encoding="utf-8", errors="ignore")
            text = text.replace(f"FILE_SCHEMA(('{declared}'))", "FILE_SCHEMA(('IFC2X3'))")
            tmp.write_text(text, encoding="utf-8")
            target = tmp
            if verbose:
                print(f"[schema] declared={declared} -> not supported by IfcOpenShell "
                      f"{ifcopenshell.version}; header normalised to IFC2X3")
        else:
            raise ifcopenshell.SchemaError(f"Unsupported schema: {declared}")
    model = ifcopenshell.open(str(target))
    return model, declared, model.schema


def unit_scale(model) -> float:
    """Factor converting project length units to metres (FOOT -> 0.3048)."""
    return float(ifc_unit.calculate_unit_scale(model))


def pset_value(element, pset_name: str, prop: str):
    """Return a single property value from instance- or type-level psets."""
    import ifcopenshell.util.element as ue
    psets = ue.get_psets(element)
    return psets.get(pset_name, {}).get(prop)


def save_json(obj, name: str) -> Path:
    p = OUT_DIR / name
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def load_json(name: str):
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))
