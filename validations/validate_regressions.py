#!/usr/bin/env python3
"""
Regression validations for fin_plan.

Goals:
  - Do NOT modify production code just to "print something".
  - Exercise existing validators + assumptions about project layout.
  - Provide a repeatable, local, scriptable set of checks that can grow over time.

Run:
  python validations/validate_regressions.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, List


# Ensure project root is on sys.path when run as a script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from engine.user_data_validation import (  # noqa: E402
    validate_files_in_dir,
    validate_base_data,
    validate_scenario_data,
)


@dataclass
class TestResult:
    name: str
    ok: bool
    details: str = ""


def _fail(name: str, msg: str) -> TestResult:
    return TestResult(name=name, ok=False, details=msg)


def _pass(name: str, msg: str = "") -> TestResult:
    return TestResult(name=name, ok=True, details=msg)


def _assert(condition: bool, name: str, msg: str) -> TestResult | None:
    if not condition:
        return _fail(name, msg)
    return None


def test_validate_data_dir() -> TestResult:
    name = "validate_files_in_dir('data') returns zero errors"
    ok, errs = validate_files_in_dir("data")
    if errs:
        # Print only first 15 for readability
        preview = "\n".join(errs[:15])
        return _fail(
            name,
            f"Expected 0 errors, got {len(errs)}. First errors:\n{preview}",
        )
    if not ok:
        return _fail(name, "Expected some ok files, got 0.")
    return _pass(name, f"ok={len(ok)} errs={len(errs)}")


def test_scenario_wrong_schema_type() -> TestResult:
    name = "scenario validator fails when schema_type != 'scenario'"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        path = tf.name
        json.dump(
            {
                "schema_type": "user_base",  # intentionally wrong
                "schema_version": 1,
                "description": "bad scenario",
                "life_events": [],
            },
            tf,
            indent=2,
        )
    try:
        with open(path, "r") as f:
            obj = json.load(f)
        errs = validate_scenario_data(obj, path)
        if not errs:
            return _fail(name, "Expected errors but got none.")
        joined = "\n".join(errs)
        if "schema_type" not in joined:
            return _fail(name, f"Expected schema_type error. Got:\n{joined}")
        return _pass(name, "Got expected schema_type error.")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def test_base_missing_schema_type() -> TestResult:
    name = "base validator fails when schema_type is missing"
    obj = {
        # schema_type intentionally missing
        "person": {"name": "X", "current_age": 50},
        "expenses": {"breakdown": {}},
        "income": {},
        "portfolio": {"breakdown": {}},
        "assumptions": {"expected_return": 0.06, "variance": 0.02, "inflation": 0.025},
        "life_events": [],
    }
    errs = validate_base_data(obj, "(in-memory)")
    if not errs:
        return _fail(name, "Expected errors but got none.")
    joined = "\n".join(errs)
    if "schema_type" not in joined:
        return _fail(name, f"Expected schema_type error. Got:\n{joined}")
    return _pass(name, "Got expected missing schema_type error.")


def test_scenario_bad_life_events_type() -> TestResult:
    name = "scenario validator fails when life_events is not a list"
    obj = {
        "schema_type": "scenario",
        "schema_version": 1,
        "description": "bad life_events type",
        "life_events": {},  # intentionally wrong
    }
    errs = validate_scenario_data(obj, "(in-memory)")
    if not errs:
        return _fail(name, "Expected errors but got none.")
    joined = "\n".join(errs)
    # be flexible on exact wording, but ensure it mentions life_events and list
    if ("life_events" not in joined) or ("list" not in joined.lower()):
        return _fail(name, f"Expected life_events/list error. Got:\n{joined}")
    return _pass(name, "Got expected life_events type error.")


def run_all(tests: List[Callable[[], TestResult]]) -> int:
    results: List[TestResult] = []
    for t in tests:
        try:
            results.append(t())
        except Exception as e:
            results.append(_fail(t.__name__, f"Unhandled exception: {e}"))

    # Pretty print
    failed = [r for r in results if not r.ok]
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"{status}: {r.name}")
        if r.details:
            print(f"  {r.details}".replace("\n", "\n  "))

    print(f"\nSummary: {len(results) - len(failed)} passed, {len(failed)} failed, {len(results)} total")
    return 0 if not failed else 1


def main() -> int:
    tests = [
        test_validate_data_dir,
        test_scenario_wrong_schema_type,
        test_base_missing_schema_type,
        test_scenario_bad_life_events_type,
    ]
    return run_all(tests)


if __name__ == "__main__":
    raise SystemExit(main())
