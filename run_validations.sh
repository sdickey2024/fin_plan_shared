#!/usr/bin/env bash
#
# Run fin_plan regression validations.
#
# This script intentionally does NOT modify any project state.
# It exists to catch regressions in schema validation, directory layout,
# and assumptions about base/scenario structure.
#

set -euo pipefail

# Resolve project root (script may be run from anywhere)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

cd "${PROJECT_ROOT}"

echo "== fin_plan validation runner =="
echo "Project root: ${PROJECT_ROOT}"
echo

# Activate virtualenv if one exists (optional)
if [[ -f ".venv/bin/activate" ]]; then
    echo "Activating virtualenv: .venv"
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
elif [[ -f "venv/bin/activate" ]]; then
    echo "Activating virtualenv: venv"
    # shellcheck disable=SC1091
    source "venv/bin/activate"
else
    echo "No virtualenv detected (using system Python)"
fi

echo
echo "Running schema/structure regression validations..."
echo

python validations/validate_regressions.py

rc=$?
if [[ $rc -ne 0 ]]; then
    echo
    echo "❌ Schema/structure validations failed (exit code $rc)"
    exit $rc
fi

echo
echo "Running runtime smoke simulations..."
echo
python validations/run_smoke_sims.py
rc=$?

echo
if [[ $rc -eq 0 ]]; then
    echo "✅ VALIDATIONS PASSED"
else
    echo "❌ VALIDATIONS FAILED (exit code $rc)"
fi

exit $rc
