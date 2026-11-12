"""Merge documented candidates into a private frame; never grant permissions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pydantic import ValidationError
from tapi_gate0.discovery_batch import BatchManifest


def merge_candidates(base: BatchManifest, candidates: BatchManifest) -> BatchManifest:
    sources = list(base.sources)
    by_handle = {s.username.casefold(): s for s in sources}
    for source in candidates.sources:
        if (source.status != "candidate" or source.approval_reference or
                source.expires_at or source.allowed_operations):
            raise ValueError("CANDIDATE_FRAME_CANNOT_CONTAIN_APPROVALS")
        prior = by_handle.get(source.username.casefold())
        if prior is not None:
            if prior.expected_ig_id and source.expected_ig_id and prior.expected_ig_id != source.expected_ig_id:
                raise ValueError("CANDIDATE_ID_CONFLICT")
            continue  # Preserve private decisions and grants exactly.
        sources.append(source)
        by_handle[source.username.casefold()] = source
    return BatchManifest(schema_version=base.schema_version, sources=sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline candidate intake, no permissions")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        root = (Path(__file__).resolve().parents[1] / "artifacts" / "private").resolve()
        if not args.output.resolve().is_relative_to(root) or args.output.suffix.lower() != ".json":
            raise ValueError("OUTPUT_MUST_BE_PRIVATE_JSON")
        base = BatchManifest.model_validate_json(args.base.read_text(encoding="utf-8"))
        candidates = BatchManifest.model_validate_json(args.candidates.read_text(encoding="utf-8"))
        merged = merge_candidates(base, candidates)
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(merged.model_dump_json(indent=2))
        print(json.dumps({"status":"CANDIDATE_FRAME_EXPANDED", "sources_before":len(base.sources),
            "sources_after":len(merged.sources), "approved":sum(s.status=="approved" for s in merged.sources),
            "grants_created":0, "external_data_accessed":False, "manifest_sha256":merged.fingerprint()}))
        return 0
    except (OSError, ValueError, ValidationError):
        print(json.dumps({"status":"BLOCKED", "code":"INVALID_CANDIDATE_FRAME_OR_OUTPUT", "external_data_accessed":False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
