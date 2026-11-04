"""Assemble independently reviewed E1.2 gold in a PRIVATE local JSONL.

Never queries APIs, trains models or sends data to a third party.
Reviews are self-attested metadata; workflow must independently verify who
reviewed the material and their access to the observed, rights-approved text.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tapi_gate0.system_one_e1 import EvidenceBundle
from tapi_gate0.system_one_e12 import E12Case, HumanReview, validate_e12_dataset


class SplitAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: Literal["dev", "test"]
    gold_reference: str = Field(min_length=12, max_length=512)


def _read(path: Path, cls):
    if not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError("PRIVATE_E12_JSONL_REQUIRED_MAX_20MB")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(cls.model_validate_json(line))
        if len(rows) > 2000:
            raise ValueError("E12_MAX_2000_ENTRIES_PER_INPUT")
    if not rows:
        raise ValueError("E12_EMPTY_PRIVATE_INPUT")
    return rows


def _index(rows, key_fn):
    by_key = {}
    for item in rows:
        key = key_fn(item)
        if key in by_key:
            raise ValueError("E12_DUPLICATE_PRIVATE_INPUT_REFERENCE")
        by_key[key] = item
    return by_key


def assemble_gold(evidence: list[EvidenceBundle],
                  assignments: list[SplitAssignment],
                  first: list[HumanReview],
                  second: list[HumanReview],
                  third: list[HumanReview] | None = None) -> list[E12Case]:
    third = third or []
    evidence_by_key = _index(evidence, lambda e: e.fingerprint())
    assignment_by_key = _index(assignments, lambda a: a.evidence_fingerprint)
    first_by_key = _index(first, lambda r: r.evidence_fingerprint)
    second_by_key = _index(second, lambda r: r.evidence_fingerprint)
    third_by_key = _index(third, lambda r: r.evidence_fingerprint) if third else {}
    keys = set(evidence_by_key)
    if not keys or any(set(source) != keys for source in
                       (assignment_by_key, first_by_key, second_by_key)):
        raise ValueError("E12_MISSING_OR_EXTRA_GOLD_REVIEWS")
    if set(third_by_key) - keys:
        raise ValueError("E12_UNEXPECTED_ADJUDICATION_REFERENCE")
    cases = []
    for key, observation in evidence_by_key.items():
        record = assignment_by_key[key]
        reviews = [first_by_key[key], second_by_key[key]]
        if key in third_by_key:
            reviews.append(third_by_key[key])
        cases.append(E12Case(
            evidence=observation, split=record.split,
            gold_kind="human_consensus", gold_reference=record.gold_reference,
            human_reviews=reviews,
        ))
    # Validate held-out split integrity without evaluating any model.
    validate_e12_dataset(cases)
    return cases


def _not_in_repository(path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    if path == repository or path.is_relative_to(repository):
        raise ValueError("E12_PRIVATE_FILES_MUST_BE_OUTSIDE_GIT_WORKTREE")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble double-reviewed, authorized E1.2 gold locally")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--splits", required=True)
    parser.add_argument("--review-a", required=True)
    parser.add_argument("--review-b", required=True)
    parser.add_argument("--adjudication")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    paths = {key: Path(value).expanduser().resolve() for key, value in vars(args).items()
             if value is not None}
    for path in paths.values():
        _not_in_repository(path)
    target = paths["output"]
    if target.exists():
        parser.error("E12_GOLD_OUTPUT_ALREADY_EXISTS: never silently overwrite reviewed gold")
    cases = assemble_gold(
        evidence=_read(paths["evidence"], EvidenceBundle),
        assignments=_read(paths["splits"], SplitAssignment),
        first=_read(paths["review_a"], HumanReview),
        second=_read(paths["review_b"], HumanReview),
        third=_read(paths["adjudication"], HumanReview)
              if "adjudication" in paths else None,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        for case in cases:
            handle.write(case.model_dump_json()+"\n")
    print("E1.2 private gold assembled:", len(cases),
          "cases; two independent reviewers per case; no data uploaded.")
    print("Scientific corpus eligibility remains unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
