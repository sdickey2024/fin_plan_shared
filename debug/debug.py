import csv
import inspect
import pprint
from datetime import date

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

    import csv

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
    header = (
        ["date", "event"]
        + ass_keys
        + exp_keys
        + inc_keys
        + port_keys
    )

    # 3) Open CSV and write
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        # --- Baseline row ---
        # Use data.get("start_date") or today’s date
        base_date = data.get("start_date", date.today().isoformat())
        base_event = "Baseline"
        row = [base_date, base_event]

        # assumptions
        for k in ass_keys:
            row.append(data["assumptions"].get(k, ""))

        # expenses
        for k in exp_keys:
            row.append(data["expenses"]["breakdown"].get(k, ""))

        # income
        for k in inc_keys:
            row.append(data["income"].get(k, ""))

        # portfolio
        for pk in port_keys:
            cat, subk = pk.split(".", 1)
            row.append(port_b.get(cat, {}).get(subk, ""))

        writer.writerow(row)

        # --- One row per event ---
        for ev in data.get("life_events", []):
            ev_date = ev.get("date", "")
            ev_name = ev.get("event", "")
            row = [ev_date, ev_name]

            # assumptions
            ev_ass = ev.get("updated_assumptions", {})
            for k in ass_keys:
                row.append(ev_ass.get(k, data["assumptions"].get(k, "")))

            # expenses
            ev_exp = ev.get("updated_expenses", {}).get("breakdown", {})
            for k in exp_keys:
                row.append(ev_exp.get(k, data["expenses"]["breakdown"].get(k, "")))

            # income
            ev_inc = ev.get("updated_income", {})
            for k in inc_keys:
                row.append(ev_inc.get(k, data["income"].get(k, "")))

            # portfolio
            ev_port = ev.get("updated_portfolio", {}).get("breakdown", {})
            for pk in port_keys:
                cat, subk = pk.split(".", 1)
                row.append(ev_port.get(cat, {}).get(subk,
                           port_b.get(cat, {}).get(subk, "")))

            writer.writerow(row)

    debug(VVERBOSE,
          "Dumped %d events (+baseline) to %s",
          len(data.get("life_events", [])), csv_path)

