"""DEC-017 E1.5: contracts for *future* independent CTA text review.

This module contains no provider clients, network operations, model loading or
real-data file runner. While Gate 0B is unapproved, evaluation is limited to
synthetic rehearsals with simulated reviewers. Human-reference acquisition and
the actual scientific benchmark require a separate, audited authorization gate.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import Id
from .system_one_e1 import E1_LABELS, EvidenceBundle
from .system_one_e14 import CTAChoice

E15_SCHEMA = "tapi-dec017-e15-independent-cta-review.v1"
STATE = Literal[
    "affirmative_single", "affirmative_multiple",
    "no_affirmative_in_observed_text", "indeterminate",
]
SINGLE = "affirmative_single"
NEGATIVE = "no_affirmative_in_observed_text"
POLICIES = frozenset({
    "baseline_e1_original",
    "rule_negation_e13",
    "gliner_e1_original",
    "gliner_e13_rule_assisted",
    "e14_gliner_original_text_guard",
    "e14_raw_type_text_agreement",
    "e14_raw_type_text_and_presence_agreement",
})


class CTAHumanFinding(BaseModel):
    """Scope is *only* the witnessed caption/transcript, never the whole video."""
    model_config = ConfigDict(extra="forbid")
    state: STATE
    cta_type: str | None = None
    evidence_locator: str = Field(min_length=3, max_length=4096)
    rationale: str = Field(min_length=8, max_length=500)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.state == SINGLE:
            if self.cta_type not in E1_LABELS["tipo_cta"]:
                raise ValueError("E15_SINGLE_REQUIRES_ALLOWED_CTA_TYPE")
        elif self.cta_type is not None:
            raise ValueError("E15_NON_SINGLE_NEVER_ASSERTS_UNIQUE_TYPE")
        return self


class IndependentCTAReview(BaseModel):
    """Model-blind first/second review, or independent adjudication."""
    model_config = ConfigDict(extra="forbid")
    reviewer_id: Id
    reviewed_at: datetime
    evidence_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    blinded_to_model_outputs: Literal[True]
    finding: CTAHumanFinding

    @model_validator(mode="after")
    def check_review_time(self):
        if self.reviewed_at.utcoffset() is None:
            raise ValueError("E15_REVIEWER_TIMEZONE_REQUIRED")
        return self


class AuthorizationEvidence(BaseModel):
    """Only an attested *reference*; actual legal grants require external audit.

    A self-declared JSON proof or source_kind='approved_local' never proves rights.
    No E1.5 code will use this to unlock real-data model inference.
    """
    model_config = ConfigDict(extra="forbid")
    evidence_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_reference: str = Field(min_length=12, max_length=512)
    proof_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    gate0b_record_reference: str = Field(min_length=12, max_length=512)
    verified_by: Id
    verified_at: datetime
    expires_at: datetime
    permitted_operations: list[Literal[
        "offline_human_annotation", "offline_classification", "aggregate_evaluation",
    ]] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def check_attestation(self):
        if self.verified_at.utcoffset() is None or self.expires_at.utcoffset() is None:
            raise ValueError("E15_RIGHTS_DATES_MUST_HAVE_TIMEZONE")
        if self.expires_at <= self.verified_at:
            raise ValueError("E15_EXPIRED_OR_INVALID_RIGHTS_WINDOW")
        if len(set(self.permitted_operations)) != 3:
            raise ValueError("E15_INCOMPLETE_OPERATION_SCOPES")
        return self


class CTAReviewedCase(BaseModel):
    """Two independent blinded reviews, arbitrator ONLY if the first two differ."""
    model_config = ConfigDict(extra="forbid")
    evidence: EvidenceBundle
    split: Literal["dev", "test"]
    canonical_creator_group: Id
    campaign_group: Id | None = None
    first: IndependentCTAReview
    second: IndependentCTAReview
    adjudication: IndependentCTAReview | None = None
    authorization: AuthorizationEvidence | None = None

    @model_validator(mode="after")
    def verify_review_integrity(self):
        item = self.evidence.observation
        if item is None:
            raise ValueError("E15_ACTUALLY_OBSERVED_TEXT_REQUIRED")
        fp = self.evidence.fingerprint()
        reviews = [self.first, self.second] + (
            [self.adjudication] if self.adjudication is not None else []
        )
        if len({r.reviewer_id for r in reviews}) != len(reviews):
            raise ValueError("E15_INDEPENDENT_REVIEWER_IDS_REQUIRED")
        if any(r.evidence_fingerprint != fp for r in reviews):
            raise ValueError("E15_REVIEW_EVIDENCE_FINGERPRINT_MISMATCH")
        if any(r.finding.evidence_locator != item.locator for r in reviews):
            raise ValueError("E15_REVIEW_LOCATOR_MUST_MATCH_OBSERVED_TEXT")
        if self.first.reviewed_at > self.second.reviewed_at:
            # Review packets can arrive out of order; independence is by IDs
            # and model blinding, not chronology between primary reviewers.
            pass
        if self.adjudication is not None and self.adjudication.reviewed_at < max(
            self.first.reviewed_at, self.second.reviewed_at
        ):
            raise ValueError("E15_ADJUDICATION_MUST_FOLLOW_PRIMARY_REVIEWS")
        disagree = self._key(self.first) != self._key(self.second)
        if disagree and self.adjudication is None:
            raise ValueError("E15_DISAGREEMENT_REQUIRES_THIRD_REVIEWER")
        if not disagree and self.adjudication is not None:
            raise ValueError("E15_UNNECESSARY_ADJUDICATION")
        if self.evidence.source_kind == "approved_local":
            if self.authorization is None:
                raise ValueError("E15_REAL_TEXT_REQUIRES_EXTERNAL_RIGHTS_EVIDENCE")
            auth = self.authorization
            if (auth.evidence_fingerprint != fp
                    or auth.rights_reference != self.evidence.rights_reference):
                raise ValueError("E15_RIGHTS_REFERENCE_DOES_NOT_MATCH_EVIDENCE")
            if auth.verified_at > min(r.reviewed_at for r in reviews):
                raise ValueError("E15_REVIEW_PRECEDES_RIGHTS_VERIFICATION")
            if auth.expires_at <= max(r.reviewed_at for r in reviews):
                raise ValueError("E15_REVIEW_AFTER_RIGHTS_EXPIRATION")
        elif self.evidence.source_kind == "synthetic":
            if self.authorization is not None:
                raise ValueError("E15_SYNTHETIC_CANNOT_MASQUERADE_AS_APPROVED")
        else:
            raise ValueError("E15_UNSUPPORTED_SOURCE_KIND")
        return self

    @staticmethod
    def _key(review: IndependentCTAReview) -> tuple:
        return review.finding.state, review.finding.cta_type

    def final_finding(self) -> CTAHumanFinding:
        return (
            self.adjudication.finding if self.adjudication is not None
            else self.first.finding
        )

    def was_adjudicated(self) -> bool:
        return self.adjudication is not None


class FrozenStudyProtocol(BaseModel):
    """Must be registered before reviewer work; no test-driven winner selection."""
    model_config = ConfigDict(extra="forbid")
    study_id: Id
    registered_at: datetime
    frozen_split_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_names: list[str] = Field(min_length=1, max_length=7)
    selected_on_dev_only: Literal[True] = True
    holdout_test_locked: Literal[True] = True
    primary_target: Literal["caption_positive_type_with_negative_risk"] = (
        "caption_positive_type_with_negative_risk"
    )
    minimum_total_for_claim: int = Field(default=50, ge=50)
    minimum_positive_test_for_claim: int = Field(default=20, ge=20)
    minimum_negative_test_for_claim: int = Field(default=20, ge=20)
    minimum_creators_test_for_claim: int = Field(default=20, ge=20)

    @model_validator(mode="after")
    def preregister(self):
        if self.registered_at.utcoffset() is None:
            raise ValueError("E15_PREREGISTRATION_REQUIRES_TIMEZONE")
        if (len(set(self.policy_names)) != len(self.policy_names)
                or not set(self.policy_names) <= POLICIES):
            raise ValueError("E15_POLICIES_MUST_BE_PREDECLARED")
        return self


def e15_split_manifest_sha256(cases: list[CTAReviewedCase]) -> str:
    """Commit to exact observed bytes, split, creator group and campaign group."""
    rows = sorted(
        (
            c.evidence.fingerprint(), c.split,
            c.canonical_creator_group, c.campaign_group or "none",
        )
        for c in cases
    )
    joined = "\n".join("\x1f".join(row) for row in rows)
    return sha256(joined.encode("utf-8")).hexdigest()


def validate_e15_study(
    cases: list[CTAReviewedCase], protocol: FrozenStudyProtocol,
) -> None:
    if not cases or len(cases) > 2000:
        raise ValueError("E15_STUDY_EXPECTS_1_TO_2000_CASES")
    identities = [(c.evidence.tenant_id, c.evidence.content_id) for c in cases]
    if len(set(identities)) != len(identities):
        raise ValueError("E15_DUPLICATE_CONTENT")
    fingerprints = [c.evidence.fingerprint() for c in cases]
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("E15_DUPLICATE_FINGERPRINT")
    if {c.split for c in cases} != {"dev", "test"}:
        raise ValueError("E15_REQUIRES_BOTH_DEV_AND_TEST")
    if e15_split_manifest_sha256(cases) != protocol.frozen_split_manifest_sha256:
        raise ValueError("E15_FROZEN_SPLIT_MANIFEST_MISMATCH")
    by_creator: dict[str, set[str]] = {}
    by_campaign: dict[str, set[str]] = {}
    by_text: dict[str, set[str]] = {}
    for c in cases:
        if min(c.first.reviewed_at, c.second.reviewed_at) <= protocol.registered_at:
            raise ValueError("E15_REGISTRATION_MUST_PRECEDE_BLINDED_REVIEWS")
        by_creator.setdefault(c.canonical_creator_group, set()).add(c.split)
        if c.campaign_group is not None:
            by_campaign.setdefault(c.campaign_group, set()).add(c.split)
        obs = c.evidence.observation
        by_text.setdefault(obs.sha256, set()).add(c.split)
        if c.adjudication is not None and c.adjudication.reviewed_at <= protocol.registered_at:
            raise ValueError("E15_ADJUDICATION_PRECEDES_PROTOCOL")
    if any(len(splits) > 1 for splits in by_creator.values()):
        raise ValueError("E15_CREATOR_DEV_TEST_LEAKAGE")
    if any(len(splits) > 1 for splits in by_campaign.values()):
        raise ValueError("E15_CAMPAIGN_DEV_TEST_LEAKAGE")
    if any(len(splits) > 1 for splits in by_text.values()):
        raise ValueError("E15_TEXT_DEV_TEST_LEAKAGE")


def _ratio(n: int, total: int) -> float | None:
    return round(n / total, 6) if total else None


def _agreement(cases: list[CTAReviewedCase]) -> dict:
    """Two-blind-review nominal agreement; kappa may be undefined on one class."""
    if not cases:
        return {"n": 0, "raw_agreement": None, "cohen_kappa_nominal": None,
                "n_adjudicated": 0}
    first = [CTAReviewedCase._key(c.first) for c in cases]
    second = [CTAReviewedCase._key(c.second) for c in cases]
    n = len(cases)
    agreement = sum(a == b for a, b in zip(first, second))
    ca, cb = Counter(first), Counter(second)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    po = agreement / n
    kappa = (po - pe) / (1 - pe) if pe < 1 else None
    return {
        "n": n,
        "raw_agreement": round(po, 6),
        "cohen_kappa_nominal": round(kappa, 6) if kappa is not None else None,
        "n_adjudicated": sum(c.was_adjudicated() for c in cases),
    }


def _policy_scores(cases: list[CTAReviewedCase],
                   predictions: Mapping[str, CTAChoice]) -> dict:
    counts = Counter()
    for c in cases:
        outcome = c.final_finding()
        pred = predictions[c.evidence.fingerprint()]
        counts["total"] += 1
        counts["presence_claims"] += int(pred.presence is True)
        counts["type_claims"] += int(pred.kind is not None)
        if outcome.state == SINGLE:
            counts["positive_single"] += 1
            counts["positive_correct"] += int(pred.kind == outcome.cta_type)
            counts["positive_wrong"] += int(
                pred.kind is not None and pred.kind != outcome.cta_type
            )
            counts["positive_abstain"] += int(pred.kind is None)
        elif outcome.state == NEGATIVE:
            counts["observed_caption_negative"] += 1
            counts["caption_negative_presence_claims"] += int(pred.presence is True)
            counts["caption_negative_type_claims"] += int(pred.kind is not None)
        elif outcome.state == "affirmative_multiple":
            counts["positive_multiple"] += 1
            counts["multiple_type_claims"] += int(pred.kind is not None)
        else:
            counts["indeterminate"] += 1
            counts["indeterminate_presence_claims"] += int(pred.presence is True)
            counts["indeterminate_type_claims"] += int(pred.kind is not None)
    n, pos, neg = (
        counts["total"], counts["positive_single"], counts["observed_caption_negative"]
    )
    accepted_decidable = (
        counts["positive_correct"] + counts["positive_wrong"]
        + counts["caption_negative_type_claims"]
    )
    return {
        "n_cases": n,
        "n_positive_single": pos,
        "n_observed_caption_negative": neg,
        "n_positive_multiple": counts["positive_multiple"],
        "n_indeterminate": counts["indeterminate"],
        "presence_claims": counts["presence_claims"],
        "presence_abstentions": n - counts["presence_claims"],
        "type_claims": counts["type_claims"],
        "type_abstentions": n - counts["type_claims"],
        "type_coverage": _ratio(counts["type_claims"], n),
        "type_recall_positive_single": _ratio(counts["positive_correct"], pos),
        "n_positive_correct": counts["positive_correct"],
        "n_positive_wrong": counts["positive_wrong"],
        "n_positive_abstain": counts["positive_abstain"],
        "caption_negative_presence_claims": counts["caption_negative_presence_claims"],
        "caption_negative_type_claims": counts["caption_negative_type_claims"],
        "caption_negative_presence_claim_rate": _ratio(
            counts["caption_negative_presence_claims"], neg
        ),
        "caption_negative_type_claim_rate": _ratio(
            counts["caption_negative_type_claims"], neg
        ),
        "selective_type_precision_decidable": _ratio(
            counts["positive_correct"], accepted_decidable
        ),
        "multiple_type_claims": counts["multiple_type_claims"],
        "indeterminate_presence_claims": counts["indeterminate_presence_claims"],
        "indeterminate_type_claims": counts["indeterminate_type_claims"],
    }


def rehearse_e15_synthetic(
    cases: list[CTAReviewedCase],
    protocol: FrozenStudyProtocol,
    predictions: Mapping[str, Mapping[str, CTAChoice]],
) -> dict:
    """Exercise review logic without scientific data. Never accept real posts.

    Any authorized_local case must fail closed even if operator supplied fake
    grant IDs; a future audited release must implement that workflow separately.
    """
    validate_e15_study(cases, protocol)
    if any(c.evidence.source_kind != "synthetic" for c in cases):
        raise PermissionError("E15_REAL_DATA_BLOCKED_PENDING_GATE0B")
    expected = {c.evidence.fingerprint() for c in cases}
    if set(predictions) != set(protocol.policy_names):
        raise ValueError("E15_POLICY_SET_MISMATCH")
    if any(set(predictions[name]) != expected for name in protocol.policy_names):
        raise ValueError("E15_PAIRED_PREDICTIONS_REQUIRED")
    results = {}
    for split in ("dev", "test"):
        subset = [c for c in cases if c.split == split]
        scores = {}
        for name in protocol.policy_names:
            for key in predictions[name]:
                if not isinstance(predictions[name][key], CTAChoice):
                    raise ValueError("E15_PREDICTION_MUST_BE_A_SAFE_CTA_CHOICE")
            scores[name] = _policy_scores(subset, predictions[name])
        results[split] = {
            "n_cases": len(subset),
            "n_creators": len({c.canonical_creator_group for c in subset}),
            "reviewer_agreement": _agreement(subset),
            "policies": scores,
        }
    test = results["test"]
    test_neg = sum(c.final_finding().state == NEGATIVE
                   for c in cases if c.split == "test")
    test_pos = sum(c.final_finding().state == SINGLE
                   for c in cases if c.split == "test")
    support_sufficient = (
        len(cases) >= protocol.minimum_total_for_claim
        and test_pos >= protocol.minimum_positive_test_for_claim
        and test_neg >= protocol.minimum_negative_test_for_claim
        and test["n_creators"] >= protocol.minimum_creators_test_for_claim
    )
    digest = sha256("".join(sorted(
        c.evidence.fingerprint() for c in cases
    )).encode("ascii")).hexdigest()
    return {
        "schema_version": E15_SCHEMA,
        "study_id": protocol.study_id,
        "mode": "SYNTHETIC_REHEARSAL_ONLY",
        "scientifically_validated": False,
        "rights_independently_verified_by_software": False,
        "production_enabled": False,
        "external_data_used": False,
        "holdout_claim_allowed": False,
        "rehearsal_support_thresholds_would_pass": support_sufficient,
        "n_total": len(cases),
        "synthetic_fingerprint_digest": digest,
        "dev": results["dev"],
        "test": results["test"],
        "decision": "NO_SCIENTIFIC_OR_PRODUCTION_APPROVAL",
        "limitations": [
            "Simulated reviewer IDs are not proof of independent humans.",
            "No external authorization, independent scientific review or real gold here.",
            "No videos were observed; no affirmative instruction in text is not no CTA in a video.",
            "Test score is a dry-run of held-out grouping, not a population estimate.",
            "Audit of legal grants, authorship, conflict of interest, and test lock is external.",
        ],
    }
