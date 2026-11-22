"""Dependency-free, offline Python 3.11 syntax preflight for Stone.

This scan parses source code only. It does not import modules, contact services,
access secrets, use a database, or authorize any release gate.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

SCAN_DIRS = ("src/tapi_gate0", "scripts", "migrations/versions", "tests")
REQUIRED = (
    "src/tapi_gate0/creative_reference_pep_a05.py",
    "src/tapi_gate0/agent_api_e1.py",
    "src/tapi_gate0/secure_api.py",
)


def audit(root: Path, *, directories=SCAN_DIRS, required=REQUIRED) -> dict:
    root = Path(root).resolve()
    errors = []
    checked = 0
    for relative in required:
        if not (root / relative).is_file():
            errors.append({"path": relative, "code": "SOURCE_REQUIRED_MISSING"})
    for relative in directories:
        folder = root / relative
        if not folder.is_dir():
            errors.append({"path": relative, "code": "SOURCE_DIRECTORY_MISSING"})
            continue
        for source in sorted(folder.rglob("*.py")):
            checked += 1
            try:
                ast.parse(source.read_bytes(), filename=str(source),
                          feature_version=(3, 11))
            except SyntaxError as exc:
                errors.append({
                    "path": source.relative_to(root).as_posix(),
                    "code": "SOURCE_SYNTAX_INVALID",
                    "line": exc.lineno,
                    "column": exc.offset,
                })
            except (OSError, ValueError, UnicodeError):
                errors.append({
                    "path": source.relative_to(root).as_posix(),
                    "code": "SOURCE_UNREADABLE",
                })
    if checked == 0:
        errors.append({"path": ".", "code": "SOURCE_DISCOVERY_EMPTY"})
    return {
        "schema_version": "stone-python-source-preflight.v1",
        "status": "PASS" if not errors else "BLOCKED",
        "python_grammar": "3.11",
        "files_checked": checked,
        "errors": errors,
        "deployment_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    result = audit(args.root)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
