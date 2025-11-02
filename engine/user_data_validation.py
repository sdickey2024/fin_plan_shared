# data/user_data_validation.py

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

    # ---- Validate base schema ----
    missing = []
    for key in ("person", "expenses", "income", "portfolio"):
        if key not in base:
            missing.append(key)
    if missing:
        print(f"ERROR: Base file is missing top-level fields: {missing}")
        return False

    # person sub-fields
    for pf in ("name", "current_age"):
        if pf not in base["person"]:
            print(f"ERROR: Base.person missing '{pf}'")
            return False

    # expenses sub-fields
    exp = base["expenses"]
    if "breakdown" not in exp:
        print("ERROR: Base.expenses missing 'breakdown'")
        return False

    # income should be a dict (we’ll assume any fields ok)
    if not isinstance(base["income"], dict):
        print("ERROR: Base.income must be an object")
        return False

    # portfolio
    port = base["portfolio"]
    if "breakdown" not in port or not isinstance(port["breakdown"], dict):
        print("ERROR: Base.portfolio missing or invalid 'breakdown'")
        return False

    # ---- Validate scenario schema ----
    missing = []
    for key in ("description", "life_events", "assumptions"):
        if key not in scenario:
            missing.append(key)
    if missing:
        print(f"ERROR: Scenario file is missing top-level fields: {missing}")
        return False

    # life_events must be a list
    if not isinstance(scenario["life_events"], list):
        print("ERROR: Scenario.life_events must be a list")
        return False

    # assumptions sub-fields
    assump = scenario["assumptions"]
    for af in ("expected_return", "variance", "inflation"):
        if af not in assump:
            print(f"ERROR: Scenario.assumptions missing '{af}'")
            return False

    print("User data validation successful.")
    return True

if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "data/user_data.json"
    result = validate_user_data(file_path)
    sys.exit(0 if result else 1)

