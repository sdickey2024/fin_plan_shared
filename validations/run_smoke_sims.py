#!/usr/bin/env python3
"""
Runtime smoke tests for fin_plan.

These tests execute a small set of representative runs and verify:
  - command exits successfully
  - something new was written to out/ (CSV at minimum)

Why "smoke":
  - we don't assert exact numerical results (those are brittle)
  - we assert the program runs, and outputs are produced
  - intended to catch pathing, schema, multiprocessing, and regression crashes

Run:
  python validations/run_smoke_sims.py
"""

from __future__ import annotations

import os
import sys
import time
import glob
import subprocess
from dataclasses import dataclass
from typing import List


# Ensure project root is on sys.path when run as a script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


OUT_DIR = os.path.join(PROJECT_ROOT, "out")
RUNNER = os.path.join(PROJECT_ROOT, "run_all_simulations.py")


@dataclass
class SmokeCase:
    name: str
    args: List[str]
    require_csv: bool = True
    require_png: bool = False  # keep loose by default; can tighten later


def _find_new_files_since(ts: float) -> List[str]:
    if not os.path.isdir(OUT_DIR):
        return []
    new_files: List[str] = []
    for p in glob.glob(os.path.join(OUT_DIR, "*")):
        try:
            st = os.stat(p)
        except OSError:
            continue
        # allow a small clock skew / FS timestamp granularity
        if st.st_mtime >= (ts - 0.5):
            new_files.append(p)
    return sorted(set(new_files))


def _run_case(case: SmokeCase) -> tuple[bool, str]:
    cmd = [sys.executable, RUNNER] + case.args
    start = time.time()

    # Ensure out dir exists
    os.makedirs(OUT_DIR, exist_ok=True)

    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    new_files = _find_new_files_since(start)
    new_csv = [p for p in new_files if p.lower().endswith(".csv")]
    new_png = [p for p in new_files if p.lower().endswith(".png")]

    if proc.returncode != 0:
        return (
            False,
            "Non-zero exit code.\n"
            f"cmd: {' '.join(cmd)}\n"
            f"exit: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n",
        )

    if case.require_csv and not new_csv:
        return (
            False,
            "No new CSV outputs detected.\n"
            f"cmd: {' '.join(cmd)}\n"
            f"new_files:\n" + "\n".join(new_files[:50]) + ("\n..." if len(new_files) > 50 else "") + "\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n",
        )

    if case.require_png and not new_png:
        return (
            False,
            "No new PNG outputs detected.\n"
            f"cmd: {' '.join(cmd)}\n"
            f"new_files:\n" + "\n".join(new_files[:50]) + ("\n..." if len(new_files) > 50 else "") + "\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n",
        )

    detail = (
        f"cmd: {' '.join(cmd)}\n"
        f"new_csv: {len(new_csv)} new_png: {len(new_png)} new_files: {len(new_files)}"
    )
    return True, detail


def main() -> int:
    cases: List[SmokeCase] = [
        SmokeCase(
            name="Example User + base retirement (montecarlo off)",
            args=["--user=example_user.json", "--file=scenario_base_retirement_.json", "--montecarlo=off", "-d", "warn"],
        ),
        SmokeCase(
            name="Example user + base retirement (montecarlo off)",
            args=["--user=example_user.json", "--file=scenario_base_retirement_.json", "--montecarlo=off", "-d", "warn"],
        ),
        SmokeCase(
            name="Example User + market crash (montecarlo sim)",
            args=["--user=example_user.json", "--file=scenario_1_market_crash.json", "--montecarlo=sim", "-d", "warn"],
        ),
        SmokeCase(
            name="Example User + parallel run (2 scenarios, jobs=2, montecarlo off)",
            args=[
                "--user=example_user.json",
                "--file=scenario_1_market_crash.json",
                "--file=scenario_long_term_care.json",
                "--montecarlo=off",
                "--jobs=2",
                "-d",
                "warn",
            ],
        ),
    ]

    failures = 0
    print("== fin_plan runtime smoke tests ==")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Runner: {RUNNER}")
    print(f"Out dir: {OUT_DIR}")
    print()

    for case in cases:
        print(f"RUN: {case.name}")
        ok, detail = _run_case(case)
        if ok:
            print(f"PASS: {case.name}")
            print(f"  {detail}")
        else:
            failures += 1
            print(f"FAIL: {case.name}")
            print(detail.replace("\n", "\n  "))
        print()

    print(f"Summary: {len(cases) - failures} passed, {failures} failed, {len(cases)} total")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
