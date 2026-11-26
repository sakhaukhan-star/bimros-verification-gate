"""
run_dsr_evaluation.py  --  DSRM Activity 5 (Evaluation)
A/B fault-injection benchmark: 2 clean + 8 mutated payload pairs derived from
the BIMROS.ifc ground truth, executed through System A (baseline converter)
and System B (verification gate).

  python evaluation/run_dsr_evaluation.py --offline    # System B symbolic layer only
  python evaluation/run_dsr_evaluation.py   # System B with Claude (needs ANTHROPIC_API_KEY)
"""
import argparse
import copy
import csv
import json
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # pipeline modules live in src/

import numpy as np

import json_to_sdf_converter as system_a
from claude_verification_gate import run_gate

OUT = Path(__file__).resolve().parents[1] / "output"   # <repo>/output
SEM = json.loads((OUT / "cut_job_semantic.json").read_text())
GEO = json.loads((OUT / "ros_fabrication_payload.json").read_text())


def scale_bbox_x(o, factor):
    mn, mx = o["bbox"]["min"], o["bbox"]["max"]
    mx[0] = mn[0] + (mx[0] - mn[0]) * factor


def cases():
    s, g = copy.deepcopy, copy.deepcopy
    out = []
    out.append(("T01", "Clean reference payload", True, s(SEM), g(GEO)))
    # T02: same model re-serialised (vertex order shuffled, rigid +10 m translation)
    p = g(GEO); v = np.array(p["wall"]["vertices"]); np.random.default_rng(7).shuffle(v)
    v[:, 0] += 10.0; p["wall"]["vertices"] = v.round(4).tolist()
    for o in p["openings"].values():
        o["bbox"]["min"][0] += 10.0; o["bbox"]["max"][0] += 10.0
    out.append(("T02", "Clean, re-serialised (shuffled + translated)", True, s(SEM), p))
    # T03: empirical baseline defect: window dropped + GlobalId l->1 mutation
    p = g(GEO); p["openings"].pop("WindowOpening")
    p["openings"]["DoorOpening"]["global_id"] = p["openings"]["DoorOpening"]["global_id"].replace("l", "1")
    out.append(("T03", "Window omitted + GlobalId l/1 mutation", False, s(SEM), p))
    p = g(GEO); scale_bbox_x(p["openings"]["DoorOpening"], 1000)
    out.append(("T04", "Unit drift: door width in mm", False, s(SEM), p))
    sm, p = s(SEM), g(GEO); v = np.array(p["wall"]["vertices"]); z0 = v[:, 2].min()
    v[:, 2] = z0 + (v[:, 2] - z0) * (5.5 / 3.2004); p["wall"]["vertices"] = v.round(4).tolist()
    sm["wall"]["height_m"] = 5.5
    out.append(("T05", "Envelope violation: height 5.50 m", False, sm, p))
    p = g(GEO); p["openings"].pop("DoorOpening")
    out.append(("T06", "Primary (door) opening omitted", False, s(SEM), p))
    p = g(GEO); p["element_global_id"] = p["element_global_id"].replace("I", "1")
    out.append(("T07", "Wall GlobalId corrupted (I/1)", False, s(SEM), p))
    p = g(GEO); v = np.array(p["wall"]["vertices"]); v[:, 1] = 0.0; p["wall"]["vertices"] = v.tolist()
    out.append(("T08", "Degenerate zero-thickness geometry", False, s(SEM), p))
    sm = s(SEM); extra = copy.deepcopy(sm["openings"][0]); extra.update(role="ServiceOpening",
                                                                         global_id="3XtraOpen1ngGl0balId00")
    sm["openings"].append(extra); sm["opening_count"] = 3
    out.append(("T09", "Semantic count mismatch (3rd opening)", False, sm, g(GEO)))
    p = g(GEO); d = p["openings"]["DoorOpening"]; d["bbox"]["max"][0] = d["bbox"]["min"][0] + 8.5
    out.append(("T10", "Topological impossibility: door 8.50 m", False, s(SEM), p))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--offline", action="store_true"); a = ap.parse_args()
    rows = []
    print(f"{'case':<5}{'description':<44}{'valid':<7}{'A: exit/SDF':<13}{'B: verdict':<10} categories")
    for cid, desc, valid, sem, geo in cases():
        t = time.perf_counter(); sdf, _ = system_a.convert(geo); ta = (time.perf_counter() - t) * 1000
        approved, rep = run_gate(sem, geo, offline=a.offline, quiet=True, write=False)
        cats = sorted({f["category"] for f in rep["verdict"]["findings"]})
        rows.append({"case": cid, "description": desc, "ground_truth_valid": valid,
                     "A_blocked": False, "A_latency_ms": round(ta, 3),
                     "B_blocked": not approved, "B_categories": ";".join(cats),
                     "B_symbolic_ms": rep["symbolic_latency_ms"], "B_llm_ms": rep["llm_meta"]["latency_ms"],
                     "B_tokens_in": rep["llm_meta"]["input_tokens"], "B_tokens_out": rep["llm_meta"]["output_tokens"]})
        print(f"{cid:<5}{desc:<44}{str(valid):<7}{'0 / written':<13}{'BLOCK' if not approved else 'PASS':<10} "
              f"{', '.join(cats) or '-'}")
    faulty = [r for r in rows if not r["ground_truth_valid"]]
    clean = [r for r in rows if r["ground_truth_valid"]]
    for sysname in ("A", "B"):
        rec = sum(r[f"{sysname}_blocked"] for r in faulty)
        fr = sum(r[f"{sysname}_blocked"] for r in clean)
        print(f"System {sysname}: fault interception {rec}/{len(faulty)} = {100 * rec / len(faulty):.1f}%  | "
              f"false rejection {fr}/{len(clean)} = {100 * fr / len(clean):.1f}%")
    with open(OUT / "dsr_evaluation_results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(f"results -> {OUT / 'dsr_evaluation_results.csv'}")
