# Quick Start

This is the fastest way to install and run `fin_plan` on a fresh machine.

## 1) Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 2) Install dependencies

Install runtime dependencies:

```bash
pip install -r requirements.txt
```

Optional (docs + tooling):

```bash
pip install -r requirements-dev.txt
```

## 3) Run a command-line simulation

```bash
python run_all_simulations.py --user=example_user.json --file=scenario_base_retirement_.json
```

Outputs are written under:

```text
out/
```

## 4) Launch the GUI

```bash
python gui_qt/main.py
```

## 5) Run validations

This runs schema checks + runtime smoke tests:

```bash
./run_validations.sh
```

## Notes

- Base files live in `data/user_base/` and must declare:
  - `"schema_type": "user_base"`
- Scenarios live in `data/scenarios/` and must declare:
  - `"schema_type": "scenario"`
```
