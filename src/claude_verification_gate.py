"""
claude_verification_gate.py  --  SYSTEM B (Neuro-Symbolic Verification Gate)

Post-geometry lineage gate placed between IfcOpenShell geometry extraction
(ros_fabrication_payload.json) and SDF/ROS formatting.

  Stage 1  deterministic vertex bounding-box computation        (symbolic)
  Stage 2  context & constraint assembly + rule pre-checks      (symbolic)
  Stage 3  schema-enforced semantic inference, Claude tool use  (neural)
  Stage 4  deterministic routing & ROS gating                   (symbolic)

Usage
  python src/claude_verification_gate.py               # uses Claude if ANTHROPIC_API_KEY is set
  python src/claude_verification_gate.py --offline     # symbolic-only (no API call)
  python src/claude_verification_gate.py --semantic S.json --payload P.json

Exit code 0 = approved (fabricated_component.sdf written), 1 = blocked.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional

import numpy as np
from pydantic import BaseModel, Field

OUT = Path(__file__).resolve().parents[1] / "output"   # <repo>/output
MODEL = os.environ.get("GATE_MODEL", "claude-sonnet-4-6")

# --- robot work-envelope and tolerance rules -------------------------------
ENVELOPE = {
    "max_wall_height_m": 3.50,
    "max_board_width_m": 1.25,      # gypsum board stock width (wall is cut into boards)
    "min_thickness_m": 0.05,
    "length_unit": "m",
    "dimension_tolerance_m": 0.005,
}


# --- Pydantic schema the LLM must return (forced tool use) -----------------
class Category(str, Enum):
    MISSING_OPENING = "MISSING_OPENING"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    UNIT_OR_SCALE_ERROR = "UNIT_OR_SCALE_ERROR"
    ID_LINEAGE_CORRUPTION = "ID_LINEAGE_CORRUPTION"
    ENVELOPE_VIOLATION = "ENVELOPE_VIOLATION"


class Finding(BaseModel):
    category: Category
    element_global_id: Optional[str] = None
    evidence: str = Field(..., description="Values compared, in metres")
    severity: str = Field(..., pattern="^(BLOCKING|WARNING)$")


class VerificationVerdict(BaseModel):
    is_approved_for_ros: bool
    findings: List[Finding]
    status_message: str = Field(..., description="One-paragraph note for the BIM coordinator")


def banner(t):
    print("\n" + "-" * 72 + f"\n {t}\n" + "-" * 72)


# --- Stage 1 -----------------------------------------------------------------
def stage1_bbox(payload: dict) -> dict:
    v = np.asarray(payload["wall"]["vertices"], dtype=float)
    mn, mx = v.min(axis=0), v.max(axis=0)
    d = mx - mn
    horiz = sorted([d[0], d[1]])
    res = {"vertex_count": int(len(v)), "delta_x": round(float(d[0]), 4),
           "delta_y": round(float(d[1]), 4), "delta_z": round(float(d[2]), 4),
           "length_m": round(float(horiz[1]), 4), "thickness_m": round(float(horiz[0]), 4),
           "height_m": round(float(d[2]), 4), "origin": mn.round(4).tolist(), "openings": {}}
    for role, o in payload.get("openings", {}).items():
        omn, omx = np.array(o["bbox"]["min"]), np.array(o["bbox"]["max"])
        od = omx - omn
        res["openings"][role] = {"global_id": o.get("global_id"),
                                 "width_m": round(float(max(od[0], od[1])), 4),
                                 "height_m": round(float(od[2]), 4),
                                 "offset_x_m": round(float(omn[0] - mn[0]), 4),
                                 "sill_m": round(float(omn[2] - mn[2]), 4)}
    return res


# --- Stage 2 -----------------------------------------------------------------
def stage2_context(semantic: dict, payload: dict, geo: dict) -> dict:
    tol = ENVELOPE["dimension_tolerance_m"]
    checks = []

    def add(cid, ok, cat, gid, ev):
        checks.append({"id": cid, "result": "PASS" if ok else "FAIL",
                       "category": None if ok else cat, "element_global_id": gid, "evidence": ev})

    w = semantic["wall"]
    add("C1_wall_id", payload.get("element_global_id") == w["global_id"], "ID_LINEAGE_CORRUPTION",
        w["global_id"], f"semantic={w['global_id']} geometry={payload.get('element_global_id')}")
    for k in ("length_m", "height_m", "thickness_m"):
        sv, gv = w[k], geo[k]
        ratio = (sv / gv) if gv else float("inf")
        cat = "UNIT_OR_SCALE_ERROR" if gv and (abs(ratio - 1000) < 5 or abs(ratio - 0.001) < 1e-4
                                               or abs(ratio - 3.2808) < 0.01) else "DIMENSION_MISMATCH"
        add(f"C2_{k}", abs(sv - gv) <= tol, cat, w["global_id"], f"semantic={sv} geometry={gv}")
    add("C3_opening_count", semantic["opening_count"] == len(geo["openings"]), "MISSING_OPENING", None,
        f"semantic={semantic['opening_count']} geometry={len(geo['openings'])}")
    for o in semantic["openings"]:
        g = geo["openings"].get(o["role"])
        if g is None:
            add(f"C4_{o['role']}_present", False, "MISSING_OPENING", o["global_id"],
                f"{o['role']} in ifcOWL/semantic job but absent from geometry payload")
            continue
        add(f"C4_{o['role']}_id", g["global_id"] == o["global_id"], "ID_LINEAGE_CORRUPTION",
            o["global_id"], f"semantic={o['global_id']} geometry={g['global_id']}")
        sw = max(o["void_profile_m"]) if o["role"] != "DoorOpening" else None
        for key, val in (("width_m", g["width_m"]), ("height_m", g["height_m"])):
            if val > 50:
                add(f"C5_{o['role']}_{key}_unit", False, "UNIT_OR_SCALE_ERROR", o["global_id"],
                    f"{key}={val} (value implies millimetres, metres expected)")
        if g["width_m"] >= geo["length_m"] or g["offset_x_m"] + g["width_m"] > geo["length_m"] + tol:
            add(f"C6_{o['role']}_inside_wall", False, "DIMENSION_MISMATCH", o["global_id"],
                f"opening span {g['offset_x_m']}+{g['width_m']} m > wall length {geo['length_m']} m")
        if sw is not None:
            add(f"C7_{o['role']}_width", abs(sw - g["width_m"]) <= tol, "DIMENSION_MISMATCH",
                o["global_id"], f"semantic void={sw} geometry={g['width_m']}")
    add("C8_height_envelope", geo["height_m"] <= ENVELOPE["max_wall_height_m"], "ENVELOPE_VIOLATION",
        w["global_id"], f"height={geo['height_m']} limit={ENVELOPE['max_wall_height_m']}")
    add("C9_min_thickness", geo["thickness_m"] >= ENVELOPE["min_thickness_m"], "ENVELOPE_VIOLATION",
        w["global_id"], f"thickness={geo['thickness_m']} min={ENVELOPE['min_thickness_m']}")
    boards = int(np.ceil(geo["length_m"] / ENVELOPE["max_board_width_m"])) if geo["length_m"] > 0 else 0
    return {"semantic_job": semantic, "geometry_extents": geo, "envelope": ENVELOPE,
            "board_layout": {"boards_required": boards, "board_width_m": ENVELOPE["max_board_width_m"]},
            "symbolic_checks": checks}


# --- Stage 3 -----------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a verification gate between an openBIM (ifcOWL/IFC) model and a ROS/Gazebo robotic "
    "fabrication cell. Compare the SEMANTIC job (designer intent) with the GEOMETRY extents that were "
    "computed deterministically from BREP vertices. Never recompute coordinates; reason only over the "
    "numbers given. Classify every discrepancy into exactly one category: MISSING_OPENING, "
    "DIMENSION_MISMATCH, UNIT_OR_SCALE_ERROR, ID_LINEAGE_CORRUPTION, ENVELOPE_VIOLATION. Approve only "
    "if the payload is complete, dimensionally faithful and inside the robot envelope. Respond only by "
    "calling the tool submit_verification_verdict.")


def stage3_llm(context: dict, offline: bool) -> tuple[Optional[VerificationVerdict], dict]:
    meta = {"mode": "offline", "latency_ms": 0.0, "input_tokens": 0, "output_tokens": 0}
    if offline or not os.environ.get("ANTHROPIC_API_KEY"):
        return None, meta
    import anthropic                                         # pip install anthropic
    client = anthropic.Anthropic()
    tool = {"name": "submit_verification_verdict",
            "description": "Return the structured verification verdict.",
            "input_schema": VerificationVerdict.model_json_schema()}
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=MODEL, max_tokens=1500, system=SYSTEM_PROMPT, tools=[tool],
        tool_choice={"type": "tool", "name": "submit_verification_verdict"},
        messages=[{"role": "user", "content": json.dumps(context, indent=1)}])
    meta.update(mode=MODEL, latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                input_tokens=msg.usage.input_tokens, output_tokens=msg.usage.output_tokens)
    block = next(b for b in msg.content if b.type == "tool_use")
    return VerificationVerdict.model_validate(block.input), meta   # schema enforced here


# --- Stage 4 -----------------------------------------------------------------
def write_verified_sdf(geo: dict, path: Path) -> int:
    """Approved path: wall split into solid boxes around every opening (x-z elevation)."""
    L, H, T = geo["length_m"], geo["height_m"], geo["thickness_m"]
    ops = sorted(geo["openings"].values(), key=lambda o: o["offset_x_m"])
    boxes, x = [], 0.0
    for o in ops:
        x0, x1 = o["offset_x_m"], o["offset_x_m"] + o["width_m"]
        z0, z1 = o["sill_m"], o["sill_m"] + o["height_m"]
        if x0 > x: boxes.append((x, x0, 0, H))
        if z0 > 0: boxes.append((x0, x1, 0, z0))
        if z1 < H: boxes.append((x0, x1, z1, H))
        x = x1
    if x < L: boxes.append((x, L, 0, H))
    links = []
    for i, (a, b, c, d) in enumerate(boxes):
        size = f"{b - a:.4f} {T:.4f} {d - c:.4f}"
        links.append(f'    <link name="seg_{i}"><pose>{(a + b) / 2:.4f} 0 {(c + d) / 2:.4f} 0 0 0</pose>'
                     f'<collision name="c"><geometry><box><size>{size}</size></box></geometry></collision>'
                     f'<visual name="v"><geometry><box><size>{size}</size></box></geometry></visual></link>')
    path.write_text('<?xml version="1.0"?>\n<sdf version="1.7">\n  <model name="fabricated_component">\n'
                    "    <static>true</static>\n" + "\n".join(links) + "\n  </model>\n</sdf>\n")
    return len(boxes)


def run_gate(semantic: dict, payload: dict, offline: bool = False, quiet: bool = False, write: bool = True):
    p = (lambda *a, **k: None) if quiet else print
    t0 = time.perf_counter()
    if not quiet: banner("STAGE 1 | Deterministic vertex bounding-box computation")
    geo = stage1_bbox(payload)
    p(f"vertices={geo['vertex_count']}  dX={geo['delta_x']}  dY={geo['delta_y']}  dZ={geo['delta_z']} (m)")
    p(f"-> length={geo['length_m']}  height={geo['height_m']}  thickness={geo['thickness_m']}")
    for r, o in geo["openings"].items():
        p(f"   {r:<14} w={o['width_m']} h={o['height_m']} offset_x={o['offset_x_m']} sill={o['sill_m']}")

    if not quiet: banner("STAGE 2 | Context & constraint assembly (symbolic pre-checks)")
    ctx = stage2_context(semantic, payload, geo)
    for c in ctx["symbolic_checks"]:
        p(f"[{c['result']}] {c['id']:<28} {c['evidence']}" + (f"  => {c['category']}" if c["category"] else ""))
    p(f"board layout: {ctx['board_layout']['boards_required']} x {ENVELOPE['max_board_width_m']} m boards")
    t_sym = (time.perf_counter() - t0) * 1000

    if not quiet: banner("STAGE 3 | Schema-enforced semantic inference (Claude tool use)")
    verdict, meta = stage3_llm(ctx, offline)
    hard_fail = [c for c in ctx["symbolic_checks"] if c["result"] == "FAIL"]
    if verdict is None:
        p("LLM call skipped (offline / no ANTHROPIC_API_KEY) -> verdict from symbolic checks only")
        verdict = VerificationVerdict(
            is_approved_for_ros=not hard_fail,
            findings=[Finding(category=c["category"], element_global_id=c["element_global_id"],
                              evidence=c["evidence"], severity="BLOCKING") for c in hard_fail],
            status_message=("Payload verified." if not hard_fail else
                            f"{len(hard_fail)} blocking discrepancy(ies) between semantic job and geometry; "
                            "re-export IFC or correct the serialiser before fabrication."))
    else:
        p(f"model={meta['mode']} latency={meta['latency_ms']} ms tokens in/out="
          f"{meta['input_tokens']}/{meta['output_tokens']}")
    p(json.dumps(verdict.model_dump(mode="json"), indent=2))

    if not quiet: banner("STAGE 4 | Deterministic routing & ROS gating")
    approved = verdict.is_approved_for_ros and not hard_fail        # fail-safe AND
    report = {"approved": approved, "verdict": verdict.model_dump(mode="json"), "llm_meta": meta,
              "symbolic_latency_ms": round(t_sym, 2), "geometry_extents": geo}
    if write:
        (OUT / "llm_gate_report.json").write_text(json.dumps(report, indent=2))
    if approved:
        n = write_verified_sdf(geo, OUT / "fabricated_component.sdf") if write else 0
        p(f"APPROVED -> fabricated_component.sdf ({n} wall segments) -> merge_bim_ros.py / Gazebo spawn")
    else:
        p("BLOCKED  -> llm_gate_report.json written to WebServer Status Message; exit(1)")
    return approved, report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--semantic", default=str(OUT / "cut_job_semantic.json"))
    ap.add_argument("--payload", default=str(OUT / "ros_fabrication_payload.json"))
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    print("=" * 72 + "\n SYSTEM B | claude_verification_gate.py\n" + "=" * 72)
    ok, _ = run_gate(json.loads(Path(a.semantic).read_text()),
                     json.loads(Path(a.payload).read_text()), offline=a.offline)
    sys.exit(0 if ok else 1)
