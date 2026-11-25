#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PWD}/src${PYTHONPATH:+:${PYTHONPATH}}"
python scripts/documentation_catalog.py check
python scripts/check_gate0.py
python scripts/verify_zero_spend.py
python -m pytest -q
