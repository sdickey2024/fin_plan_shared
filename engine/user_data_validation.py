# data/user_data_validation.py

from __future__ import annotations
import json
import os
import sys

from json.decoder import JSONDecodeError

SCHEMA_FIELDS = [
    "person", "expenses", "portfolio", "life_events", "assumptions"
]

REQUIRED_EXPENSE_FIELDS = ["breakdown"]
REQUIRED_PERSON_FIELDS = ["name", "current_age"]
REQUIRED_ASSUMPTIONS = ["expected_return", "variance", "inflation"]


# -----------------------------------------------------------------------------
# File type discrimination (NO heuristics)
# -----------------------------------------------------------------------------
#
# We do *not* infer file type from other keys. The file declares its intent via
# schema_type, and we validate contents accordingly.
#
#   Base file:     { "schema_type": "user_base", ... }
#   Scenario file: { "schema_type": "scenario",  ... }
#
SCHEMA_TYPE_FIELD = "schema_type"
SCHEMA_TYPE_USER_BASE = "user_base"
SCHEMA_TYPE_SCENARIO = "scenario"
ALLOWED_SCHEMA_TYPES = {SCHEMA_TYPE_USER_BASE, SCHEMA_TYPE_SCENARIO}


def _get_schema_type(obj: object) -> str | None:
    if not isinstance(obj, dict):
        return None
    st = obj.get(SCHEMA_TYPE_FIELD)
    return st if isinstance(st, str) else None

# -----------------------------------------------------------------------------
# Life-event structural checks
# -----------------------------------------------------------------------------

# Keys allowed directly under updated_expenses.
_UE_RESERVED_KEYS = {
    "breakdown",
    "total_tax_rate",
    "classification",
    "spending_policy",
}


def _validate_updated_expenses_shape(updated_expenses, where: str, errors: list[str]):
    """Enforce: updated_expenses MUST be an object containing a breakdown object.

    Rule we want:
      updated_expenses: { breakdown: { <key>: <value>, ... }, ... }

    This flags the common mistake of putting expense keys directly under
    updated_expenses (shorthand), which the engine may not apply.
    """
    if not isinstance(updated_expenses, dict):
        errors.append(f"{where}: updated_expenses must be an object")
        return

    if "breakdown" not in updated_expenses:
        errors.append(
            f"{where}: updated_expenses is missing required 'breakdown' object "
            "(use updated_expenses: { breakdown: { ... } })"
        )
        return

    bd = updated_expenses.get("breakdown")
    if not isinstance(bd, dict):
        errors.append(f"{where}: updated_expenses.breakdown must be an object")

    # Anything non-reserved at this level is almost certainly a mistake.
    extras = [k for k in updated_expenses.keys() if k not in _UE_RESERVED_KEYS]
    if extras:
        errors.append(
            f"{where}: updated_expenses contains expense keys at the wrong level: {extras}. "
            "Move them under updated_expenses.breakdown."
        )


def validate_life_events(life_events, context: str) -> list[str]:
    """Return a list of validation error strings for life_events."""
    errors: list[str] = []
    if life_events is None:
        return errors
    if not isinstance(life_events, list):
        return [f"{context}: life_events must be a list"]

    for idx, ev in enumerate(life_events):
        if not isinstance(ev, dict):
            errors.append(f"{context}: life_events[{idx}] must be an object")
            continue

        name = ev.get("event") or ev.get("name") or f"life_events[{idx}]"
        where = f"{context}: {name}"

        if "updated_expenses" in ev:
            _validate_updated_expenses_shape(ev.get("updated_expenses"), where, errors)

    return errors


def validate_base_data(base: dict, base_path: str = "(base)") -> list[str]:
    """Return a list of validation errors for a base file (empty == ok)."""
    errors: list[str] = []
    if not isinstance(base, dict):
        return [f"{base_path}: base JSON must be an object"]

    st = _get_schema_type(base)
    if st is None:
        errors.append(
            f"{base_path}: missing required top-level '{SCHEMA_TYPE_FIELD}' "
            f"(expected '{SCHEMA_TYPE_USER_BASE}')"
        )
        return errors
    if st != SCHEMA_TYPE_USER_BASE:
        errors.append(
            f"{base_path}: {SCHEMA_TYPE_FIELD} is '{st}', expected '{SCHEMA_TYPE_USER_BASE}'"
        )
        return errors
    
    missing = []
    for key in ("person", "expenses", "income", "portfolio", "assumptions"):
        if key not in base:
            missing.append(key)
    if missing:
        errors.append(f"{base_path}: missing top-level fields: {missing}")
        return errors

    if "name" not in base.get("person", {}):
        errors.append(f"{base_path}: person missing 'name'")

    person = base.get("person", {})
    has_birthdate = "birthdate" in person
    has_current_age = "current_age" in person
    if not has_birthdate and not has_current_age:
        errors.append(f"{base_path}: person must include either 'birthdate' or 'current_age'")
    if has_birthdate and has_current_age:
        errors.append(f"{base_path}: person must not include both 'birthdate' and 'current_age'")

    exp = base.get("expenses", {})
    if "breakdown" not in exp or not isinstance(exp.get("breakdown"), dict):
        errors.append(f"{base_path}: expenses.breakdown missing or invalid")

    if not isinstance(base.get("income"), dict):
        errors.append(f"{base_path}: income must be an object")

    port = base.get("portfolio", {})
    if "breakdown" not in port or not isinstance(port.get("breakdown"), dict):
        errors.append(f"{base_path}: portfolio.breakdown missing or invalid")

    assump_base = base.get("assumptions")
    if not isinstance(assump_base, dict):
        errors.append(f"{base_path}: assumptions must be an object")
    else:
        for af in ("expected_return", "variance", "inflation"):
            if af not in assump_base:
                errors.append(f"{base_path}: assumptions missing '{af}'")

    errors.extend(validate_life_events(base.get("life_events", []), base_path))
    return errors


def validate_scenario_data(scenario: dict, scenario_path: str = "(scenario)") -> list[str]:
    """Return a list of validation errors for a scenario file (empty == ok)."""
    errors: list[str] = []
    if not isinstance(scenario, dict):
        return [f"{scenario_path}: scenario JSON must be an object"]

    st = _get_schema_type(scenario)
    if st is None:
        errors.append(
            f"{scenario_path}: missing required top-level '{SCHEMA_TYPE_FIELD}' "
            f"(expected '{SCHEMA_TYPE_SCENARIO}')"
        )
        return errors
    if st != SCHEMA_TYPE_SCENARIO:
        errors.append(
            f"{scenario_path}: {SCHEMA_TYPE_FIELD} is '{st}', expected '{SCHEMA_TYPE_SCENARIO}'"
        )
        return errors

    missing = []
    for key in ("description", "life_events"):
        if key not in scenario:
            missing.append(key)
    if missing:
        errors.append(f"{scenario_path}: missing top-level fields: {missing}")
        return errors

    if not isinstance(scenario.get("life_events"), list):
        errors.append(f"{scenario_path}: life_events must be a list")

    if "assumptions" in scenario:
        assump = scenario.get("assumptions")
        if not isinstance(assump, dict):
            errors.append(f"{scenario_path}: assumptions must be an object when present")
        else:
            for af in ("expected_return", "variance", "inflation"):
                if af not in assump:
                    errors.append(
                        f"{scenario_path}: assumptions missing '{af}' (scenario overrides must be complete)"
                    )

    errors.extend(validate_life_events(scenario.get("life_events", []), scenario_path))
    return errors


def validate_json_schema(data):
    missing = [field for field in SCHEMA_FIELDS if field not in data]
    if missing:
        raise ValueError(f"Missing top-level fields: {missing}")

    for field in REQUIRED_PERSON_FIELDS:
        if field not in data["person"]:
            raise ValueError(f"Missing person field: {field}")

    for field in REQUIRED_EXPENSE_FIELDS:
        if field not in data["expenses"]:
            raise ValueError(f"Missing expenses field: {field}")

    for field in REQUIRED_ASSUMPTIONS:
        if field not in data["assumptions"]:
            raise ValueError(f"Missing assumption field: {field}")

    if not isinstance(data["life_events"], list):
        raise ValueError("life_events should be a list")


def validate_user_data(base_filepath, scenario_filepath):
    """
    Validate two JSON files:
      1) base_filepath must contain: person, expenses, income, portfolio
      2) scenario_filepath must contain: description, life_events, assumptions
    Returns True if both are syntactically valid and pass their schema checks.
    """

    def load_and_parse(path):
        if not os.path.exists(path):
            print(f"ERROR: File {path} does not exist.")
            return None
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except JSONDecodeError as e:
            line = e.lineno
            print(f"ERROR: JSON syntax error in {path} on line {line}: {e.msg}")
            with open(path, 'r') as f:
                lines = f.readlines()
                if 0 < line <= len(lines):
                    print(f"--> {lines[line-1].rstrip()}")
            return None

    base = load_and_parse(base_filepath)
    if base is None:
        return False

    scenario = load_and_parse(scenario_filepath)
    if scenario is None:
        return False

    base_errors = validate_base_data(base, base_filepath)
    if base_errors:
        for e in base_errors:
            print("ERROR:", e)
        return False

    scen_errors = validate_scenario_data(scenario, scenario_filepath)
    if scen_errors:
        for e in scen_errors:
            print("ERROR:", e)
        return False

    return True

def validate_files_in_dir(data_dir: str) -> tuple[list[str], list[str]]:
    """Validate all *.json files under a data directory.

    Current layout keeps JSON in subdirectories (e.g. data/user_base and
    data/scenarios). Older versions kept JSON directly under data/. The
    GUI's "Tools -> Validate Data Files" expects this function to find and
    validate both layouts.

    Classification rule (NO heuristics):
      - schema_type == "user_base"  -> validate_base_data()
      - schema_type == "scenario"   -> validate_scenario_data()
      - missing/unknown             -> error

    Returns:
      (ok_paths, error_messages)
    """
    ok: list[str] = []
    errs: list[str] = []

    if not os.path.isdir(data_dir):
        return ([], [f"ERROR: Data directory does not exist: {data_dir}"])

    # Discover JSON files.
    # - Always include any *.json directly under data_dir (legacy layout)
    # - Also include common subdirs used by the current layout.
    paths: list[str] = []

    def add_json_files(dir_path: str):
        if not os.path.isdir(dir_path):
            return
        for f in os.listdir(dir_path):
            if f.lower().endswith(".json"):
                paths.append(os.path.join(dir_path, f))

    add_json_files(data_dir)
    add_json_files(os.path.join(data_dir, "user_base"))
    add_json_files(os.path.join(data_dir, "scenarios"))

    paths = sorted(set(paths))

    def load(path):
        try:
            with open(path, "r") as fp:
                return json.load(fp)
        except JSONDecodeError as e:
            errs.append(f"ERROR: {path}: JSON syntax error line {e.lineno}: {e.msg}")
            return None
        except Exception as e:
            errs.append(f"ERROR: {path}: failed to read: {e}")
            return None

    for p in paths:
        data = load(p)
        if data is None:
            continue

        st = _get_schema_type(data)
        if st not in ALLOWED_SCHEMA_TYPES:
            if st is None:
                problems = [
                    f"{p}: missing required top-level '{SCHEMA_TYPE_FIELD}' "
                    f"(expected one of: {sorted(ALLOWED_SCHEMA_TYPES)})"
                ]
            else:
                problems = [
                    f"{p}: invalid {SCHEMA_TYPE_FIELD} '{st}' "
                    f"(expected one of: {sorted(ALLOWED_SCHEMA_TYPES)})"
                ]
        elif st == SCHEMA_TYPE_USER_BASE:
            problems = validate_base_data(data, p)
        else:  # st == SCHEMA_TYPE_SCENARIO
            problems = validate_scenario_data(data, p)

        if problems:
            errs.extend([msg if "ERROR" in msg else f"ERROR: {msg}" for msg in problems])
        else:
            ok.append(p)

    return (ok, errs)

if __name__ == "__main__":
    # Usage:
    #   python user_data_validation.py <base.json> <scenario.json>
    base_path = sys.argv[1] if len(sys.argv) > 1 else "data/user_base/example_user.json"
    scenario_path = sys.argv[2] if len(sys.argv) > 2 else "data/scenarios/scenario_1_market_crash.json"
    result = validate_user_data(base_path, scenario_path)
    sys.exit(0 if result else 1)

