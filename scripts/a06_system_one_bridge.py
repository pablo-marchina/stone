"""Offline A06→System One evidence handoff for pinned, synthetic shared AV.

Never decodes input media, downloads weights, reads operational rights/secrets,
touches the tenant database, or writes a canonical scientific assessment.
An output is created only under artifacts/private with explicit input SHA,
clean expected Git HEAD and an unused output name. Failure emits no raw data.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .a00_baseline import check_checkout
from tapi_gate0.multimodal_system_one_bridge import bridge_verified_synthetic_report

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT_BYTES = 2_000_000
MAX_OUTPUT_BYTES = 2_000_000
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.json\Z")
HEX = re.compile(r"[a-f0-9]{64}\Z")


def _private_file(root: Path, name: str) -> Path:
    if not NAME.fullmatch(name):
        raise ValueError("A06_PRIVATE_NAME_INVALID")
    folder = root / "artifacts" / "private"
    if (not folder.is_dir() or folder.is_symlink()
            or folder.resolve(strict=True) != folder.absolute()):
        raise ValueError("A06_PRIVATE_FOLDER_REQUIRED")
    path = folder / name
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError("A06_PRIVATE_PATH_INVALID")
    return path


def _read_pinned(path: Path, digest: str) -> dict:
    if not HEX.fullmatch(digest):
        raise ValueError("A06_INPUT_PIN_INVALID")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise ValueError("A06_INPUT_NOT_REGULAR")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(MAX_INPUT_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_INPUT_BYTES or sha256(raw).hexdigest() != digest:
        raise ValueError("A06_INPUT_SHA256_MISMATCH")
    return json.loads(raw.decode("utf-8"))


def _write_new(path: Path, report: dict) -> str:
    raw = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if not 0 < len(raw) <= MAX_OUTPUT_BYTES:
        raise ValueError("A06_OUTPUT_SIZE_INVALID")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        # A failed write must not retain a truncated "completed" receipt.
        path.unlink(missing_ok=True)
        raise
    return sha256(raw).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-head", required=True)
    p.add_argument("--input-name", required=True)
    p.add_argument("--input-sha256", required=True)
    p.add_argument("--output-name", required=True)
    args = p.parse_args(argv)
    try:
        if not re.fullmatch(r"[a-f0-9]{40}", args.expected_head):
            raise ValueError("A06_HEAD_INVALID")
        check_checkout(ROOT, args.expected_head)
        source = _private_file(ROOT, args.input_name)
        destination = _private_file(ROOT, args.output_name)
        if source == destination or destination.exists():
            raise ValueError("A06_OUTPUT_ALREADY_EXISTS")
        raw_report = _read_pinned(source, args.input_sha256)
        candidate = bridge_verified_synthetic_report(raw_report)
        check_checkout(ROOT, args.expected_head)
        digest = _write_new(destination, candidate)
        print(json.dumps({
            "status": candidate["status"],
            "schema_version": candidate["schema_version"],
            "source_case_count": candidate["source_case_count"],
            "text_observation_count": candidate["text_observation_count"],
            "output_name": args.output_name,
            "output_sha256": digest,
            "scientific_admissions": 0,
            "production_approved": False,
        }, sort_keys=True))
        return 0
    except Exception:
        # A pinned local report may contain media/creator metadata. Do not
        # expose validation traceback, paths or raw external payloads.
        print(json.dumps({
            "status": "BLOCKED", "code": "A06_E1_SYNTHETIC_BRIDGE_BLOCKED",
            "scientific_admissions": 0, "production_approved": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
