"""
measure_latency.py  --  repeated in-process latency measurement (Dissertation Section 4.7.3, Appendix D.3)

Times System A (json_to_sdf_converter.convert) and the symbolic layer of System B
(Stages 1, 2 and 4 of claude_verification_gate.run_gate, offline) on every test case
T01-T10, repeating each call N times (default 50) with time.perf_counter and
reporting the mean per case and over all cases.

Run after steps 01-03 have written output/cut_job_semantic.json and
output/ros_fabrication_payload.json:

  python evaluation/measure_latency.py   # 50 repetitions per case
  python evaluation/measure_latency.py --reps 200
"""
import argparse
import statistics
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))   # pipeline modules live in src/

import json_to_sdf_converter as system_a
from claude_verification_gate import run_gate
from run_dsr_evaluation import cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=50)
    reps = ap.parse_args().reps

    a_means, b_means = [], []
    print(f"{'case':<5} {'System A (ms)':>14} {'System B symbolic (ms)':>24}   (mean of {reps} runs)")
    for cid, _desc, _valid, sem, geo in cases():
        ta, tb = [], []
        for _ in range(reps):
            t0 = time.perf_counter()
            system_a.convert(geo)
            ta.append((time.perf_counter() - t0) * 1000)
            _ok, rep = run_gate(sem, geo, offline=True, quiet=True, write=False)
            tb.append(rep["symbolic_latency_ms"])
        a_means.append(statistics.mean(ta))
        b_means.append(statistics.mean(tb))
        print(f"{cid:<5} {a_means[-1]:>14.4f} {b_means[-1]:>24.4f}")
    print(f"\nmean over cases: System A {statistics.mean(a_means):.4f} ms | "
          f"System B symbolic {statistics.mean(b_means):.4f} ms | "
          f"overhead {statistics.mean(b_means) - statistics.mean(a_means):.4f} ms")


if __name__ == "__main__":
    main()
