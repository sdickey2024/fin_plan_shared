import csv
import inspect
import pprint
from datetime import date
from copy import deepcopy

# Debug level constants
ERROR      = 0
WARNING    = 1
INFO       = 2
VERBOSE    = 3
VVERBOSE   = 4
VVVERBOSE  = 5

# Current threshold (only messages ≤ this level will print)
debug_level = VVVERBOSE

def set_debug_level(level):
    """Set the global debug_level. Accepts one of ERROR…VVVERBOSE."""
    global debug_level
    debug_level = level

def debug(level, msg, *args, **kwargs):
    """
    Print a debug message if level ≤ current debug_level.
    
    Usage:
        debug(INFO,    "Starting simulation with x={}", x)
        debug(VVERBOSE, "Details: {}", data)
    """
    if level > debug_level:
        return

    # Find caller info
    frame = inspect.currentframe().f_back
    func_name = frame.f_code.co_name
    line_no   = frame.f_lineno

    # Format message
    try:
        text = msg.format(*args, **kwargs)
    except Exception:
        text = msg

    # Prefix level name
    level_name = {
        ERROR:     "ERROR    ",
        WARNING:   "WARNING  ",
        INFO:      "INFO     ",
        VERBOSE:   "VERBOSE  ",
        VVERBOSE:  "VVERBOSE ",
        VVVERBOSE: "VVVERBOSE"
    }.get(level, str(level))

    print(f"[{level_name}] {func_name} [{line_no}]: {text}")

def dump_data(data):
    """
    Pretty‐print a Python structure (e.g. your loaded user_data dict),
    but only if debug_level ≥ VVERBOSE.
    """
    # Only dump at very high verbosity
    if debug_level < VVERBOSE:
        return

    # Figure out who called us
    frame = inspect.currentframe().f_back
    func_name = frame.f_code.co_name
    line_no   = frame.f_lineno

    # Format the entire data structure
    pretty = pprint.pformat(data, indent=2, width=120)

    # Emit with context
    print(f"DUMP {func_name} [{line_no}]:\n{pretty}")

def _port_value(port_b, cat, subk, default=""):
    """Safe getter for portfolio breakdown nested dicts."""
    if not isinstance(port_b, dict):
        return default
    cat_d = port_b.get(cat, {})
    if not isinstance(cat_d, dict):
        return default
    return cat_d.get(subk, default)

def _port_event_value(ev_port, cat, subk):
    """Return event override value for a portfolio key if present, else None."""
    if not isinstance(ev_port, dict):
        return None
    cat_d = ev_port.get(cat, None)
    if not isinstance(cat_d, dict):
        return None
    return cat_d.get(subk, None)
    
def _is_assumptions_reset_event(ev: dict, ev_name: str) -> bool:
    """
    Detect events that reset assumptions back to the base file assumptions.
    The simulator typically performs this as a special-case (not via updated_assumptions),
    so the debug CSV must model it explicitly.
    """
    if not isinstance(ev, dict):
        return False

    # Prefer explicit flags if present
    for k in ("reload_base_assumptions", "reset_assumptions", "revert_to_base_assumptions", "end_scenario"):
        v = ev.get(k, False)
        if v is True:
            return True

    # Fallback heuristic based on name text (covers your current event label)
    n = (ev_name or "").lower()
    if "reload base assumptions" in n:
        return True
    if "revert" in n and "assumption" in n:
        return True
    if "reset" in n and "assumption" in n:
        return True

    return False

def dump_events_to_csv(data, csv_path):
    """
    Write out one row per life‐event (plus a Baseline row) with a column
    for every assumption, expense, income, and portfolio sub‐item.
    Only active when debug_level >= VVERBOSE.
    """
    debug(INFO, "dumping events to {}", csv_path)

    # 1) Discover all column keys
    # Assumptions
    ass_keys = list(data.get("assumptions", {}).keys())
    # Expenses breakdown
    exp_keys = list(data.get("expenses", {}).get("breakdown", {}).keys())
    # Income
    inc_keys = list(data.get("income", {}).keys())
    # Portfolio: flatten category.subkey
    port_b = data.get("portfolio", {}).get("breakdown", {})
    port_keys = [f"{cat}.{subk}"
                 for cat, subd in port_b.items()
                 for subk in subd.keys()]

    # 2) Build header row
    # Minimal strategy: split "what this event explicitly changes" vs "what is active after applying it".
    header = ["date", "event",
              "assumptions_changed", "expenses_changed", "income_changed", "portfolio_changed"]

    # Assumptions: event_*, active_*
    for k in ass_keys:
        header.append(f"event_{k}")
        header.append(f"active_{k}")

    # Expenses: event_exp_*, active_exp_*
    for k in exp_keys:
        header.append(f"event_exp_{k}")
        header.append(f"active_exp_{k}")

    # Income: event_inc_*, active_inc_*
    for k in inc_keys:
        header.append(f"event_inc_{k}")
        header.append(f"active_inc_{k}")

    # Portfolio: event_port_*, active_port_*
    for pk in port_keys:
        header.append(f"event_port_{pk}")
        header.append(f"active_port_{pk}")

    # 3) Open CSV and write
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        # Track "active" state as we walk events in order.
        cur_ass = dict(data.get("assumptions", {}) or {})
        cur_exp = dict(data.get("expenses", {}).get("breakdown", {}) or {})
        cur_inc = dict(data.get("income", {}) or {})
        cur_port = deepcopy(port_b) if isinstance(port_b, dict) else {}
        
        # Base assumptions (pre-scenario) are typically stored here by the loader.
        # If missing, fall back to current assumptions.
        base_ass = data.get("_base_assumptions")
        if not isinstance(base_ass, dict):
            base_ass = dict(cur_ass)

        # --- Baseline row ---
        # Use data.get("start_date") or today’s date
        base_date = data.get("start_date", date.today().isoformat())
        base_event = "Baseline"

        row = [base_date, base_event, False, False, False, False]

        # Baseline: no explicit event changes, so event_* columns blank; active_* columns show current state.
        for k in ass_keys:
            row.append("")               # event_{k}
            row.append(cur_ass.get(k, ""))  # active_{k}

        for k in exp_keys:
            row.append("")               # event_exp_{k}
            row.append(cur_exp.get(k, ""))  # active_exp_{k}

        for k in inc_keys:
            row.append("")               # event_inc_{k}
            row.append(cur_inc.get(k, ""))  # active_inc_{k}

        for pk in port_keys:
            cat, subk = pk.split(".", 1)
            row.append("")  # event_port_{pk}
            row.append(_port_value(cur_port, cat, subk, ""))  # active_port_{pk}

        writer.writerow(row)

        # --- One row per event ---
        for ev in data.get("life_events", []):
            ev_date = ev.get("date", "")
            ev_name = ev.get("event", "")

            ev_ass = ev.get("updated_assumptions", {}) or {}
            ev_exp = (ev.get("updated_expenses", {}) or {}).get("breakdown", {}) or {}
            ev_inc = ev.get("updated_income", {}) or {}
            ev_port = (ev.get("updated_portfolio", {}) or {}).get("breakdown", {}) or {}
            
            reset_assumptions = _is_assumptions_reset_event(ev, ev_name)
            if reset_assumptions:
                # The event explicitly causes assumptions to revert to base.
                # We model that as:
                #  - event_* assumption columns: base values
                #  - active_* assumption columns: base values after applying
                ev_ass_effective = dict(base_ass)
            else:
                ev_ass_effective = ev_ass

            assumptions_changed = reset_assumptions or (
                isinstance(ev_ass, dict) and any(k in ev_ass for k in ass_keys)
                )
            expenses_changed    = isinstance(ev_exp, dict) and any(k in ev_exp for k in exp_keys)
            income_changed      = isinstance(ev_inc, dict) and any(k in ev_inc for k in inc_keys)
            portfolio_changed   = False
            if isinstance(ev_port, dict):
                for pk in port_keys:
                    cat, subk = pk.split(".", 1)
                    if _port_event_value(ev_port, cat, subk) is not None:
                        portfolio_changed = True
                        break

            # Apply event updates to "active" state BEFORE outputting active_* columns.
            if reset_assumptions:
                cur_ass = dict(base_ass)
            elif isinstance(ev_ass, dict):
                cur_ass.update(ev_ass)
            if isinstance(ev_exp, dict):
                cur_exp.update(ev_exp)
            if isinstance(ev_inc, dict):
                cur_inc.update(ev_inc)
            if isinstance(ev_port, dict):
                # Nested update
                for cat, subd in ev_port.items():
                    if not isinstance(subd, dict):
                        continue
                    cur_cat = cur_port.get(cat)
                    if not isinstance(cur_cat, dict):
                        cur_cat = {}
                        cur_port[cat] = cur_cat
                    cur_cat.update(subd)

            row = [ev_date, ev_name,
                   assumptions_changed, expenses_changed, income_changed, portfolio_changed]

            # Assumptions: event values only if explicitly set; active values from cur_ass
            for k in ass_keys:
                row.append(ev_ass_effective.get(k, ""))     # event_{k}
                row.append(cur_ass.get(k, ""))    # active_{k}

            # Expenses
            for k in exp_keys:
                row.append(ev_exp.get(k, ""))     # event_exp_{k}
                row.append(cur_exp.get(k, ""))    # active_exp_{k}

            # Income
            for k in inc_keys:
                row.append(ev_inc.get(k, ""))     # event_inc_{k}
                row.append(cur_inc.get(k, ""))    # active_inc_{k}

            # Portfolio
            for pk in port_keys:
                cat, subk = pk.split(".", 1)
                v = _port_event_value(ev_port, cat, subk)
                row.append("" if v is None else v)                      # event_port_{pk}
                row.append(_port_value(cur_port, cat, subk, ""))        # active_port_{pk}
 
            writer.writerow(row)

    debug(VVERBOSE,
          "Dumped {} events (+baseline) to {}",
          len(data.get("life_events", [])), csv_path)

