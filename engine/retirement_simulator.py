# engine/retirement_simulator.py

import os
import random
import json
import copy

from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.ticker as ticker
from dateutil.relativedelta import relativedelta
from debug import *

from dataclasses import dataclass, field
from copy import deepcopy

def load_user_data(base_filepath, scenario_filepath):

    debug(INFO, "Loading User Data from Files {} + {}", base_filepath, scenario_filepath)

    # 1) Load the two JSONs
    debug(INFO, "Loading baseline data from {}", base_filepath)
    with open(base_filepath, 'r') as f:
        base = json.load(f)

    debug(INFO, "Loading scenario data from {}", scenario_filepath)
    with open(scenario_filepath, 'r') as f:
        scenario = json.load(f)

    # 2) Merge into one dict
    data = {}
    # copy baseline keys
    for key in ("person", "expenses", "income", "portfolio"):
        if key in base:
            data[key] = base[key]
    # overlay scenario-specific keys
    data["description"]  = scenario.get("description", "")
    data["life_events"]  = scenario.get("life_events", [])
    data["assumptions"]  = scenario.get("assumptions", {})

    # 3) Defensive initialization (as before)
    data.setdefault("income", {})
    data.setdefault("expenses", {})
    data["income"].setdefault("monthly", 0.0)
    data["expenses"].setdefault("total_tax_rate", 0.0)
    data["expenses"].setdefault("breakdown", {})

    # 4) Prepopulate any new income/expense categories from life_events
    all_income_keys  = set(data["income"].keys())
    all_expense_keys = set(data["expenses"]["breakdown"].keys())

    for ev in data["life_events"]:
        for k in ev.get("updated_income", {}):
            all_income_keys.add(k)
        for k in ev.get("updated_expenses", {}).get("breakdown", {}):
            all_expense_keys.add(k)

    for k in all_income_keys:
        data["income"].setdefault(k, 0.0)
    for k in all_expense_keys:
        data["expenses"]["breakdown"].setdefault(k, 0.0)

    debug(INFO, "Final merged data keys: person={}; expenses={}; income={}; portfolio={}; events={}",
          list(data.get("person",{}).keys()),
          list(data.get("expenses",{}).get("breakdown",{}).keys()),
          list(data.get("income",{}).keys()),
          list(data.get("portfolio",{}).get("breakdown",{}).keys()),
          len(data.get("life_events", []))
    )

    return data

def get_event_age(event_date_str, current_age, current_date=None):
    """
    Convert an event date string (e.g., '2030-01-01') into an age (float).
    Optionally takes the current date for precise calculation (defaults to now).
    """
    if current_date is None:
        current_date = datetime.now()

    try:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format for life event: {event_date_str}")

    # Compute the number of months between the two dates
    delta_years = (event_date.year - current_date.year)
    delta_months = event_date.month - current_date.month
    total_months = delta_years * 12 + delta_months

    # Calculate precise age at the time of event
    return round(current_age + total_months / 12.0, 2)

def sum_portfolio(portfolio_breakdown):
    total = 0
    for category in portfolio_breakdown.values():
        total += sum(category.values())
    return total

def apply_tax_rate(value, tax_rate):
    return value / (1 - tax_rate) if tax_rate < 1 else value

@dataclass
class SimState:
    year: int
    month: int
    age: float
    stop_age: float
    tax_rate: float
    income: dict
    expenses_breakdown: dict
    portfolio: float
    exp_return: float
    variance: float
    inflation: float

def build_initial_state(user_data, start_year=None):
    p = user_data["person"]
    a = user_data["assumptions"]
    return SimState(
        year=(start_year or datetime.now().year),
        month=1,
        age=float(p["current_age"]),
        stop_age=float(p.get("stop_age", 100)),
        tax_rate=float(user_data["expenses"].get("total_tax_rate", 0.0)),
        income=deepcopy(user_data.get("income", {})),
        expenses_breakdown=deepcopy(user_data["expenses"]["breakdown"]),
        portfolio=sum_portfolio(user_data["portfolio"]["breakdown"]),
        exp_return=float(a.get("expected_return", 0.06)),
        variance=float(a.get("variance", 0.02)),
        inflation=float(a.get("inflation", 0.025)),
    )

def date_str(y, m): 
    return f"{y:04d}-{m:02d}-01"

def apply_events_for_date(state: SimState, life_events, start_current_age, start_date):
    """Apply any events scheduled for state.year/state.month.
       Returns the label of the first event matched (for logging/graphs)
       and a flag indicating whether exp_return/variance/inflation changed."""
    evt_label = ""
    changed_assumptions = False
    d = date_str(state.year, state.month)
    for ev in life_events:
        if ev.get("date") != d:
            continue

        # Income
        if "updated_income" in ev:
            state.income.update(ev["updated_income"])

        # Expenses
        if "updated_expenses" in ev:
            ue = ev["updated_expenses"]
            if "breakdown" in ue:
                state.expenses_breakdown.update(ue["breakdown"])
            if "total_tax_rate" in ue:
                state.tax_rate = float(ue["total_tax_rate"])

        # Assumptions
        if "updated_assumptions" in ev:
            ua = ev["updated_assumptions"]
            if "expected_return" in ua:
                state.exp_return = float(ua["expected_return"])
                changed_assumptions = True
            if "variance" in ua:
                state.variance = float(ua["variance"])
            if "inflation" in ua:
                state.inflation = float(ua["inflation"])
                changed_assumptions = True

        if not evt_label:
            evt_label = ev.get("event", "")

    return evt_label, changed_assumptions

def compute_cashflows(income: dict, expenses_breakdown: dict, tax_rate: float):
    monthly_income = sum(v for v in income.values() if isinstance(v, (int, float, float)))
    raw_expenses   = sum(expenses_breakdown.values())
    taxed_income   = monthly_income * (1 - tax_rate)
    net_expense    = raw_expenses - taxed_income
    gross_up       = apply_tax_rate(max(net_expense, 0), tax_rate)
    return monthly_income, raw_expenses, taxed_income, net_expense, gross_up

def step_factors(exp_return_annual, inflation_annual, granularity):
    if granularity == "monthly":
        r = (1 + exp_return_annual) ** (1/12) - 1
        i = (1 + inflation_annual) ** (1/12) - 1
        step_div = 12
    else:
        r = exp_return_annual
        i = inflation_annual
        step_div = 1
    return r, i, step_div

def timeline(state: SimState, granularity='monthly'):
    """Yield successive (year, month, age) until stop_age (inclusive)."""
    while state.age <= state.stop_age:
        # expose the *current* timestamp to the caller
        yield state.year, state.month, state.age

        if granularity == 'monthly':
            # Advance exactly one month with proper wrap to 1..12
            # Convert to zero-based month index, add one, then normalize.
            zero_based_next = (state.month - 1) + 1
            state.year  += zero_based_next // 12
            state.month  = (zero_based_next % 12) + 1

            # Age advances by exactly one month
            state.age   += 1.0 / 12.0
        else:
            # Yearly step
            state.year  += 1
            state.age   += 1.0

def simulate_retirement(data, granularity='monthly'):
    life_events = sorted(data.get("life_events", []), key=lambda e: e["date"])
    state_base  = build_initial_state(data)
    sims = {}
    for label, annual_return in {
        "min": state_base.exp_return - state_base.variance,
        "expected": state_base.exp_return,
        "max": state_base.exp_return + state_base.variance
    }.items():
        state = deepcopy(state_base)
        state.exp_return = annual_return
        r, i, step_div = step_factors(state.exp_return, state.inflation, granularity)

        results = []
        for y, m, age in timeline(state, granularity):
            # Apply any events for this date
            ev_label, changed = apply_events_for_date(
                state, life_events,
                start_current_age=data["person"]["current_age"],
                start_date=datetime(datetime.now().year, 1, 1),
            )
            if changed:
                r, i, step_div = step_factors(state.exp_return, state.inflation, granularity)

            mi, raw, taxed_inc, net, gross_up = compute_cashflows(
                state.income, state.expenses_breakdown, state.tax_rate
            )

            # portfolio update
            state.portfolio = max(0.0, state.portfolio * (1 + r) - gross_up)

            results.append({
                "year": y, "month": m, "age": round(age, 2),
                "portfolio_end": round(state.portfolio, 2),
                "income": round(mi * 12, 2),
                "taxed_income": round(taxed_inc * 12, 2),
                "monthly_raw_expenses": round(raw, 2),
                "raw_expenses": round(raw * 12, 2),
                "net_expenses": round(net * 12, 2),
                "gross_up": round(gross_up * 12, 2),
                "event": ev_label
            })

            # drift expenses with inflation for next step
            inflation_step = (1 + i)
            for k in state.expenses_breakdown:
                state.expenses_breakdown[k] *= inflation_step

            if state.portfolio <= 0:
                break

        sims[label] = results

    return sims


# ---- Core MC engine ---------------------------------------------------------
def mc_core(user_data,
            trials=1000,
            granularity='monthly',
            sampler=None,
            collect_paths=False,
            seed=None):
    """
    Shared Monte Carlo engine that matches deterministic simulator semantics.

    - sampler(state, y, m, base_r, base_i, step_div, rng) -> per-step return (float)
    - Returns a summary dict; if collect_paths=True, includes:
        summary["paths"] : np.ndarray of shape (trials, steps_total)
    """
    import numpy as np
    from copy import deepcopy
    from datetime import datetime

    rng = np.random.default_rng(seed)

    # Prepare events/state like deterministic sim
    life_events = sorted(user_data.get("life_events", []), key=lambda e: e["date"])
    base_state  = build_initial_state(user_data)

    # Timeline setup (no drift)
    start_age   = float(base_state.age)
    stop_age    = float(base_state.stop_age)
    start_year  = int(base_state.year)
    start_month = int(base_state.month)
    per_year    = 12 if granularity == 'monthly' else 1
    # Include the terminal step at stop_age (mirror "while age <= stop_age")
    steps_total = int(round((stop_age - start_age) * per_year)) + 1

    # Pre-allocate outputs
    paths = np.zeros((trials, steps_total), dtype=float) if collect_paths else None
    terminal_values = np.zeros(trials, dtype=float)
    failure_flags   = np.zeros(trials, dtype=bool)

    def _cursor_from_step(step: int):
        if granularity == 'monthly':
            y = start_year  + ((start_month - 1 + step) // 12)
            m = ((start_month - 1 + step) % 12) + 1
            a = start_age + step / 12.0
            return y, m, a
        # yearly
        return start_year + step, start_month, start_age + step

    for t in range(trials):
        state = deepcopy(base_state)
        # Base factors for current assumptions
        base_r, base_i, step_div = step_factors(state.exp_return, state.inflation, granularity)

        depleted = False
        for s in range(steps_total):
            # Drive time cursor from step index (no incremental drift)
            y, m, age = _cursor_from_step(s)
            state.year, state.month, state.age = y, m, age

            # Apply events for THIS date, like deterministic path
            _, changed = apply_events_for_date(
                state, life_events,
                start_current_age=user_data["person"]["current_age"],
                start_date=datetime(datetime.now().year, 1, 1),
            )
            if changed:
                base_r, base_i, step_div = step_factors(state.exp_return, state.inflation, granularity)

            if not depleted:
                # Draw per-step return via injected sampler (or default 0 if none)
                if sampler is not None:
                    step_r = sampler(state, y, m, base_r, base_i, step_div, rng)
                else:
                    step_r = base_r  # deterministic fallback (no randomness)

                # Cashflows for this step
                mi, raw, taxed_inc, net, gross_up = compute_cashflows(
                    state.income, state.expenses_breakdown, state.tax_rate
                )

                # Portfolio evolution (same order as deterministic)
                state.portfolio = max(0.0, state.portfolio * (1.0 + step_r) - gross_up)

                # Detect depletion; if depleted, carry zeros for remainder
                if state.portfolio <= 0.0:
                    depleted = True
                    failure_flags[t] = True

                # Drift expenses with inflation to next step
                infl_mult = (1.0 + base_i)
                for k in state.expenses_breakdown:
                    state.expenses_breakdown[k] *= infl_mult

            # Record path value
            if collect_paths:
                paths[t, s] = state.portfolio if not depleted else 0.0

        terminal_values[t] = state.portfolio

    summary = {
        "success_rate": float(1.0 - failure_flags.mean()),
        "terminal_median": float(np.median(terminal_values)),
        "terminal_p10": float(np.percentile(terminal_values, 10)),
        "terminal_p90": float(np.percentile(terminal_values, 90)),
        "trials": trials,
        "granularity": granularity,
    }
    if collect_paths:
        summary["paths"] = paths
    return summary


# ---- Baseline Monte Carlo wrapper -------------------------------------------
def run_monte_carlo(user_data,
                    trials=1000,
                    granularity='monthly',
                    seed=None,
                    _return_paths: bool = False):
    """
    Baseline Monte Carlo using mc_core; life events are applied inside mc_core.
    Returns:
      ages, (p10, p50, p90)             when _return_paths=False (default)
      ages, (p10, p50, p90), paths_nd   when _return_paths=True
    """
    import numpy as np

    steps_per_year = 12 if granularity == 'monthly' else 1

    def _step_sigma(annual_sigma: float, steps: int) -> float:
        if not annual_sigma:
            return 0.0
        return float(annual_sigma) / np.sqrt(float(steps))

    def sampler(state, y, m, base_r, base_i, step_div, rng_local):
        sigma = _step_sigma(state.variance, steps_per_year)
        return rng_local.normal(loc=base_r, scale=sigma)

    summary = mc_core(
        user_data=user_data,
        trials=trials,
        granularity=granularity,
        sampler=sampler,
        collect_paths=True,   # always collect so we can compute envelopes (and sample if requested)
        seed=seed,
    )

    paths = summary.get("paths")
    if paths is None or getattr(paths, "size", 0) == 0:
        return ([], ([], [], [])) if not _return_paths else ([], ([], [], []), None)

    start_age = float(user_data.get("person", {}).get("current_age", 0.0))
    steps_total = int(paths.shape[1])
    if granularity == 'monthly':
        ages = [start_age + s / 12.0 for s in range(steps_total)]
    else:
        ages = [start_age + s for s in range(steps_total)]

    p10 = np.nanpercentile(paths, 10, axis=0).tolist()
    p50 = np.nanpercentile(paths, 50, axis=0).tolist()
    p90 = np.nanpercentile(paths, 90, axis=0).tolist()

    return (ages, (p10, p50, p90)) if not _return_paths else (ages, (p10, p50, p90), paths)

def run_monte_carlo_events(user_data,
                           trials=1000,
                           granularity='monthly',
                           seed=None):
    """
    Back-compat wrapper that returns a sample path for plotting.
    Behavior is identical to run_monte_carlo; only the return shape differs.
    Returns: ages, (p10, p50, p90), mc_sample_run(list of dicts)
    """
    ages, mc_percentiles, paths = run_monte_carlo(
        user_data,
        trials=trials,
        granularity=granularity,
        seed=seed,
        _return_paths=True,
    )

    if paths is None or getattr(paths, "size", 0) == 0:
        return ages, mc_percentiles, []

    mc_sample_run = [
        {"age": ages[s], "portfolio_value": float(paths[0, s])}
        for s in range(len(ages))
    ]
    return ages, mc_percentiles, mc_sample_run

def run_monte_carlo_force(user_data,
                          trials=1000,
                          granularity='monthly',
                          seed=None,
                          forced_events=None):
    """
    Monte Carlo with forced market shocks on specified months.
    Behavior matches run_monte_carlo, except when a month is listed in
    forced_events (or user_data["forced_market_events"]) we override that
    step's return.

    Each event supports either:
      {"date": "YYYY-MM[-DD]", "drop_pct": 0.30}        # -30% for that step
      {"date": "YYYY-MM[-DD]", "shock_return": -0.35}   # literal per-step return
    """
    import numpy as np

    # --- Build a month->forced_return map ------------------------------------
    events = forced_events
    if events is None:
        events = user_data.get("forced_market_events", []) or []

    def _to_ym(ev):
        # accept "YYYY-MM" or "YYYY-MM-DD"
        d = ev.get("date", "")
        if len(d) >= 7:
            return d[:7]  # YYYY-MM
        # allow alternate key "ym"
        return ev.get("ym", "")

    crash_map = {}
    for ev in events:
        ym = _to_ym(ev)
        if not ym:
            continue
        if "shock_return" in ev:
            crash_map[ym] = float(ev["shock_return"])
        elif "drop_pct" in ev:
            crash_map[ym] = -abs(float(ev["drop_pct"]))  # 0.30 -> -0.30

    steps_per_year = 12 if granularity == 'monthly' else 1

    def _step_sigma(annual_sigma: float, steps: int) -> float:
        if not annual_sigma:
            return 0.0
        return float(annual_sigma) / np.sqrt(float(steps))

    # Sampler: if month is forced, use that; else draw normally
    def sampler(state, y, m, base_r, base_i, step_div, rng_local):
        ym = f"{int(y):04d}-{int(m):02d}"
        if ym in crash_map:
            return crash_map[ym]
        sigma = _step_sigma(state.variance, steps_per_year)
        return rng_local.normal(loc=base_r, scale=sigma)

    # --- Run core engine ------------------------------------------------------
    summary = mc_core(
        user_data=user_data,
        trials=trials,
        granularity=granularity,
        sampler=sampler,
        collect_paths=True,
        seed=seed,
    )

    paths = summary.get("paths")
    if paths is None or getattr(paths, "size", 0) == 0:
        return [], ([], [], []), []

    # Age axis aligned to paths length
    start_age = float(user_data.get("person", {}).get("current_age", 0.0))
    steps_total = int(paths.shape[1])
    if granularity == 'monthly':
        ages = [start_age + s / 12.0 for s in range(steps_total)]
    else:
        ages = [start_age + s for s in range(steps_total)]

    # Percentiles
    p10 = np.nanpercentile(paths, 10, axis=0).tolist()
    p50 = np.nanpercentile(paths, 50, axis=0).tolist()
    p90 = np.nanpercentile(paths, 90, axis=0).tolist()

    # Sample path (trial 0) in dict shape the plotter already accepts
    mc_sample_run = [
        {"age": ages[s], "portfolio_value": float(paths[0, s])}
        for s in range(steps_total)
    ]

    return ages, (p10, p50, p90), mc_sample_run
