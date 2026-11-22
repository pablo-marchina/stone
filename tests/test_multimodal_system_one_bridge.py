"""A06→E1 text-only AV handoff: lab fixtures, never external media rights.

Mapping tests stub the expensive *full* shared report validator so that one
case can be constructed without Whisper weights or OCR binaries. This does
NOT replace the full pinned validation on real shared fixture reports.
"""
from copy import deepcopy
from hashlib import sha256

import pytest

from tapi_gate0 import multimodal_fusion as fusion
from tapi_gate0 import multimodal_system_one_bridge as bridge


ASSET = "a" * 64


def fragment(kind, text, *, eligible=True):
    locator = (
        {"caption_sha256": sha256(text.encode()).hexdigest(),
         "source": "authored_fixture_caption"}
        if kind == "caption" else
        {"start_s": 0.5, "end_s": 1.5, "source_pcm_sha256": "b" * 64,
         "chunk_pcm_sha256": "c" * 64, "timestamp_kind": "vad_selected"}
        if kind == "audio" else
        {"timestamp_s": 0, "frame_sha256": "d" * 64}
    )
    return fusion.fragment(ASSET, kind, text, locator,
                           semantic_eligible=eligible)


def fixture_report(monkeypatch, fragments=None):
    checks = {"report": 0, "asset": 0}

    def report_guard(report):
        checks["report"] += 1
        assert report["synthetic_only"] is True

    def asset_guard(row):
        checks["asset"] += 1
        assert row["asset_binding_verified"] is True
        return True

    monkeypatch.setattr(bridge.semantic, "validate_report", report_guard)
    monkeypatch.setattr(bridge.shared, "validate_asset_binding", asset_guard)
    monkeypatch.setattr(bridge.shared, "CASES", (("case1",),))
    row = {
        "case_id": "case1", "media_sha256": ASSET,
        "source_pixels_and_pcm_verified": True,
        "asset_binding_verified": True, "temporal_passed": True,
        "fragments": [] if fragments is None else fragments,
    }
    report = {
        "synthetic_only": True, "engineering_gate_passed": True,
        "database_mutated": False, "external_data_accessed": False,
        "production_approved": False, "real_media_processed": 0,
        "cases": [row],
    }
    return report, checks


def decisions(observation):
    return {d["field_id"]: d for d in observation["decision_bundle"]["decisions"]}


def test_caption_becomes_e1_candidate_with_sha_bound_fingerprint(monkeypatch):
    text = "Como vender mais? Comente sua dúvida!"
    report, checks = fixture_report(monkeypatch, [fragment("caption", text)])
    before = deepcopy(report)
    result = bridge.bridge_verified_synthetic_report(report)
    assert report == before
    assert (checks["report"], checks["asset"]) == (1, 1)
    assert result["source_kind"] == "synthetic"
    assert result["source_case_count"] == 1
    assert result["scientific_admissions"] == 0
    assert result["rubric_assessments_written"] == 0
    assert result["production_approved"] is False
    obs = result["cases"][0]["observations"][0]
    assert obs["modality"] == "caption"
    assert obs["text_sha256"] == sha256(text.encode()).hexdigest()
    assert obs["decision_bundle"]["evidence_fingerprint"] == obs["evidence_fingerprint"]
    assert decisions(obs)["tema_principal"]["value"] == "vendas"
    assert decisions(obs)["tipo_cta"]["value"] == "comentar"
    assert decisions(obs)["tipo_hook"]["abstained"] is True


def test_audio_segments_never_concatenated_or_mislabeled(monkeypatch):
    report, _ = fixture_report(monkeypatch, [
        fragment("audio", "Clique no link"),
        fragment("audio", "na bio"),
    ])
    result = bridge.bridge_verified_synthetic_report(report)
    obs = result["cases"][0]["observations"]
    assert len(obs) == 2
    assert all(x["modality"] == "transcript" for x in obs)
    assert len({x["evidence_fingerprint"] for x in obs}) == 2
    assert all(decisions(x)["tipo_cta"]["abstained"] for x in obs)
    assert all(decisions(x)["tipo_hook"]["abstained"] for x in obs)


def test_caption_and_audio_remain_separate_even_when_conflicting(monkeypatch):
    report, _ = fixture_report(monkeypatch, [
        fragment("caption", "Comente sua dúvida abaixo."),
        fragment("audio", "Salve este post."),
    ])
    result = bridge.bridge_verified_synthetic_report(report)
    obs = result["cases"][0]["observations"]
    assert [x["modality"] for x in obs] == ["caption", "transcript"]
    assert [decisions(x)["tipo_cta"]["value"] for x in obs] == [
        "comentar", "salvar",
    ]
    assert result["independent_gold"] is False


def test_ocr_and_vlm_are_never_misrepresented_as_e1_text(monkeypatch):
    report, _ = fixture_report(monkeypatch, [
        fragment("ocr", "Siga nosso perfil", eligible=True),
    ])
    result = bridge.bridge_verified_synthetic_report(report)
    assert result["ocr_vlm_promoted_to_e1"] is False
    assert result["text_observation_count"] == 0
    obs = result["cases"][0]["observations"]
    assert len(obs) == 1 and obs[0]["modality"] is None
    assert obs[0]["text_sha256"] is None
    assert all(d["abstained"] for d in obs[0]["decision_bundle"]["decisions"])


@pytest.mark.parametrize("change", [
    {"synthetic_only": False},
    {"database_mutated": True},
    {"external_data_accessed": True},
    {"production_approved": True},
    {"real_media_processed": 1},
    {"engineering_gate_passed": False},
])
def test_non_synthetic_or_noncompliant_report_denied(monkeypatch, change):
    report, checks = fixture_report(monkeypatch)
    report.update(change)
    with pytest.raises(bridge.SystemOneAVBridgeDenied,
                       match="A06_SYSTEM_ONE_SYNTHETIC_REPORT_REQUIRED"):
        bridge.bridge_verified_synthetic_report(report)
    assert checks["asset"] == 0


@pytest.mark.parametrize("flag", [
    "source_pixels_and_pcm_verified", "asset_binding_verified",
    "temporal_passed",
])
def test_missing_asset_or_temporal_integrity_denied(monkeypatch, flag):
    report, checks = fixture_report(monkeypatch)
    report["cases"][0][flag] = False
    with pytest.raises(bridge.SystemOneAVBridgeDenied):
        bridge.bridge_verified_synthetic_report(report)


def test_invalid_real_report_rejected_before_any_e1_output(monkeypatch):
    # Here the real pinned report validator is NOT replaced; an incomplete
    # report must fail even if its top-level safety flags look promising.
    report = {
        "synthetic_only": True, "engineering_gate_passed": True,
        "database_mutated": False, "external_data_accessed": False,
        "production_approved": False, "real_media_processed": 0,
        "cases": [],
    }
    with pytest.raises(bridge.SystemOneAVBridgeDenied):
        bridge.bridge_verified_synthetic_report(report)


def test_duplicate_case_identity_denied(monkeypatch):
    report, _ = fixture_report(monkeypatch)
    monkeypatch.setattr(bridge.shared, "CASES", (("case1",), ("case2",)))
    report["cases"].append(deepcopy(report["cases"][0]))
    with pytest.raises(bridge.SystemOneAVBridgeDenied):
        bridge.bridge_verified_synthetic_report(report)


def test_untrusted_tenant_identifier_denied_without_leaking_raw_payload(monkeypatch):
    report, _ = fixture_report(monkeypatch, [fragment("caption", "Salve este post.")])
    with pytest.raises(bridge.SystemOneAVBridgeDenied) as exc:
        bridge.bridge_verified_synthetic_report(report, tenant_id="wrong/tenant")
    assert "Salve este post." not in str(exc.value)
