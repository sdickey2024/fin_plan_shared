from datetime import datetime
from debug import *

def normalize_user_data_events(data):
    """
    Mutates `data` in place so that every life event has a full set of:
      - updated_expenses.breakdown
      - updated_income
      - updated_portfolio.breakdown
      - updated_assumptions

    Steps:
    1) Verify life_events are in ascending date order.
    2) Gather baseline keys for each category.
    3) Walk through events in order, carrying forward a 'current_state'
       for each category and writing back a fully-populated override block.
    """
    events = data.get("life_events", [])
    # 1) Validate chronological order
    dates = [e["date"] for e in events]
    if dates != sorted(dates, key=lambda d: datetime.strptime(d, "%Y-%m-%d")):
        raise ValueError("life_events must be in ascending date order")

    # 2) Baseline keys
    # Expenses
    base_exp = data["expenses"].setdefault("breakdown", {})
    exp_keys = set(base_exp.keys())
    # Income
    base_inc = data.setdefault("income", {})
    inc_keys = set(base_inc.keys())
    # Portfolio (nested)
    base_port = data["portfolio"].setdefault("breakdown", {})
    port_keys = { cat: set(sub.keys()) 
                  for cat, sub in base_port.items() }
    # Assumptions
    base_ass = data.setdefault("assumptions", {})
    ass_keys = set(base_ass.keys())

    # If any event introduces brand-new keys, zero-init in baseline
    for ev in events:
        for k in ev.get("updated_expenses", {}).get("breakdown", {}):
            if k not in exp_keys:
                base_exp[k] = 0.0
                exp_keys.add(k)
        for k in ev.get("updated_income", {}):
            if k not in inc_keys:
                base_inc[k] = 0.0
                inc_keys.add(k)
        for cat, upd in ev.get("updated_portfolio", {}).get("breakdown", {}).items():
            if cat not in port_keys:
                base_port[cat] = {}
                port_keys[cat] = set()
            for subk in upd:
                if subk not in port_keys[cat]:
                    base_port[cat][subk] = 0.0
                    port_keys[cat].add(subk)
        for k in ev.get("updated_assumptions", {}):
            if k not in ass_keys:
                base_ass[k] = 0.0
                ass_keys.add(k)

    # 3) Now walk events to fill out full snapshots
    curr_exp   = dict(base_exp)
    curr_inc   = dict(base_inc)
    curr_port  = {cat: dict(sub) for cat, sub in base_port.items()}
    curr_ass   = dict(base_ass)

    for ev in events:
        # EXPENSES
        ue = ev.setdefault("updated_expenses", {})
        ub = ue.setdefault("breakdown", {})
        # Merge: apply overrides
        curr_exp.update({k: float(v) for k, v in ub.items()})
        # Now write back a **complete** breakdown
        ev["updated_expenses"]["breakdown"] = {k: curr_exp[k] for k in exp_keys}
        # Also carry forward total_tax_rate if present
        if "total_tax_rate" in ue:
            curr_total = float(ue["total_tax_rate"])
        else:
            curr_total = float(data["expenses"].get("total_tax_rate", 0.0))
        ev["updated_expenses"]["total_tax_rate"] = curr_total
        data["expenses"]["total_tax_rate"] = curr_total

        # INCOME
        ui = ev.setdefault("updated_income", {})
        curr_inc.update({k: float(v) for k, v in ui.items()})
        ev["updated_income"] = {k: curr_inc[k] for k in inc_keys}

        # PORTFOLIO
        up = ev.setdefault("updated_portfolio", {})
        pb = up.setdefault("breakdown", {})
        # Apply overrides
        for cat, subd in pb.items():
            if cat not in curr_port:
                curr_port[cat] = {}
            for sk, sv in subd.items():
                curr_port[cat][sk] = float(sv)
        # Write back full nested snapshot
        new_pb = {}
        for cat, subvals in curr_port.items():
            new_pb[cat] = {sk: subvals.get(sk, 0.0) for sk in port_keys.get(cat, [])}
        ev["updated_portfolio"]["breakdown"] = new_pb

        # ASSUMPTIONS
        ua = ev.setdefault("updated_assumptions", {})
        curr_ass.update({k: float(v) for k, v in ua.items()})
        ev["updated_assumptions"] = {k: curr_ass[k] for k in ass_keys}

    # dump all the data
    dump_data(data)
        
    # 4) Done — data["life_events"] now contains fully populated snapshots
    return data
