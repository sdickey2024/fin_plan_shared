# fin_plan
**Retirement & Financial Scenario Simulator**

Version **1.0.0**

---

## Quick Start

`fin_plan` simulates long-term financial outcomes by combining:

- A **Base File** (your personal financial profile)
- One or more **Scenario Files** (external events and risks)

### Prerequisites

- Python **3.10+** recommended
- Linux is the primary development platform
- Use of a **virtual environment (venv)** is strongly encouraged

### Installation (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional (docs and tooling):

```bash
pip install -r requirements-dev.txt
```

### First Run (CLI)

```bash
python run_all_simulations.py \
  --user=example_user.json \
  --file=scenario_base_retirement_.json
```

Outputs will be written to the `out/` directory.

### GUI Launch

```bash
python gui_qt/main.py
```

---

## Typical Workflow

1. **Open a Base JSON** (from `data/user_base/`)
2. **Select one or more Scenario JSONs** (from `data/scenarios/`)
3. Choose run parameters:
   - **Granularity**: monthly / yearly
   - **Monte Carlo Mode**: off / sim / events / force
   - **Jobs**: parallel execution count
4. Click **Run Selected Scenarios**
5. Review results:
   - Graphs (auto-open after run; also available via **Open Graphs**)
   - CSV outputs in the output directory

---

## Basic Concepts

### Base vs Scenario

`fin_plan` enforces a strict separation of concerns:

> **User-specific data belongs in the Base file**  
> **External events and risks belong in Scenario files**

This keeps scenarios reusable, comparable, and independent of any one user.

This separation is enforced explicitly via JSON schema declarations:

- Base files must declare:
  ```json
  "schema_type": "user_base"
  ```
- Scenario files must declare:
  ```json
  "schema_type": "scenario"
  ```

The validator never guesses file intent; declared schema type is authoritative.

---

## Base Files (User Profile)

The Base file contains information that is personal, long-lived, and under the user’s control:

- **person**: identity and simulation horizon
- **income**: recurring income streams
- **expenses**: recurring expense breakdown and classification
- **portfolio**: current balances
- **assumptions**: default economic assumptions
- **life_events**: user-specific events (e.g., retirement)

### person

Defines the simulated individual and time horizon.

Common fields:

- `name`
- `birthdate` (preferred) or `current_age`
- `stop_age`

### income

All income streams are modeled as **monthly values**, unless explicitly documented otherwise.

Examples:

- salary
- pension
- social_security

Income can change over time via life events.

### expenses

Expenses are modeled as a monthly breakdown.

#### breakdown

`expenses.breakdown` is a flat dictionary of:

```
category -> monthly amount
```

#### classification (fixed vs discretionary)

Each expense category may be labeled:

- **fixed**: difficult to reduce (housing, insurance)
- **discretionary**: reducible or optional (travel, dining, subscriptions)

Unclassified categories default to **fixed**.

#### spending_policy (optional)

Spending policy controls **withdrawals**, not raw expenses.

Typical use cases:

- portfolio-based withdrawal caps
- priority ordering for discretionary categories

This allows stress scenarios to compress discretionary spending while preserving fixed obligations.

### portfolio

Portfolio balances are grouped by tax treatment:

- taxable
- non-taxable
- brokerage
- savings

The engine simulates the total portfolio while honoring configured withdrawal policies.

### assumptions

Baseline economic assumptions:

- `expected_return`
- `variance` (volatility)
- `inflation`

Assumptions may be overridden by life events or scenario files.

---

## Scenario Files (External Events)

Scenario files describe **external risks and shocks** and are intended to be generic and reusable.

Typical contents:

- `description`
- `life_events` representing risks or regime changes
- optional assumption overrides

Examples:

- market crash at retirement
- inflation spike
- historical worst-case decade
- long-term care costs

---

## Life Events

Life events represent state changes that occur at a specific time.

Events may modify:

- income (`updated_income`)
- expenses (`updated_expenses`)
- assumptions (`updated_assumptions`)

### Event Timing

Events can be scheduled using one of:

- `t_month` (months from simulation start)
- `t: { year, month }` (relative coordinates)
- `age` (converted internally to a month offset)
- legacy absolute `date` (converted to relative time)

#### Offsets (recommended)

Offsets are preferred because they remain valid when base assumptions change (e.g., retirement age).

Example:

```json
"offset": { "from": "Retirement", "years": 5, "months": 0 }
```

This means: **five years after the Retirement event**.

Event names must be unique so that offsets are unambiguous.

---

## Deterministic vs Monte Carlo

`fin_plan` supports multiple run modes via `--montecarlo`:

### Deterministic (`off` / `events`)

Deterministic mode runs a small set of fixed-return paths:

- **min**: expected_return − variance
- **expected**: expected_return
- **max**: expected_return + variance

This is useful for quick comparisons and for validating event logic.

### Monte Carlo (`sim`, `force`)

Monte Carlo modes sample per-step returns according to configured variance and produce percentile envelopes.

Monte Carlo runs still honor:

- life events
- spending policies
- inflation drift
- depletion logic

---

## Interpreting Results

Key signals to watch:

- **Depletion age**: if and when the portfolio reaches zero
- **Discretionary compression**: how much discretionary spend is funded under stress
- **Scenario divergence**: sensitivity to external shocks
- **Monte Carlo failure rate**: probability of depletion by `stop_age`

`fin_plan` is a **decision-support tool**. It explores risk and tradeoffs; it does not predict the future.

---

## Validation and Testing

Before committing changes or trusting new scenarios, run:

```bash
./run_validations.sh
```

This performs:

1. Schema and structural validation of all JSON files
2. Runtime smoke tests using representative scenarios

This validation layer exists to prevent silent regressions and enforce explicit contracts.

