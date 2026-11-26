# BIMROS Verification Gate

**A neuro-symbolic LLM verification gate that stops silent data loss between IFC geometry and ROS/Gazebo in openBIM robotic prefabrication.**

This repository contains the software artefact, test data generator and evidence for the MSc dissertation
*"Preventing Silent Data Loss in BIM-Based Digital Fabrication Using ROS: A Design Science Study of a Neuro-Symbolic Verification Gate for Robotic Gypsum Board Cutting"*
(Sakha Ullah Khan, MSc Construction Project Management, University of Greenwich, 2026). It is the Communication output (DSRM Activity 6) of the study.

---

## The problem

In a BIM-to-ROS pipeline (modelled on buildingSMART Use Case 3088), an IFC model is queried, tessellated and
converted into a Gazebo SDF file. The rule-based converter at the end checks only that it can write a file. On the
case-study wall it reported **SUCCESS (exit code 0)** while writing a wall of the wrong size, with **no window opening**
and a collapsed segment.

| Failure mode | What happened |
|---|---|
| (i) Opening omitted | The window opening `25q0F7Cega_$0LrQe2CMgO` was dropped |
| (ii) Dimensions overwritten | 5.6388 × 3.2004 × 0.1143 m replaced by a hard-coded 3.5 × 2.8 × 0.2 m |
| (iii) Silent exception | A missing key was swallowed and defaults were used |
| (iv) GlobalId corruption | Look-alike character swaps (l→1, I→1) break traceability |

## The solution: a four-stage gate

`src/claude_verification_gate.py` sits after geometry extraction and before SDF conversion.

| Stage | Type | What it does |
|---|---|---|
| 1 Bounding box | Symbolic | Computes wall and opening extents from the BREP vertices (no LLM arithmetic) |
| 2 Pre-checks | Symbolic | Runs nine rules (C1–C9) comparing the semantic job with the geometry; each failure carries a fault category and GlobalId |
| 3 Inference | Neural | Claude returns a `VerificationVerdict` through forced tool use, validated by Pydantic |
| 4 Routing | Symbolic | Approves only if the LLM **and** all rules approve (fail-safe AND); otherwise writes `llm_gate_report.json` and exits with code 1 |

Fault taxonomy: `MISSING_OPENING`, `DIMENSION_MISMATCH`, `UNIT_OR_SCALE_ERROR`, `ID_LINEAGE_CORRUPTION`, `ENVELOPE_VIOLATION`.

---

## Repository structure

```
bimros-verification-gate/
├── data/
│   └── BIMROS.ifc                    # case-study model (Revit 2027 export, IFC2X2 header, feet)
├── src/                              # the pipeline and the artefact
│   ├── bimros_common.py              # shared helpers: IFC2X2 header normalisation, units, JSON I/O
│   ├── 01_ifc_inventory.py           # Step 01 - model inventory            (Result 1)
│   ├── 02_extract_semantic.py        # Step 02 - semantic job               (Result 3)
│   ├── 03_extract_geometry.py        # Step 03 - geometry payload           (Result 3)
│   ├── json_to_sdf_converter.py      # System A - non-LLM baseline converter (Result 4)
│   └── claude_verification_gate.py   # System B - the four-stage verification gate
├── evaluation/                       # DSRM Activity 5
│   ├── run_dsr_evaluation.py         # generates T01-T10 and runs the A/B benchmark
│   ├── export_cases.py               # writes T01-T10 to output/ for single-case runs
│   └── measure_latency.py            # repeated in-process latency measurement
├── tools/                            # figure scripts
│   ├── plot_elevations.py            # Figure A.1 - ground truth vs System A
│   └── plot_sdf_3d.py                # Figure C.5 - 3D plot of the T01 SDF files
├── sparql/
│   └── globalids.rq                  # SPARQL query for GlobalId lineage (Result 2)
├── results/                          # evidence behind Chapters 3 and 4 (see results/README.md)
│   ├── ch3_problem_identification/   # logs of Results 1-4, semantic job, payload, System A SDF
│   ├── ch4_demonstration/            # T01 and T03 gate output, System B SDF, live Claude runs
│   ├── ch4_evaluation/               # T01-T10 test cases, gate output, benchmark log and CSV
│   └── figures/                      # Gazebo Fuel screenshots and generated plots
├── README.md · LICENSE · CITATION.cff · requirements.txt · .gitignore
```

## Where is the evidence for each part of the dissertation?

| Dissertation | Evidence in this repository |
|---|---|
| Ch. 3.4 Results 1-4 (audit of the non-LLM pipeline) | `results/ch3_problem_identification/` |
| Ch. 3.4 Result 2 (GlobalId reference) | `sparql/globalids.rq` |
| Ch. 3.6 Design of the gate | `src/claude_verification_gate.py` |
| Ch. 4.2-4.3 Demonstration on T01 and T03 | `results/ch4_demonstration/gate_output/` |
| Ch. 4.4 Live Claude runs | `results/ch4_demonstration/llm_live_runs/` |
| Ch. 4.5 Evaluation over T01-T10 | `results/ch4_evaluation/` |
| Ch. 4.5.3 Latency and cost | `evaluation/measure_latency.py`, `results/ch4_evaluation/dsr_evaluation_results.csv` |
| Figures A.1, C.5, 3.8-3.9, 4.2 | `tools/`, `results/figures/` |

---

## Requirements

- Python 3.10 or later (developed with 3.13)
- `ifcopenshell` 0.9, `numpy`, `pydantic` 2, `anthropic` (only for the live LLM mode), `matplotlib`
- Optional: Apache Jena, to run `sparql/globalids.rq` against an ifcOWL conversion of the model

```bash
pip install -r requirements.txt
```

## Quick start (reproduces every result in Chapters 3 and 4)

Run every command from the repository root. All outputs are written to `./output` (ignored by git).

```bash
python src/01_ifc_inventory.py data/BIMROS.ifc       # Result 1: schema, units, two openings
python src/02_extract_semantic.py data/BIMROS.ifc    # Result 3: semantic job
python src/03_extract_geometry.py data/BIMROS.ifc    # Result 3: 24-vertex geometry payload
python src/json_to_sdf_converter.py                  # Result 4: System A, exit 0 but wrong SDF
python src/claude_verification_gate.py --offline     # System B on the clean payload: APPROVED
python evaluation/run_dsr_evaluation.py --offline    # A/B benchmark over T01-T10
python evaluation/export_cases.py                    # write T01-T10 to output/ as JSON files
python evaluation/measure_latency.py                 # mean latency over 50 runs per case
python tools/plot_elevations.py                      # Figure A.1
python tools/plot_sdf_3d.py                          # Figure C.5
```

Run the gate on a single case, for example the faulty case T03:

```bash
python src/claude_verification_gate.py --offline --semantic output/T03_semantic.json --payload output/T03_payload.json
echo $?        # Linux/macOS (Windows PowerShell: echo $LASTEXITCODE)  ->  0 = approved, 1 = blocked
```

### Live LLM mode (Stage 3 with Claude)

```bash
# Linux/macOS
export ANTHROPIC_API_KEY="sk-ant-..."
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

python src/claude_verification_gate.py           # without --offline
```

The model defaults to `claude-sonnet-4-6`. Set `GATE_MODEL` to use another model. Without an API key the gate falls
back to offline mode automatically. **Never commit your API key.**

### Note on the IFC schema

Revit exported `BIMROS.ifc` with an `IFC2X2_FINAL` header, which current IfcOpenShell releases reject.
`bimros_common.open_ifc()` rewrites the header to `IFC2X3` in a temporary copy and logs both schemas. This is safe
for this model because every entity it contains has the same definition in IFC2X3. A native IFC2x3 or IFC4 export
avoids the step.

---

## Results (offline benchmark, T01–T10)

| Case | Ground truth | Fault injected | System A | System B | Categories reported |
|---|---|---|---|---|---|
| T01 | Valid | None | exit 0, SDF written | **Approved** | – |
| T02 | Valid | Vertices shuffled, wall moved +10 m | exit 0, SDF written | **Approved** | – |
| T03 | Faulty | Window removed + door GlobalId l→1 | exit 0, SDF written | **Blocked** | MISSING_OPENING, ID_LINEAGE_CORRUPTION |
| T04 | Faulty | Door width in mm | exit 0, SDF written | **Blocked** | UNIT_OR_SCALE_ERROR, DIMENSION_MISMATCH |
| T05 | Faulty | Wall height 5.50 m | exit 0, SDF written | **Blocked** | ENVELOPE_VIOLATION |
| T06 | Faulty | Door opening removed | exit 0, SDF written | **Blocked** | MISSING_OPENING |
| T07 | Faulty | Wall GlobalId I→1 | exit 0, SDF written | **Blocked** | ID_LINEAGE_CORRUPTION |
| T08 | Faulty | Zero-thickness wall | exit 0, SDF written | **Blocked** | ENVELOPE_VIOLATION, DIMENSION_MISMATCH |
| T09 | Faulty | Extra opening in semantic job | exit 0, SDF written | **Blocked** | MISSING_OPENING |
| T10 | Faulty | Door 8.50 m wide | exit 0, SDF written | **Blocked** | DIMENSION_MISMATCH |

| Metric | System A (baseline) | System B (gate) |
|---|---|---|
| Fault detection rate | 0% (0/8) | **100% (8/8)** |
| False rejection rate | 0% (0/2) | **0% (0/2)** |
| Diagnostic precision | not defined | **100% (8/8)** |
| Mean latency | 0.018 ms | 0.064 ms symbolic (+0.046 ms) |
| Cost per wall | USD 0 | USD 0 offline; ≈ USD 0.016 with Claude Sonnet 4.6 (estimated) |

The live Claude verdicts for T01 (approved) and T03 (blocked) agreed with the symbolic rules. They are in
`results/ch4_demonstration/llm_live_runs/`. Limitations: one wall, synthetic faults, and the LLM was run live on two cases through the
chat interface, so its latency and exact token use were not measured.

---

## How to cite

```
Khan, S.U. (2026) Preventing Silent Data Loss in BIM-Based Digital Fabrication Using ROS: A Design Science
Study of a Neuro-Symbolic Verification Gate for Robotic Gypsum Board Cutting. MSc dissertation. London:
University of Greenwich. Software available at: https://github.com/sakhaukhan-star/bimros-verification-gate
```

See also `CITATION.cff`.

## Licence

Released under the MIT Licence (see `LICENSE`). The case-study model `data/BIMROS.ifc` was authored by the author for
this study.

## Acknowledgements

The pipeline follows the buildingSMART BIM-ROS Integration use case (Use Case 3088). It uses IfcOpenShell,
Pydantic, Apache Jena and Anthropic's Claude API.
