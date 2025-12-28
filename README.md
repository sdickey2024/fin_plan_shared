# fin_plan

A Python-based retirement and financial planning simulator with scenario modeling, Monte Carlo analysis, and both CLI and GUI front‑ends.

`fin_plan` is designed for iterative exploration: you define a **base financial profile**, apply one or more **scenario files** (market crashes, inflation shocks, long‑term care, etc.), and run deterministic or Monte Carlo simulations to understand outcomes over time.

The project emphasizes:
- Clear, explicit JSON schemas (no guessing or heuristics)
- Reproducible simulations
- Strong validation and regression testing
- Separation between real user data and example/demo data

---

## Features

- **Base vs Scenario modeling**
  - Base files describe a complete financial profile
  - Scenario files describe changes over time (life events, assumption shifts)

- **Monte Carlo modes**
  - Deterministic (off)
  - Simulation-based
  - Event-driven
  - Forced Monte Carlo

- **Multiple execution paths**
  - Command-line interface for batch runs
  - Qt-based GUI for interactive exploration

- **Validation & regression testing**
  - Schema and structural validation
  - Runtime smoke tests
  - Fully automated test runner

---

## Project Layout

```
fin_plan/
├── data/
│   ├── user_base/        # Base user profiles (schema_type: user_base)
│   ├── scenarios/        # Scenario definitions (schema_type: scenario)
│   └── normalize.py
├── engine/               # Core simulation and validation logic
├── gui_qt/               # Qt GUI implementation
├── validations/          # Regression and runtime validation tests
├── out/                  # Generated outputs (CSV, PNG)
├── run_all_simulations.py
├── run_validations.sh
└── README.md
```

---

## Requirements

- Python 3.10+ (recommended)
- Linux (primary development platform)
- Required Python packages (see project imports):
  - matplotlib
  - numpy
  - PySide6 (for GUI)

Using a virtual environment is strongly recommended.

---

## Quick Start

This section is intended for Python users who want to get up and running quickly.

### 1. Clone the repository

```bash
git clone <repo-url>
cd fin_plan
```

### 2. Create and activate a virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see your shell prompt change to indicate the virtual environment is active.

### 3. Install required Python packages

`fin_plan` does not yet ship with a frozen `requirements.txt`, but the expected dependency set is:

```bash
pip install \
  pyfolio-reloaded \
  quantstats \
  matplotlib \
  pandas \
  jsonschema \
  pydantic \
  typer \
  argparse \
  plotly
```

These cover:
- portfolio and performance analysis
- plotting and visualization
- structured data validation
- CLI argument handling

> **Note**: `argparse` is part of the Python standard library, but is listed here for clarity.

### 4. Verify installation

Run a simple smoke test:

```bash
python run_all_simulations.py --user=example_user.json --file=scenario_base_retirement_.json
```

If this completes and writes output to `out/`, your environment is correctly set up.

---

## Installation

For users who prefer a more explicit setup process, the steps above are equivalent to:

```bash
git clone <repo-url>
cd fin_plan
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # if present
```

If no `requirements.txt` is present, install dependencies manually as described in **Quick Start**.

---

## Data Model Overview

### Base Files (`schema_type: user_base`)

Base files define the full financial state of a user:

- Personal information (age or birthdate)
- Expenses and income
- Portfolio composition
- Default assumptions
- Life events baseline

Example:
```json
{
  "schema_type": "user_base",
  "schema_version": 1,
  "person": { ... },
  "expenses": { ... },
  "income": { ... },
  "portfolio": { ... },
  "assumptions": { ... }
}
```

### Scenario Files (`schema_type: scenario`)

Scenario files describe **changes over time** applied on top of a base:

- Market shocks
- Inflation changes
- Policy or spending changes
- Long-term care events

Example:
```json
{
  "schema_type": "scenario",
  "schema_version": 1,
  "description": "Market crash at retirement",
  "life_events": [ ... ]
}
```

The declared `schema_type` is authoritative; validators never infer file roles.

---

## Command-Line Usage

### Basic run

```bash
python run_all_simulations.py \
  --user=example_user.json \
  --file=scenario_base_retirement_.json
```

### Multiple scenarios in one run

```bash
python run_all_simulations.py \
  --user=example_user.json \
  --file=scenario_1_market_crash.json \
  --file=scenario_long_term_care.json
```

### Monte Carlo modes

```bash
--montecarlo off      # deterministic
--montecarlo sim      # Monte Carlo on returns
--montecarlo events   # Monte Carlo on events
--montecarlo force    # Force Monte Carlo everywhere
```

### Parallel execution

```bash
python run_all_simulations.py \
  --user=example_user.json \
  --file=scenario_1_market_crash.json \
  --file=scenario_long_term_care.json \
  --jobs 2
```

Outputs are written to the `out/` directory.

---

## GUI Usage

Launch the Qt GUI:

```bash
python3 -m gui_qt.main
```

From the GUI you can:
- Open base files from `data/user_base/`
- Open and select scenarios from `data/scenarios/`
- Run simulations interactively
- View generated graphs and output files

Note: Editing JSON structures via the tree view is currently limited; complex edits (such as adding new life events) are best done in a text editor.

---

## Validation & Testing

### Schema and structural validation

Run all validators and runtime smoke tests:

```bash
./run_validations.sh
```

This performs:
1. JSON schema and structural validation
2. Runtime execution smoke tests (CLI)

Validation scripts live in:

```
validations/
├── validate_regressions.py
└── run_smoke_sims.py
```

These tests are designed to catch regressions without modifying production code.

---

## Philosophy

`fin_plan` is intentionally conservative in design:

- Explicit schemas over inference
- Validation before execution
- Separation of real user data from example/demo data
- Reproducibility over convenience

The goal is not just to "run simulations", but to **trust the results**.

---

## Status

Active development. APIs and file formats may evolve, but changes are gated by validation and regression tests.

Contributions, experimentation, and careful refactoring are encouraged.

