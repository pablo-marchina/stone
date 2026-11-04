"""IMP-167/170: curate source candidates and preview technically eligible metadata.

The only permitted persistent output is an explicit local, private audit report.
Corpus DB is not written; register/create grants only through existing admin APIs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from pydantic import ValidationError
from tapi_gate0.connectors import ConnectorError, OfficialHttp
from tapi_gate0.mpe_evidence import FirstEligibleSampler
from tapi_gate0.mpe_sources import SourceGateError, load_frame, authorized_source, audit_source_frame

DEFAULT_VIEWER = "17841459971757521"
PRIVATE_OUTPUT_DIR = Path("artifacts/private/mpe_corpus")


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def main(argv=None, *, http=None):
    parser = argparse.ArgumentParser(description="Strictly gated MPE candidate corpus pilot")
    parser.add_argument("--frame", required=True, help="Source frame v2 (or legacy v1); read-only audit by default")
    parser.add_argument("--execute", action="store_true", help="Explicitly perform one bounded read")
    parser.add_argument("--source", help="Known candidate username in the frame")
    parser.add_argument("--evidence-dir", default="artifacts/private/mpe_approvals")
    parser.add_argument("--viewer-id", default=DEFAULT_VIEWER)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--output-name", help="Optional private JSON filename; never overwritten")
    args = parser.parse_args(argv)
    try:
        frame = load_frame(Path(args.frame))
    except (OSError, ValueError, ValidationError, SourceGateError):
        # Never show raw JSON/paths from an untrusted manifest.
        _print({"status": "BLOCKED", "code": "INVALID_SOURCE_FRAME"})
        return 2
    if not args.execute:
        _print({"status": "SOURCE_FRAME_AUDIT", **audit_source_frame(frame)})
        return 0
    if not args.source:
        _print({"status": "BLOCKED", "code": "EXPLICIT_SOURCE_REQUIRED"})
        return 2
    if os.getenv("TAPI_OFFICIAL_METADATA_READS") != "1":
        _print({"status": "BLOCKED", "code": "OFFICIAL_READS_DISABLED"})
        return 2
    if os.getenv("TAPI_ZERO_BILLING_CONFIRMED") != "1":
        _print({"status": "BLOCKED", "code": "PROVIDER_ZERO_BILLING_NOT_CONFIRMED"})
        return 2
    token = os.getenv("TAPI_INSTAGRAM_ACCESS_TOKEN", "")
    if len(token) < 10:
        _print({"status": "BLOCKED", "code": "CREDENTIAL_MISSING"})
        return 2
    matched = [x for x in frame.sources if x.username.casefold() == args.source.casefold()]
    if len(matched) != 1:
        _print({"status": "BLOCKED", "code": "SOURCE_NOT_IN_FRAME"})
        return 2
    try:
        approval = authorized_source(matched[0], Path(args.evidence_dir))
    except SourceGateError as exc:
        _print({"status": "BLOCKED", "code": exc.code})
        return 2
    if args.output_name and not re.fullmatch(r"mpe-[a-z0-9_-]{5,80}\.json", args.output_name):
        _print({"status": "BLOCKED", "code": "INVALID_PRIVATE_OUTPUT_NAME"})
        return 2
    if args.output_name:
        output_path = PRIVATE_OUTPUT_DIR / args.output_name
        if output_path.exists() or output_path.is_symlink():
            _print({"status": "BLOCKED", "code": "PRIVATE_REPORT_ALREADY_EXISTS"})
            return 2
    owns = http is None
    transport = http or OfficialHttp()
    try:
        report = FirstEligibleSampler(transport).scan(args.viewer_id, token, approval,
                                                 limit=args.limit, max_pages=args.max_pages)
    except ConnectorError as exc:
        _print({"status": "FAILED", "code": exc.code})
        return 1
    finally:
        if owns:
            transport.close()
    if args.output_name:
        output_directory = PRIVATE_OUTPUT_DIR
        if output_directory.is_symlink():
            _print({"status": "BLOCKED", "code": "UNSAFE_PRIVATE_OUTPUT_DIR"})
            return 2
        output_directory.mkdir(parents=True, exist_ok=True)
        out = output_directory / args.output_name
        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        try:
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
        except FileExistsError:
            _print({"status": "BLOCKED", "code": "PRIVATE_REPORT_ALREADY_EXISTS"})
            return 2
        summary = {"status": "PRIVATE_EVIDENCE_SAVED", "source": report["source"]["username"],
                   "technically_eligible_14d": report["counts"]["technically_eligible_14d"],
                   "scientifically_eligible_14d": 0,
                   "pages_examined": report["pages_examined"],
                   "report_path": str(out), "report_sha256": __import__("hashlib").sha256(payload).hexdigest(),
                   "corpus_posts_persisted": 0}
        _print(summary)
    else:
        # Don't accidentally echo potentially sensitive third-party media list.
        _print({"status": "EVIDENCE_PILOT_READ", "source": report["source"],
                "counts": report["counts"], "pages_examined": report["pages_examined"],
                "another_page_possible": report["another_page_possible"],
                "scientific_eligibility_status": "UNREVIEWED_CONTENT",
                "corpus_posts_persisted": 0, "record_exported": False})
    return 0


if __name__ == "__main__":
    sys.exit(main())
