# PRBD Automated Drainage Design System

Automated drainage pipe routing system for multi-storey prefab residential buildings, based on BIM (Building Information Modeling) methodology.

## Features

- **Automated Pipe Routing** — A\* pathfinding algorithm for shortest drainage pipe paths, accounting for slope, joist constraints, and floor obstacles
- **Vent Pipe Design** — 3 scenarios (Individual / Single Common / Shared Sink)
- **Cross-Storey Routing** — Automatic optimal riser position selection on walls (perimeter + partition), window avoidance via zigzag
- **Panelization** — Cut pipes at panel boundaries, insert couplings, generate per-panel BOM
- **Pipe Cutting Optimization** — 1D Cutting Stock Problem (CSP) solver to minimize material waste
- **3D Visualization** — Render entire multi-storey building with walls, floors, doors, windows, fixtures, and pipes

## Project Structure

```
MEP auto-routing/
├── src/                         # Source code
│   ├── main.py                  #   Entry point & CLI (argparse)
│   ├── models.py                #   Data models (XYZ, Wall, Pipe, Fixture, Panel, ...)
│   ├── pathfinding.py           #   Algorithm 1: A* Heuristic Pathfinding
│   ├── vent_design.py           #   Vent pipe design (3 scenarios)
│   ├── panelization.py          #   Algorithm 2: Panelization (cut at panel boundaries)
│   ├── cutting_optimization.py  #   Algorithm 3: 1D-CSP Cutting Optimization
│   ├── pipeline.py              #   4-step pipeline orchestrator
│   └── visualizer.py            #   3D visualization with matplotlib
├── input_dir/                   # Input building models (JSON)
│   ├── model_complex_obstacles.json
│   ├── model_default.json
│   ├── model_large_building.json
│   ├── model_single_storey.json
│   └── model_two_fixtures.json
├── output_dir/                  # Output logs (auto-generated)
├── docs/                        # Documentation
│   ├── architecture.md          #   System architecture & detailed code flow
│   ├── algorithm.md             #   Algorithm descriptions (A*, CSP, panelization)
│   ├── methodology.md           #   Research methodology
│   └── summary.md               #   Original paper summary
├── requirements.txt             # Dependencies
├── .gitignore
└── README.md
```

## Documentation

| File | Description |
|------|-------------|
| [docs/architecture.md](docs/architecture.md) | System architecture diagrams, detailed module flow, inter-module relationships, key mathematical formulas |
| [docs/algorithm.md](docs/algorithm.md) | Detailed algorithm descriptions: A\* pathfinding, 1D Cutting Stock Problem, panelization |
| [docs/methodology.md](docs/methodology.md) | Research methodology, PRBD design process |
| [docs/summary.md](docs/summary.md) | Summary of the original paper on automated drainage system design for panelized residential buildings |

## Requirements

- Python 3.11+
- See [requirements.txt](requirements.txt) for full dependencies

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
cd src

# List available models
python main.py --list-models

# Run a specific model by number
python main.py --model 2

# Run without 3D visualization
python main.py --model 2 --no-viz

# Save output to output_dir
python main.py --model 2 --output-dir ../output_dir --no-viz

# Run all models at once
python main.py --run-all --no-viz

# Default (no args) runs model #1
python main.py
```

### Available Models

| # | File | Description |
|---|------|-------------|
| 1 | `model_complex_obstacles.json` | 3-storey, many floor openings + window overrides forcing zigzag riser |
| 2 | `model_default.json` | 3-storey, single toilet L3→L1 (original demo) |
| 3 | `model_large_building.json` | 5-storey, larger footprint (7200×5400) |
| 4 | `model_single_storey.json` | 1-storey, horizontal routing only |
| 5 | `model_two_fixtures.json` | 3-storey, toilet on L3 + sink on L2 |

### CLI Options

| Flag | Description |
|------|-------------|
| `--model N` / `-m N` | Run model number N (see `--list-models`) |
| `--list-models` | List all models in `input_dir/` with indices |
| `--run-all` | Run all models sequentially |
| `--output-dir PATH` / `-o PATH` | Save terminal output to a log file in the given directory |
| `--no-viz` | Skip 3D matplotlib visualization |
| `--input-dir PATH` | Custom input directory (default: `input_dir/`) |

### What Happens

1. Load building model from `input_dir/*.json`
2. Select optimal riser position on wall
3. Horizontal routing on top floor: fixture → riser (avoiding floor openings)
4. Vertical riser down to L1 (avoiding windows via zigzag)
5. Horizontal routing on L1: riser → main stack
6. 3D visualization (unless `--no-viz`)

## 4-Step Pipeline

| Step | Module | Description |
|------|--------|-------------|
| 1 | `vent_design.py` | Vent pipe design by scenario |
| 2 | `pathfinding.py` | Drainage pipe routing (A\*) |
| 3 | `panelization.py` | Cut pipes at panel boundaries + BOM |
| 4 | `cutting_optimization.py` | Standard pipe cutting optimization (1D-CSP) |

## Key Algorithms

### A\* Pathfinding

$$f(n) = g(n) + h(n) + t(n)$$

- $g(n)$: cumulative pipe length from start
- $h(n)$: Manhattan distance to terminal
- $t(n)$: turn count × grid\_size (direction change penalty)

### Riser Position Selection

$$cost = |f_x - r_x| + |f_y - r_y| + |s_x - r_x| + |s_y - r_y|$$

Scans all walls (perimeter + partition), skips positions blocked by doors/windows/floor openings, selects the point with the lowest total cost.

### 1D Cutting Stock Problem

$$\min \sum_{i} N_i \times w_i \quad \text{where } w_i = L_{standard} - \sum_{j} n_{ij} \times l_j$$

See [docs/architecture.md](docs/architecture.md) for detailed flow diagrams.
