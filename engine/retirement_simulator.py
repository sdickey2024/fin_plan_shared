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

def compute_start_age(person, start_date_dt):
    if "birthdate" in person:
        bd = datetime.strptime(person["birthdate"], "%Y-%m-%d")
        months = (start_date_dt.year - bd.year) * 12 + (start_date_dt.month - bd.month)
        return months / 12.0
    else:
        return float(person["current_age"])

def _validate_unique_event_names(events):
    """Require every life_event to have a unique 'event' string."""
    names = []
    for ev in events:
        name = (ev.get("event") or "").strip()
        if not name:
            raise ValueError("Each life_event must have a non-empty 'event' name")
        names.append(name)

    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(
            f"Duplicate life_event names not allowed: {dupes}. "
            "Make 'event' strings unique so offset.from is unambiguous."
        )

def _resolve_offset_events_to_t_month(events):
    """
    Resolve events with:
      offset: { from: <event name>, years: N, months: M }
    into a concrete t_month.

    Requires:
      - unique event names
      - referenced event exists
      - referenced event has a resolved t_month
    """
    by_name = {ev["event"].strip(): ev for ev in events}

    # Fixed-point dependency resolution so chains work (A -> B -> C)
    remaining = True
    while remaining:
        remaining = False
        progressed = False

        for ev in events:
            off = ev.get("offset")
            if not isinstance(off, dict):
                continue

            # already resolved?
            if ev.get("t_month") is not None:
                continue

            frm = (off.get("from") or "").strip()
            if not frm:
                raise ValueError(f"Event '{ev.get('event')}' has offset but missing offset.from")

            if frm not in by_name:
                raise ValueError(
                    f"Event '{ev.get('event')}' offset.from '{frm}' does not exist "
                    "(check spelling / uniqueness)."
                )

            ref = by_name[frm]
            if ref.get("t_month") is None:
                # can't resolve yet; ref might itself be an offset event
                remaining = True
                continue

            years  = int(off.get("years", 0))
            months = int(off.get("months", 0))
            ev["t_month"] = int(ref["t_month"]) + years * 12 + months
            progressed = True

        if remaining and not progressed:
            offenders = [
                (e.get("event"), e.get("offset", {}).get("from"))
                for e in events
                if isinstance(e.get("offset"), dict) and e.get("t_month") is None
            ]
            raise ValueError(
                "Could not resolve offset events (cycle or missing base time). "
                f"Unresolved: {offenders}"
            )

def load_user_data(base_filepath, scenario_filepath):

    debug(INFO, "Loading User Data from Files {} + {}", base_filepath, scenario_filepath)

    # 1) Load the two JSONs
    debug(INFO, "Loading baseline data from {}", base_filepath)
    with open(base_filepath, 'r') as f:
        base = json.load(f)

    # IMPORTANT:
    # Snapshot *true baseline* assumptions from the base file BEFORE any scenario overlay/merge.
    # If we derive this from the merged dict, "reset to base" will incorrectly reset to
    # scenario-modified assumptions (exactly the failure mode you're seeing).
    base_assumptions_snapshot = deepcopy(base.get("assumptions", {}) or {})
        
    debug(INFO, "Loading scenario data from {}", scenario_filepath)
    with open(scenario_filepath, 'r') as f:
        scenario = json.load(f)

    # Start from baseline, then merge scenario on top (whatever your current logic is)
    data = base

    # Copy baseline keys (base owns the defaults)
    for key in ("person", "expenses", "income", "portfolio", "assumptions", "start_date", "description"):
        if key in base:
            data[key] = base[key]

    ## overlay scenario-specific keys

    # Scenario overrides: description and (optionally) assumptions/start_date
    data["description"] = scenario.get("description", data.get("description", ""))

    # Assumptions:
    # - Preserve the *baseline* assumptions from the base file so scenarios can
    #   explicitly reset back to them mid-simulation.
    # - Then overlay scenario defaults (scenario may omit this entirely).
    data["_base_assumptions"] = base_assumptions_snapshot

    # Start with baseline assumptions, then overlay scenario defaults.
    base_assumptions = deepcopy(data["_base_assumptions"])
    scen_assumptions = scenario.get("assumptions")
    if isinstance(scen_assumptions, dict):
        base_assumptions.update(scen_assumptions)
    data["assumptions"] = base_assumptions

    # Allow scenario to override the simulation start date if desired
    if "start_date" in scenario:
        data["start_date"] = scenario.get("start_date")

    # merge life events from user data and scenario
    base_events = base.get("life_events", [])
    scen_events = scenario.get("life_events", [])   
    data["life_events"] = (base_events or []) + (scen_events or [])

    
    for ev in base_events or []:
        ev.setdefault("source", "profile")
    for ev in scen_events or []:
        ev.setdefault("source", "scenario")

    # 3) Defensive initialization (as before)
    data.setdefault("income", {})
    data.setdefault("expenses", {})
    data["income"].setdefault("monthly", 0.0)
    data["expenses"].setdefault("total_tax_rate", 0.0)
    data["expenses"].setdefault("breakdown", {})
    data["expenses"].setdefault("classification", {})
    data["expenses"].setdefault("spending_policy", {})

    # 4) Prepopulate any new income/expense categories from life_events
    all_income_keys  = set(data["income"].keys())
    all_expense_keys = set(data["expenses"]["breakdown"].keys())

    for ev in data["life_events"]:
        for k in ev.get("updated_income", {}):
            all_income_keys.add(k)
        for k in ev.get("updated_expenses", {}).get("breakdown", {}):
            all_expense_keys.add(k)
        for k in ev.get("updated_expenses", {}).get("classification", {}):
            all_expense_keys.add(k)

    for k in all_income_keys:
        data["income"].setdefault(k, 0.0)
    for k in all_expense_keys:
        data["expenses"]["breakdown"].setdefault(k, 0.0)

    # Back-compat default: unclassified expenses are fixed.
    # (This keeps existing simulations identical until we actually enforce caps.)
    cls = data["expenses"].get("classification") or {}
    for k in data["expenses"]["breakdown"].keys():
        cls.setdefault(k, "fixed")
    data["expenses"]["classification"] = cls

    # 5) Normalize simulation anchor + relative event timing
    #    - Anchor the entire simulation to a single start_date (month granularity)
    #    - Allow life events to be specified relative to start via:
    #         * t_month (int, months from start; 0 = start month)
    #         * t: { "year": N, "month": M }  (1-based year/month from start)
    #      Legacy "date" is still accepted and will be converted to t_month.
    start_date_str = data.get("start_date")
    start_date_dt = None
    if isinstance(start_date_str, str) and start_date_str.strip():
        s = start_date_str.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                start_date_dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        if start_date_dt is None:
            raise ValueError(f"Invalid start_date '{start_date_str}'. Expected YYYY-MM-01 or YYYY-MM.")
    else:
        now = datetime.now()
        start_date_dt = datetime(now.year, now.month, 1)

    # Force to first-of-month and persist back to the merged data
    start_date_dt = datetime(start_date_dt.year, start_date_dt.month, 1)
    data["start_date"] = start_date_dt.strftime("%Y-%m-%d")

    # Compute current age from birthdate (preferred) or legacy current_age
    age0 = compute_start_age(data["person"], start_date_dt)
    data["person"]["current_age"] = age0

    _validate_unique_event_names(data.get("life_events", []))

    # --- Two-pass timing resolution -----------------------------------------
    # Pass 1: resolve non-offset events to t_month (t_month / t / age / date).
    # Pass 2: resolve offset-based events once refs have t_month.
    # Pass 3: convert all t_month -> date and fill in human-friendly 't'.

    # Pass 1: compute t_month for events that are NOT offset-based
    for ev in data.get("life_events", []):
        if isinstance(ev.get("offset"), dict):
            continue

        tm = None

        if "t_month" in ev and ev["t_month"] is not None:
            tm = int(ev["t_month"])

        elif isinstance(ev.get("t"), dict):
            ty = int(ev["t"].get("year"))
            tmn = int(ev["t"].get("month"))
            if ty < 0:
                raise ValueError("life_event.t.year must be >= 0")
            if not (1 <= tmn <= 12):
                raise ValueError("life_event.t.month must be in 1..12")
            tm = ty * 12 + (tmn - 1)

        elif "age" in ev:
            target_age = float(ev["age"])
            tm = int(round((target_age - age0) * 12))
            if tm < 0:
                raise ValueError(
                    f"life_event '{ev.get('event')}' occurs before simulation start"
                )

        elif isinstance(ev.get("date"), str) and ev["date"].strip():
            # Legacy absolute date -> convert to month offset
            ed = datetime.strptime(ev["date"].strip(), "%Y-%m-%d")
            tm = (ed.year - start_date_dt.year) * 12 + (ed.month - start_date_dt.month)

        else:
            raise ValueError("Each life_event must include one of: t_month, t{year,month}, or date")

        ev["t_month"] = tm

    # Pass 2: resolve offset-based events into t_month (supports chaining)
    _resolve_offset_events_to_t_month(data.get("life_events", []))

    # Pass 3: convert *all* t_month to absolute date strings + fill 't'
    for ev in data.get("life_events", []):
        if ev.get("t_month") is None:
            raise ValueError(
                f"life_event '{ev.get('event')}' still missing t_month after resolution"
            )
        tm = int(ev["t_month"])
        ed = start_date_dt + relativedelta(months=tm)
        ev["date"] = datetime(ed.year, ed.month, 1).strftime("%Y-%m-%d")
        ev.setdefault("t", {"year": (tm // 12), "month": (tm % 12) + 1})

    # Ensure chronological order (normalize_user_data_events expects this)
    data["life_events"] = sorted(data.get("life_events", []), key=lambda e: int(e.get("t_month", 0)))

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
    expenses_classification: dict
    spending_policy: dict
    portfolio: float
    exp_return: float
    variance: float
    inflation: float

def build_initial_state(user_data):
    p = user_data["person"]
    a = user_data["assumptions"]
    start_date_dt = None
    start_date_str = user_data.get("start_date")
    if isinstance(start_date_str, str) and start_date_str.strip():
        start_date_dt = datetime.strptime(start_date_str.strip(), "%Y-%m-%d")
    else:
        now = datetime.now()
        start_date_dt = datetime(now.year, now.month, 1)

    # Optional spending control metadata (plumbing only; not yet enforced)
    classification = deepcopy(user_data.get("expenses", {}).get("classification", {}) or {})
    spending_policy = deepcopy(user_data.get("expenses", {}).get("spending_policy", {}) or {})

    # Back-compat: any expense key not explicitly classified is treated as fixed.
    base_breakdown = deepcopy(user_data["expenses"]["breakdown"])
    for k in base_breakdown.keys():
        classification.setdefault(k, "fixed")

    return SimState(
        year=int(start_date_dt.year),
        month=int(start_date_dt.month),
        age=float(p["current_age"]),
        stop_age=float(p.get("stop_age", 100)),
        tax_rate=float(user_data["expenses"].get("total_tax_rate", 0.0)),
        income=deepcopy(user_data.get("income", {})),
        expenses_breakdown=base_breakdown,
        expenses_classification=classification,
        spending_policy=spending_policy,
        portfolio=sum_portfolio(user_data["portfolio"]["breakdown"]),
        exp_return=float(a.get("expected_return", 0.06)),
        variance=float(a.get("variance", 0.02)),
        inflation=float(a.get("inflation", 0.025)),
    )

def date_str(y, m): 
    return f"{y:04d}-{m:02d}-01"

def apply_events_for_date(state: SimState, life_events, start_current_age, start_date, base_assumptions=None):
    """Apply any events scheduled for state.year/state.month.
       Returns the label of the first event matched (for logging/graphs)
       and a flag indicating whether exp_return/variance/inflation changed."""
    evt_label = ""
    changed_assumptions = False
    assumption_reason = "undefined"
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
            if "classification" in ue and isinstance(ue.get("classification"), dict):
                state.expenses_classification.update(ue["classification"])
            if "spending_policy" in ue and isinstance(ue.get("spending_policy"), dict):
                state.spending_policy.update(ue["spending_policy"])

        # Assumptions
        if "updated_assumptions" in ev:
            ua = ev.get("updated_assumptions")
            if not isinstance(ua, dict):
                ua = {}
            if "expected_return" in ua:
                old = state.exp_return
                state.exp_return = float(ua["expected_return"])
                changed_assumptions = True
                assumption_reason = f"updated_assumptions.expected_return={ua.get('expected_return')}"
                if old == 0.3 and state.exp_return == 0.04:
                    print(f"[ASSUMP] {d} event='{ev.get('event')}' exp_return {old} -> {state.exp_return}  ev_keys={list(ev.keys())}")
            if "variance" in ua:
                changed_assumptions = True
                if not assumption_reason: assumption_reason = "updated_assumptions.variance"
                state.variance = float(ua["variance"])
            if "inflation" in ua:
                state.inflation = float(ua["inflation"])
                changed_assumptions = True
                if not assumption_reason: assumption_reason = "updated_assumptions.inflation"

        # Reset markers (explicit end-of-scenario behavior)
        # Example:
        #   "reset": { "assumptions": "base" }
        if isinstance(ev.get("reset"), dict):
            reset = ev["reset"]
            if reset.get("assumptions") == "base":
                if not isinstance(base_assumptions, dict):
                    raise ValueError(
                        "life_event.reset.assumptions='base' requires base_assumptions to be provided"
                    )
                if "expected_return" in base_assumptions:
                    state.exp_return = float(base_assumptions["expected_return"])
                    changed_assumptions = True
                    assumption_reason = f"reset.base.expected_return={base_assumptions.get('expected_return')}"
                if "variance" in base_assumptions:
                    state.variance = float(base_assumptions["variance"])
                    changed_assumptions = True
                    if not assumption_reason: assumption_reason = "reset.base.variance"
                if "inflation" in base_assumptions:
                    state.inflation = float(base_assumptions["inflation"])
                    changed_assumptions = True
                    if not assumption_reason: assumption_reason = "reset.base.inflation"

        if not evt_label:
            evt_label = ev.get("event", "")

    if not assumption_reason: assumption_reason = "undefined"

    return evt_label, changed_assumptions, assumption_reason
        
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

def _is_number(x):
    return isinstance(x, (int, float, np.floating))

def apply_spending_policy(state: SimState, granularity: str):
    """
    Enforce spending policy by capping *withdrawals* (gross_up), not raw expenses.

    Returns:
      effective_breakdown (dict): raw expenses to use for this step's cashflow calc
      monthly_discretionary_spend (float): actual discretionary raw spend after cap
      monthly_withdrawal_cap (float): W_cap
      monthly_fixed_withdrawal_need (float): W_fixed
      monthly_requested_discretionary (float): desired discretionary raw spend (pre-cap)
    """
    requested = state.expenses_breakdown
    cls = state.expenses_classification or {}
    policy = state.spending_policy or {}

    discretionary_keys = [k for k in requested.keys() if cls.get(k, "fixed") == "discretionary"]
    requested_disc = sum(float(requested.get(k, 0.0)) for k in discretionary_keys)

    # No discretionary categories -> nothing to cap (still report)
    if not discretionary_keys:
        return dict(requested), 0.0, 0.0, 0.0, requested_disc

    # If no policy or unsupported policy -> no change (but report requested/actual)
    cap_rate = policy.get("cap_rate", None)
    policy_type = policy.get("type", None)
    if policy_type != "portfolio_cap" or not _is_number(cap_rate) or float(cap_rate) <= 0:
        disc_total = requested_disc
        return dict(requested), disc_total, 0.0, 0.0, requested_disc

    # --- Withdrawal cap (gross_up cap) ---------------------------------------
    div = 12.0 if granularity == "monthly" else 1.0
    W_cap = float(state.portfolio) * float(cap_rate) / div

    # Split requested expenses into fixed + discretionary (raw)
    fixed_breakdown = {k: float(v) for k, v in requested.items() if cls.get(k, "fixed") != "discretionary"}
    disc_breakdown  = {k: float(requested.get(k, 0.0)) for k in discretionary_keys}

    # Compute fixed-only withdrawal need under your tax model
    # (gross_up is the pre-tax withdrawal required to fund net expenses)
    _mi, _raw_fixed, _taxed_inc, _net_fixed, W_fixed = compute_cashflows(
        state.income, fixed_breakdown, state.tax_rate
    )

    W_room = max(0.0, W_cap - float(W_fixed))

    # Convert remaining withdrawal room into raw discretionary allowance.
    # Because spending $1 of raw expenses costs 1/(1-tax_rate) of withdrawals.
    disc_raw_allow = W_room * (1.0 - float(state.tax_rate))

    # Fund discretionary in priority order, then the rest alphabetically
    prio = policy.get("priority_order") or []
    prio = [k for k in prio if k in disc_breakdown]
    tail = sorted([k for k in disc_breakdown.keys() if k not in prio])
    order = prio + tail

    remaining = disc_raw_allow
    funded_disc = {}
    disc_spend = 0.0

    for k in order:
        want = float(disc_breakdown.get(k, 0.0))
        spend = min(want, remaining)
        funded_disc[k] = spend
        disc_spend += spend
        remaining -= spend
        if remaining <= 0:
            break

    # Any discretionary not funded -> 0
    for k in disc_breakdown:
        funded_disc.setdefault(k, 0.0)

    effective = dict(fixed_breakdown)
    effective.update(funded_disc)

    return effective, disc_spend, W_cap, float(W_fixed), requested_disc
            
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
            ev_label, changed, assumption_reason = apply_events_for_date(
                state, life_events,
                start_current_age=data["person"]["current_age"],
                start_date=datetime.strptime(data["start_date"], "%Y-%m-%d"),
                base_assumptions=data.get("_base_assumptions"),
            )
            if changed:
                r, i, step_div = step_factors(state.exp_return, state.inflation, granularity)

            effective_breakdown, disc_spend, W_cap, W_fixed, req_disc = apply_spending_policy(state, granularity)

            cls = state.expenses_classification or {}
            requested_total = sum(float(v) for v in state.expenses_breakdown.values())
            requested_disc  = sum(float(v) for k, v in state.expenses_breakdown.items()
                                  if cls.get(k, "fixed") == "discretionary")
            requested_fixed = requested_total - requested_disc
            
            mi, raw, taxed_inc, net, gross_up = compute_cashflows(
                state.income, effective_breakdown, state.tax_rate
            )

            # portfolio update
            state.portfolio = max(0.0, state.portfolio * (1 + r) - gross_up)

            results.append({
                "year": y, "month": m, "age": round(age, 2),
                "portfolio_end": round(state.portfolio, 2),
                
                "exp_return_annual": round(state.exp_return, 6),
                "variance_annual": round(state.variance, 6),
                "inflation_annual": round(state.inflation, 6),
                "return_step_factor": round(r, 10),
                "inflation_step_factor": round(i, 10),
                "return_step_pct": round((r - 1.0) * 100.0, 6),

                "monthly_income": round(mi, 2),
                "monthly_taxed_income": round(taxed_inc, 2),
                "monthly_requested_raw_expenses": round(requested_total, 2),
                "monthly_requested_fixed_expenses": round(requested_fixed, 2),
                "monthly_requested_discretionary_expenses": round(requested_disc, 2),
                "monthly_raw_expenses": round(raw, 2),
                "monthly_discretionary_expenses": round(disc_spend, 2),
                "monthly_withdrawl_cap":round(W_cap, 2),
                "monthly_fixed_withdrawl_need": round(W_fixed, 2),
                "monthly_net_expenses": round(net, 2),
                "monthly_gross_up": round(gross_up, 2),
                "event": ev_label,
                "assumption_reason": assumption_reason,
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
            _, changed, assumption_reason = apply_events_for_date(
                state, life_events,
                start_current_age=user_data["person"]["current_age"],
                start_date=datetime.strptime(user_data["start_date"], "%Y-%m-%d"),
                base_assumptions=user_data.get("_base_assumptions"),
            )
            if changed:
                base_r, base_i, step_div = step_factors(state.exp_return, state.inflation, granularity)

            if not depleted:
                # Draw per-step return via injected sampler (or default 0 if none)
                if sampler is not None:
                    step_r = sampler(state, y, m, base_r, base_i, step_div, rng)
                else:
                    step_r = base_r  # deterministic fallback (no randomness)

                # Apply spending policy (must match deterministic semantics)
                effective_breakdown, _, _, _, _ = apply_spending_policy(state, granularity)

                # Cashflows for this step
                mi, raw, taxed_inc, net, gross_up = compute_cashflows(
                    state.income, effective_breakdown, state.tax_rate
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
