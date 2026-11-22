"""A06/DEC-017: verified synthetic multimodal observations -> System One E1.

This is a report-only, deterministic bridge. It does NOT decode media, run a
model remotely, write a rubric/corpus, claim independent gold, or process
third-party content. The public entrypoint first checks the complete authored
shared-AV report and source-to-fragment lineage. OCR/VLM observations are
intentionally NOT misrepresented as E1 caption/transcript observations.
"""
from __future__ import annotations

from hashlib import sha256
import json

from . import multimodal_semantic_replay as semantic
from . import multimodal_shared_fixture as shared
from .system_one_e1 import (
    DeterministicTextDecider, EvidenceBundle, ObservedText,
)

VERSION = "tapi-a06-system-one-synthetic-av-bridge.v1"


class SystemOneAVBridgeDenied(ValueError):
    """Sanitized denial: no external payloads, paths or raw model outputs."""


def _fail():
    raise SystemOneAVBridgeDenied("A06_SYSTEM_ONE_SYNTHETIC_REPORT_REQUIRED")


def _digest_report(report):
    return sha256(json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _one_case(row, *, tenant_id: str, creator_id: str):
    """Map a fully source-verified lab row without conflating modalities.

    Internal helper; it cannot independently attest a row. Only the public
    bridge calls it AFTER the complete report and asset bindings are checked.
    """
    cid = row["case_id"]
    asset_sha = row["media_sha256"]
    content_id = "synthetic.av." + cid
    fragments = [
        f for f in row["fragments"]
        if f["modality"] in ("caption", "audio")
        and f["semantic_eligible"] is True
    ]
    if len(fragments) > 64:
        _fail()
    fragments.sort(key=lambda f: (
        0 if f["modality"] == "caption" else 1,
        f["locator"].get("start_s", 0),
        f["text_sha256"],
    ))
    observations = []
    # An absent caption or silence must yield explicit abstention rather than
    # a fabricated negative assertion about the complete source video.
    if not fragments:
        fragments = [None]
    for f in fragments:
        if f is None:
            observation = None
            observed_modality = None
            source_text_sha256 = None
        else:
            observed_modality = (
                "caption" if f["modality"] == "caption" else "transcript"
            )
            locator = (
                "synthetic-av:sha256:" + asset_sha + "/"
                + f["modality"] + "/text-sha256:" + f["text_sha256"]
            )
            if f["modality"] == "audio":
                bounds = f["locator"]
                locator += (
                    "/start:" + str(bounds["start_s"])
                    + "/end:" + str(bounds["end_s"])
                    + "/pcm-sha256:" + bounds["source_pcm_sha256"]
                )
            observation = ObservedText(
                modality=observed_modality,
                text=f["text"], locator=locator, sha256=f["text_sha256"],
            )
            source_text_sha256 = f["text_sha256"]
        evidence = EvidenceBundle(
            tenant_id=tenant_id, content_id=content_id,
            creator_id=creator_id, source_kind="synthetic",
            observation=observation,
        )
        decision = DeterministicTextDecider().evaluate(evidence)
        if decision.evidence_fingerprint != evidence.fingerprint():
            _fail()
        observations.append({
            "modality": observed_modality,
            "text_sha256": source_text_sha256,
            "evidence_fingerprint": evidence.fingerprint(),
            "decision_bundle": decision.model_dump(mode="json"),
            "is_scientific_review": False,
            "is_canonical_rubric": False,
        })
    return {
        "case_id": cid, "content_id": content_id,
        "asset_sha256": asset_sha,
        "observations": observations,
    }


def bridge_verified_synthetic_report(
    report: dict, *, tenant_id: str = "synthetic_lab",
    creator_id: str = "synthetic_av_author",
) -> dict:
    """Make E1 text-only candidate decisions from an attested synthetic AV lab.

    The independent verified-AV report validator pins model checkpoint, native
    source assets, shared synthetic fixtures, ASR/VAD/OCR provenance and
    zero external/media/corpus actions. No bypass flag or caller-asserted
    'validated' boolean exists in this entrypoint.
    """
    if not isinstance(report, dict):
        _fail()
    try:
        initial = _digest_report(report)
        if (report.get("synthetic_only") is not True
                or report.get("engineering_gate_passed") is not True
                or report.get("source_report_kind") not in (None, "shared_fixture")
                or report.get("database_mutated") is not False
                or report.get("external_data_accessed") is not False
                or report.get("production_approved") is not False
                or report.get("real_media_processed") != 0):
            _fail()
        semantic.validate_report(report)
        if _digest_report(report) != initial:
            _fail()
        cases = report["cases"]
        if not isinstance(cases, list) or len(cases) != len(shared.CASES):
            _fail()
        mapped = []
        seen = set()
        for row in cases:
            if row["case_id"] in seen:
                _fail()
            seen.add(row["case_id"])
            if (row["source_pixels_and_pcm_verified"] is not True
                    or row["asset_binding_verified"] is not True
                    or row["temporal_passed"] is not True):
                _fail()
            shared.validate_asset_binding(row)
            mapped.append(_one_case(
                row, tenant_id=tenant_id, creator_id=creator_id,
            ))
        if _digest_report(report) != initial:
            _fail()
        return {
            "schema_version": VERSION,
            "status": "SYNTHETIC_TEXT_CANDIDATES_ONLY",
            "source_report_content_sha256": initial,
            "cases": mapped,
            "source_case_count": len(mapped),
            "text_observation_count": sum(
                1 for c in mapped for item in c["observations"]
                if item["modality"] is not None
            ),
            "source_kind": "synthetic",
            "e1_text_only": True,
            "ocr_vlm_promoted_to_e1": False,
            "independent_gold": False,
            "scientific_admissions": 0,
            "rubric_assessments_written": 0,
            "external_data_accessed": False,
            "database_mutated": False,
            "media_processed_by_bridge": 0,
            "production_approved": False,
            "global_gates_released": False,
        }
    except SystemOneAVBridgeDenied:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        _fail()
