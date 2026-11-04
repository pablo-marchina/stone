"""MPE source curation before any external read or corpus registration.

Candidate discovery, research authorization, API access, and corpus persistence
are distinct stages. A local document hash only proves integrity of the cited
operator evidence; it does NOT independently establish legal rights.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Literal
from hashlib import sha256
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

USERNAME = re.compile(r"[A-Za-z0-9_.]{1,30}\Z")
SECTORS = {"commerce", "food", "services", "beauty", "other"}
BANNED_TECHNICAL_TEST_ACCOUNTS = {"instagram", "academy_fellow_stone"}
REQUIRED_SCOPES = frozenset({"business_discovery_metadata_read", "local_research_metadata_export"})
OPTIONAL_SCOPES = frozenset({"corpus_metadata_ingest"})


class SourceGateError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    sector: str
    size_band: str  # micro / small / unverified; no follower proxy
    sampling_stratum: str = Field(min_length=3, max_length=80)
    size_evidence_reference: str | None = None
    source_evidence_reference: str = Field(min_length=12, max_length=256)
    status: str = "candidate"
    approval_reference: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    allowed_operations: list[str] = Field(default_factory=list)
    approval_proof_file: str | None = None
    approval_proof_sha256: str | None = None

    @model_validator(mode="after")
    def validate_source(self):
        if not USERNAME.fullmatch(self.username) or self.username.startswith(".") or self.username.endswith("."):
            raise ValueError("INVALID_SOURCE_USERNAME")
        if self.sector not in SECTORS:
            raise ValueError("INVALID_SECTOR")
        if self.size_band not in {"micro", "small", "unverified"}:
            raise ValueError("INVALID_SIZE_BAND")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", self.sampling_stratum):
            raise ValueError("INVALID_SAMPLING_STRATUM")
        if not self.sampling_stratum.startswith(self.sector + "_"):
            raise ValueError("SAMPLING_STRATUM_SECTOR_MISMATCH")
        if self.status not in {"candidate", "review", "approved", "rejected"}:
            raise ValueError("INVALID_SOURCE_STATUS")
        if len(self.allowed_operations) != len(set(self.allowed_operations)) or not set(self.allowed_operations) <= REQUIRED_SCOPES:
            raise ValueError("INVALID_OPERATION_SCOPE")
        if self.status == "approved":
            if self.size_band == "unverified" or not self.size_evidence_reference:
                raise ValueError("MPE_SIZE_EVIDENCE_REQUIRED")
            if not all((self.approval_reference, self.approved_by,
                        self.approved_at, self.expires_at,
                        self.approval_proof_file, self.approval_proof_sha256)):
                raise ValueError("SOURCE_APPROVAL_EVIDENCE_REQUIRED")
            if not REQUIRED_SCOPES.issubset(self.allowed_operations):
                raise ValueError("SOURCE_APPROVAL_SCOPE_INCOMPLETE")
            if not re.fullmatch(r"[a-f0-9]{64}", self.approval_proof_sha256 or ""):
                raise ValueError("INVALID_APPROVAL_DOCUMENT_HASH")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.approval_proof_file or ""):
                raise ValueError("INVALID_APPROVAL_DOCUMENT_NAME")
            if self.approved_at.tzinfo is None or self.expires_at.tzinfo is None or self.expires_at <= self.approved_at:
                raise ValueError("INVALID_APPROVAL_TIMESTAMPS")
        return self


class SourceFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "mpe-source-frame.v1"
    sources: list[SourceEntry] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_frame(self):
        if self.schema_version != "mpe-source-frame.v1":
            raise ValueError("UNSUPPORTED_SOURCE_FRAME")
        usernames = [x.username.casefold() for x in self.sources]
        if len(usernames) != len(set(usernames)):
            raise ValueError("DUPLICATE_SOURCE_USERNAME")
        return self


# DEC-016: producers of MPE-targeted posts need not themselves be MPEs.
CREATOR_TYPES = ("mpe_business", "independent_creator", "educator_expert",
                 "financial_institution", "fintech", "sector_brand",
                 "sector_organization", "other", "unverified")
AUDIENCE_INTENTS = ("mpe_targeted", "uncertain", "not_mpe_targeted")


class ResearchSourceEntry(BaseModel):
    """v2 source hypothesis. Only per-post evidence establishes scientific inclusion."""
    model_config = ConfigDict(extra="forbid")
    username: str
    creator_type: Literal[
        "mpe_business", "independent_creator", "educator_expert",
        "financial_institution", "fintech", "sector_brand",
        "sector_organization", "other", "unverified",
    ] = "unverified"
    business_size_class: Literal[
        "micro", "small", "medium", "large", "unknown", "not_applicable",
    ] = "unknown"
    business_size_evidence_reference: str | None = None
    sector_context: Literal[
        "commerce", "food", "services", "beauty", "finance", "cross_sector", "other",
    ] = "other"
    sampling_stratum: str = Field(min_length=3, max_length=80)
    audience_intent: Literal["mpe_targeted", "uncertain", "not_mpe_targeted"] = "uncertain"
    audience_rationale_reference: str | None = None
    source_evidence_reference: str = Field(min_length=12, max_length=256)
    status: Literal["candidate", "review", "approved", "rejected"] = "candidate"
    approval_reference: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    allowed_operations: list[str] = Field(default_factory=list)
    approval_proof_file: str | None = None
    approval_proof_sha256: str | None = None

    @model_validator(mode="after")
    def validate_research_source(self):
        if not USERNAME.fullmatch(self.username) or self.username.startswith(".") or self.username.endswith("."):
            raise ValueError("INVALID_SOURCE_USERNAME")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", self.sampling_stratum):
            raise ValueError("INVALID_SAMPLING_STRATUM")
        operations = set(self.allowed_operations)
        if len(operations) != len(self.allowed_operations) or not operations <= REQUIRED_SCOPES | OPTIONAL_SCOPES:
            raise ValueError("INVALID_OPERATION_SCOPE")
        if self.creator_type == "mpe_business" and self.status == "approved":
            if self.business_size_class not in {"micro", "small"} or not self.business_size_evidence_reference:
                raise ValueError("MPE_SIZE_EVIDENCE_REQUIRED")
        if self.status == "approved":
            if self.creator_type == "unverified" or self.audience_intent == "not_mpe_targeted":
                raise ValueError("RESEARCH_SOURCE_UNSUITABLE")
            if not self.audience_rationale_reference or len(self.audience_rationale_reference) < 12:
                raise ValueError("AUDIENCE_RATIONALE_REQUIRED")
            if not all((self.approval_reference, self.approved_by, self.approved_at,
                        self.expires_at, self.approval_proof_file, self.approval_proof_sha256)):
                raise ValueError("SOURCE_APPROVAL_EVIDENCE_REQUIRED")
            if not REQUIRED_SCOPES.issubset(operations):
                raise ValueError("SOURCE_APPROVAL_SCOPE_INCOMPLETE")
            if not re.fullmatch(r"[a-f0-9]{64}", self.approval_proof_sha256 or ""):
                raise ValueError("INVALID_APPROVAL_DOCUMENT_HASH")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.approval_proof_file or ""):
                raise ValueError("INVALID_APPROVAL_DOCUMENT_NAME")
            if (self.approved_at.tzinfo is None or self.expires_at.tzinfo is None
                or self.expires_at <= self.approved_at):
                raise ValueError("INVALID_APPROVAL_TIMESTAMPS")
        return self


class ResearchSourceFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["tapi-source-frame.v2"] = "tapi-source-frame.v2"
    sources: list[ResearchSourceEntry] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_research_frame(self):
        usernames = [x.username.casefold() for x in self.sources]
        if len(usernames) != len(set(usernames)):
            raise ValueError("DUPLICATE_SOURCE_USERNAME")
        return self


def load_frame(path: Path) -> SourceFrame | ResearchSourceFrame:
    if path.stat().st_size > 128_000:
        raise SourceGateError("SOURCE_FRAME_TOO_LARGE")
    raw = path.read_text(encoding="utf-8")
    version = json.loads(raw).get("schema_version")
    if version == "tapi-source-frame.v2":
        return ResearchSourceFrame.model_validate_json(raw)
    if version == "mpe-source-frame.v1":
        return SourceFrame.model_validate_json(raw)
    raise SourceGateError("UNSUPPORTED_SOURCE_FRAME")


def authorized_source(source: SourceEntry | ResearchSourceEntry, evidence_dir: Path, *, now: datetime | None = None) -> dict:
    """Fail before any API call. Hash-check a local operator approval artifact.

    The contents are intentionally NOT uploaded or logged. An independent
    legal/terms review is still required; this gate is a process control.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise SourceGateError("INVALID_AS_OF_TIME")
    if source.username.casefold() in BANNED_TECHNICAL_TEST_ACCOUNTS:
        raise SourceGateError("TEST_ACCOUNT_EXCLUDED_FROM_CORPUS")
    if source.status != "approved":
        raise SourceGateError("SOURCE_APPROVAL_REQUIRED")
    if source.expires_at <= now:
        raise SourceGateError("SOURCE_APPROVAL_EXPIRED")
    if source.approved_at > now:
        raise SourceGateError("SOURCE_APPROVAL_IN_FUTURE")
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise SourceGateError("APPROVAL_PROOF_DIRECTORY_MISSING")
    proof = evidence_dir / source.approval_proof_file
    if proof.is_symlink() or not proof.is_file():
        raise SourceGateError("APPROVAL_PROOF_MISSING")
    if proof.stat().st_size > 100_000 or proof.stat().st_size == 0:
        raise SourceGateError("APPROVAL_PROOF_INVALID_SIZE")
    digest = sha256(proof.read_bytes()).hexdigest()
    if digest != source.approval_proof_sha256:
        raise SourceGateError("APPROVAL_PROOF_HASH_MISMATCH")
    return {
        "username": source.username,
        "sector": source.sector,
        "creator_type": getattr(source, "creator_type", "mpe_business"),
        "business_size_class": getattr(source, "business_size_class", getattr(source, "size_band", "unknown")),
        "audience_intent": getattr(source, "audience_intent", "uncertain"),
        "audience_rationale_reference": getattr(source, "audience_rationale_reference", None),
        "sector_context": getattr(source, "sector_context", getattr(source, "sector", "other")),
        "size_band": getattr(source, "size_band", None),
        "sampling_stratum": source.sampling_stratum,
        "size_evidence_reference": getattr(source, "business_size_evidence_reference", getattr(source, "size_evidence_reference", None)),
        "source_evidence_reference": source.source_evidence_reference,
        "approval_reference": source.approval_reference,
        "approved_by": source.approved_by,
        "approved_at": source.approved_at.isoformat(),
        "expires_at": source.expires_at.isoformat(),
        "approval_proof_sha256": digest,
        "allowed_operations": sorted(source.allowed_operations),
        "operator_evidence_verified": True,
        "legal_rights_independently_verified": False,
    }


def audit_source_frame(frame: SourceFrame | ResearchSourceFrame, *, as_of: datetime | None = None) -> dict:
    """Offline sampling-frame audit: never credits candidates as eligible profiles."""
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        raise ValueError("timezone-aware as_of required")
    sectors = {sector: 0 for sector in sorted(SECTORS | {"finance", "cross_sector"})}
    creators = {name: 0 for name in CREATOR_TYPES}
    intents = {name: 0 for name in AUDIENCE_INTENTS}
    statuses = {key: 0 for key in ("candidate", "review", "approved", "rejected")}
    strata = {}
    deferred = []
    for src in frame.sources:
        sectors[getattr(src, "sector_context", getattr(src, "sector", "other"))] += 1
        creators[getattr(src, "creator_type", "mpe_business")] += 1
        intents[getattr(src, "audience_intent", "uncertain")] += 1
        statuses[src.status] += 1
        strata[src.sampling_stratum] = strata.get(src.sampling_stratum, 0) + 1
        if src.username.casefold() in BANNED_TECHNICAL_TEST_ACCOUNTS:
            deferred.append({"username": src.username, "reason": "TECHNICAL_TEST_ACCOUNT"})
        elif src.status != "approved":
            deferred.append({"username": src.username, "reason": "APPROVAL_PENDING"})
        elif src.expires_at <= as_of:
            deferred.append({"username": src.username, "reason": "APPROVAL_EXPIRED"})
    approved_not_expired = sum(
        s.status == "approved" and s.expires_at > as_of and
        s.username.casefold() not in BANNED_TECHNICAL_TEST_ACCOUNTS
        for s in frame.sources
    )
    return {
        "schema_version": frame.schema_version,
        "as_of": as_of.astimezone(timezone.utc).isoformat(),
        "target": {"minimum_profiles": 30, "minimum_eligible_posts": 2000,
                   "maximum_eligible_posts": 5000, "minimum_post_age_days": 14},
        "candidate_profiles": len(frame.sources),
        "approved_unexpired_candidates_not_yet_verified": approved_not_expired,
        "actual_eligible_profiles": 0,
        "actual_eligible_posts": 0,
        "counts_by_source_status": statuses,
        "counts_by_sector": sectors,
        "counts_by_creator_type": creators,
        "counts_by_source_audience_intent": intents,
        "counts_by_stratum": strata,
        "deferred_sources": deferred,
        "external_requests_performed": 0,
        "corpus_posts_persisted": 0,
        "note": "Source interest is a hypothesis; post targeting and legal usage require separate evidence.",
    }
