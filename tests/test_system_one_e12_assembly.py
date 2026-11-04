"""DEC-017 E1.2: independent human gold assembly; PRIVATE/local only."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
from assemble_e12_human_gold import (
    SplitAssignment, _not_in_repository, assemble_gold,
)
from tapi_gate0.system_one_e1 import EvidenceBundle, ObservedText, E1_FIELDS
from tapi_gate0.system_one_e12 import E12Case, HumanReview, ReferenceLabel


def _source(content_id="post1"):
    text = "Dicas de vendas para o comércio do bairro."
    return EvidenceBundle(
        tenant_id="private_test", content_id=content_id, creator_id="creator1",
        source_kind="approved_local",
        rights_reference="locally-verified-research-approval",
        allowed_operations=["offline_classification"],
        observation=ObservedText(
            modality="caption", text=text, locator="private:post1#caption",
            sha256=sha256(text.encode("utf-8")).hexdigest()))


def _review(source, person="annotatorA", theme="vendas"):
    labels = [
        ReferenceLabel(
            field_id=field,
            status="observed" if field == "tema_principal" else "not_observable",
            value=theme if field == "tema_principal" else None,
            evidence_locator="private:post1#caption" if field == "tema_principal" else None,
            rationale="private reviewed text evidence" if field == "tema_principal"
                      else "insufficient source modality",
        )
        for field in E1_FIELDS
    ]
    return HumanReview(
        reviewer_id=person,
        reviewed_at=datetime(2026,11,4,10,tzinfo=timezone.utc),
        evidence_fingerprint=source.fingerprint(),
        labels=labels)


def _assignment(source):
    return SplitAssignment(
        evidence_fingerprint=source.fingerprint(),
        split="test", gold_reference="private-operator-record-verified")


def test_assemble_two_reviewers_without_adjudication():
    src = _source()
    cases = assemble_gold([src],[_assignment(src)],[_review(src,"annotatorA")],
                          [_review(src,"annotatorB")])
    assert len(cases)==1
    assert cases[0].gold_kind=="human_consensus"
    assert cases[0].resolved()[0]["tema_principal"].value=="vendas"


def test_assemble_fails_closed_on_missing_review():
    src = _source()
    with pytest.raises(ValueError, match="E12_MISSING_OR_EXTRA_GOLD_REVIEWS"):
        assemble_gold([src],[_assignment(src)],[_review(src,"annotatorA")],[])


def test_assemble_rejects_unresolved_disagreement_and_accepts_third():
    src=_source()
    first=_review(src,"annotatorA","vendas")
    second=_review(src,"annotatorB","marketing")
    with pytest.raises(ValueError, match="E12_UNRESOLVED_REVIEWER_DISAGREEMENT"):
        assemble_gold([src],[_assignment(src)],[first],[second])
    third=_review(src,"independentThird","vendas")
    cases=assemble_gold([src],[_assignment(src)],[first],[second],[third])
    assert cases[0].resolved()[1]=={"tema_principal"}


def test_private_paths_cannot_point_into_git():
    with pytest.raises(ValueError, match="E12_PRIVATE_FILES_MUST_BE_OUTSIDE_GIT_WORKTREE"):
        _not_in_repository(ROOT / "artifacts" / "private" / "gold.jsonl")


def test_private_cli_never_overwrites_gold_or_prints_content(tmp_path):
    src=_source()
    def write(name,objs):
        file=tmp_path/name
        file.write_text("".join(x.model_dump_json()+"\n" for x in objs),
                        encoding="utf-8")
        return file
    sources=write("sources.jsonl",[src])
    splits=write("splits.jsonl",[_assignment(src)])
    first=write("review_a.jsonl",[_review(src,"a")])
    second=write("review_b.jsonl",[_review(src,"b")])
    target=tmp_path/"final_gold.jsonl"
    command=[sys.executable,str(ROOT/"scripts"/"assemble_e12_human_gold.py"),
        "--evidence",str(sources),"--splits",str(splits),
        "--review-a",str(first),"--review-b",str(second),"--output",str(target)]
    first_run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,check=True)
    assert "private gold assembled: 1" in first_run.stdout
    assert "Dicas de vendas para" not in first_run.stdout
    rows=[E12Case.model_validate_json(line) for line in
          target.read_text(encoding="utf-8").splitlines()]
    assert rows[0].resolved()[0]["tema_principal"].value=="vendas"
    second_run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert second_run.returncode!=0
    assert "E12_GOLD_OUTPUT_ALREADY_EXISTS" in second_run.stderr
