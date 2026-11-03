"""Source selection and auditable first-eligible evidence, fully offline."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import httpx
import pytest

from tapi_gate0.connectors import OfficialHttp
from tapi_gate0.mpe_sources import (SourceEntry, SourceFrame, SourceGateError,
                                   authorized_source, audit_source_frame)
from tapi_gate0.mpe_evidence import FirstEligibleSampler, canonical_hash
from scripts.mpe_corpus_pilot import main

NOW = datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc)
VIEWER = "17841459971757521"
TARGET_ID = "17841412345678901"
TOKEN = "mock-meta-token-never-forwarded"


def source(tmp_path, username="mpe_loja_teste", status="approved", *, expired=False):
    folder = tmp_path / "approvals"
    folder.mkdir(exist_ok=True)
    payload = b"Independent human research approval fixture; synthetic and not a real grant."
    (folder / "proof.txt").write_bytes(payload)
    data = {
        "username": username, "sector": "food", "size_band": "micro",
        "sampling_stratum": "food_micro", "size_evidence_reference": "operator-size-verification-v1",
        "source_evidence_reference": "operator-profile-link-v1",
        "status": status,
    }
    if status == "approved":
        data.update({"approval_reference": "research-data-license-2026",
                     "approved_by": "research_admin", "approved_at": NOW - timedelta(days=30),
                     "expires_at": NOW - timedelta(days=1) if expired else NOW + timedelta(days=30),
                     "allowed_operations": ["business_discovery_metadata_read", "local_research_metadata_export"],
                     "approval_proof_file": "proof.txt",
                     "approval_proof_sha256": sha256(payload).hexdigest()})
    return SourceEntry(**data), folder


def row(mid, published, kind="REELS", **changes):
    data = {"id": mid,
            "media_type": "VIDEO" if kind == "REELS" else "CAROUSEL_ALBUM",
            "media_product_type": "REELS" if kind == "REELS" else "FEED",
            "timestamp": published, "permalink": "https://www.instagram.com/reel/abc123/",
            "like_count": 22, "comments_count": 3}
    data.update(changes)
    return data


def graph(response_items, *, next_cursor=None, followers=200, seen=None):
    def handler(req):
        if seen is not None:
            seen.append(req)
        assert req.url.host == "graph.facebook.com"
        assert req.url.path == "/v23.0/" + VIEWER
        assert req.headers["Authorization"] == "Bearer " + TOKEN
        assert "access_token" not in req.url.params
        fields = req.url.params["fields"]
        assert "business_discovery.username(mpe_loja_teste)" in fields
        assert "media.limit(" in fields
        if isinstance(response_items, dict):
            requested = response_items["second"] if ".after(CURSOR_SAFE_2)" in fields else response_items["first"]
        else:
            requested = response_items
        pagination = {"cursors": {"after": "CURSOR_SAFE_2"}} if next_cursor and ".after(CURSOR_SAFE_2)" not in fields else {}
        return httpx.Response(200, json={"id": VIEWER, "business_discovery": {
            "id": TARGET_ID, "username": "mpe_loja_teste", "followers_count": followers,
            "media_count": 200, "media": {"data": requested, "paging": pagination}}})
    return handler


def test_frame_is_zero_corpus_and_stratified(tmp_path):
    item, _ = source(tmp_path)
    other = item.model_copy(update={"username": "mpe_outra", "sector": "beauty",
                                    "sampling_stratum": "beauty_micro", "status": "candidate"})
    frame = SourceFrame(sources=[item, other])
    report = audit_source_frame(frame, as_of=NOW)
    assert report["candidate_profiles"] == 2
    assert report["approved_unexpired_candidates_not_yet_verified"] == 1
    assert report["actual_eligible_profiles"] == 0
    assert report["actual_eligible_posts"] == 0
    assert report["counts_by_sector"]["food"] == 1
    assert report["counts_by_stratum"]["beauty_micro"] == 1
    assert report["external_requests_performed"] == 0
    with pytest.raises(ValueError):
        SourceFrame(sources=[item, item])


def test_proof_hash_and_scope_must_match_before_any_network(tmp_path):
    candidate, root = source(tmp_path, status="candidate")
    with pytest.raises(SourceGateError) as exc:
        authorized_source(candidate, root, now=NOW)
    assert exc.value.code == "SOURCE_APPROVAL_REQUIRED"
    approved, root = source(tmp_path)
    assert authorized_source(approved, root, now=NOW)["operator_evidence_verified"]
    (root / "proof.txt").write_text("TAMPERED")
    with pytest.raises(SourceGateError) as exc:
        authorized_source(approved, root, now=NOW)
    assert exc.value.code == "APPROVAL_PROOF_HASH_MISMATCH"


def test_tech_test_target_not_allowed_and_expired_blocked(tmp_path):
    test_target, root = source(tmp_path, username="instagram")
    with pytest.raises(SourceGateError) as exc:
        authorized_source(test_target, root, now=NOW)
    assert exc.value.code == "TEST_ACCOUNT_EXCLUDED_FROM_CORPUS"
    old, root = source(tmp_path, expired=True)
    with pytest.raises(SourceGateError) as exc:
        authorized_source(old, root, now=NOW)
    assert exc.value.code == "SOURCE_APPROVAL_EXPIRED"


def test_validates_source_size_and_sector_evidence(tmp_path):
    item, _ = source(tmp_path)
    with pytest.raises(ValueError):
        SourceEntry(**{**item.model_dump(), "size_band": "unverified"})
    with pytest.raises(ValueError):
        SourceEntry(**{**item.model_dump(), "sampling_stratum": "beauty_micro"})
    with pytest.raises(ValueError):
        SourceEntry(**{**item.model_dump(), "allowed_operations": ["business_discovery_metadata_read"]})


def test_two_realistic_pages_with_eligible_records_and_integrity(tmp_path):
    item, folder = source(tmp_path)
    approval = authorized_source(item, folder, now=NOW)
    before = "2026-10-10T12:00:00+0000"
    just_recent = "2026-10-30T12:00:00+0000"
    first = [row("18100000000000001", before), row("18100000000000002", just_recent)]
    second = [row("18100000000000003", before, kind="CAROUSEL_ALBUM"),
              row("18100000000000001", before)]
    seen = []
    with httpx.Client(transport=httpx.MockTransport(graph({"first":first,"second":second},
                                                          next_cursor=True, seen=seen))) as c:
        result = FirstEligibleSampler(OfficialHttp(c)).scan(VIEWER, TOKEN, approval,
                                                              limit=2, max_pages=2, as_of=NOW)
    assert len(seen) == 2
    assert result["pages_examined"] == 2
    assert result["counts"]["eligible_14d"] == 2
    assert result["counts"]["too_recent"] == 1
    assert result["counts"]["duplicates"] == 1
    assert result["corpus_posts_persisted"] == 0
    assert result["not_a_rights_grant"]
    assert result["eligible_media"][0]["denominator_quality"] == "observed_current_only"
    assert result["eligible_media"][0]["followers_measured_at"] == NOW.isoformat()
    assert result["eligible_media"][0]["source_account_id"] == TARGET_ID
    digest = result["eligible_media"][0].pop("integrity_sha256")
    assert canonical_hash(result["eligible_media"][0]) == digest
    assert len(result["page_metadata_sha256"]) == 2
    assert TOKEN not in json.dumps(result)


def test_zero_followers_and_missing_metrics_are_excluded(tmp_path):
    approved, folder = source(tmp_path)
    approval = authorized_source(approved, folder, now=NOW)
    old = "2026-10-01T12:00:00+0000"
    entries = [row("18100000000000001", old, like_count=None),
               row("18100000000000002", old),
               row("18100000000000003", old, permalink="https://evil.invalid/x")]
    with httpx.Client(transport=httpx.MockTransport(graph(entries, followers=0))) as c:
        result = FirstEligibleSampler(OfficialHttp(c)).scan(VIEWER, TOKEN, approval, limit=3,
                                                              max_pages=1, as_of=NOW)
    assert result["counts"]["missing_metrics"] == 1
    assert result["counts"]["invalid_denominator"] == 1
    assert result["counts"]["invalid_metadata"] == 1
    assert result["counts"]["eligible_14d"] == 0
    assert result["eligible_media"] == []


def test_cli_stays_offline_for_unapproved_and_never_writes(tmp_path, monkeypatch, capsys):
    item, folder = source(tmp_path, status="candidate")
    file = tmp_path / "frame.json"
    file.write_text(SourceFrame(sources=[item]).model_dump_json(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["--frame", str(file)]) == 0
    assert '"status": "SOURCE_FRAME_AUDIT"' in capsys.readouterr().out
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    assert main(["--frame", str(file), "--execute", "--source", item.username,
                 "--evidence-dir", str(folder)]) == 2
    assert "SOURCE_APPROVAL_REQUIRED" in capsys.readouterr().out
    assert not (tmp_path / "artifacts").exists()


def test_cli_can_export_private_report_only_for_approved_source(tmp_path, monkeypatch, capsys):
    item, folder = source(tmp_path)
    file = tmp_path / "frame.json"
    file.write_text(SourceFrame(sources=[item]).model_dump_json(), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TAPI_INSTAGRAM_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("TAPI_OFFICIAL_METADATA_READS", "1")
    monkeypatch.setenv("TAPI_ZERO_BILLING_CONFIRMED", "1")
    with httpx.Client(transport=httpx.MockTransport(graph([
        row("18100000000000001", "2026-10-01T12:00:00+0000")
    ]))) as c:
        args = ["--frame", str(file), "--execute", "--source", item.username,
                "--evidence-dir", str(folder), "--output-name", "mpe-test-local.json"]
        assert main(args, http=OfficialHttp(c)) == 0
        assert "PRIVATE_EVIDENCE_SAVED" in capsys.readouterr().out
        saved = tmp_path / "artifacts/private/mpe_corpus/mpe-test-local.json"
        report = json.loads(saved.read_text())
        assert report["counts"]["eligible_14d"] == 1
        assert report["corpus_posts_persisted"] == 0
        assert TOKEN not in saved.read_text()
        assert main(args, http=OfficialHttp(c)) == 2
        assert "PRIVATE_REPORT_ALREADY_EXISTS" in capsys.readouterr().out


def test_official_cannot_read_test_account_even_with_fake_approval(tmp_path):
    item, folder = source(tmp_path, username="instagram")
    with pytest.raises(SourceGateError):
        authorized_source(item, folder, now=NOW)
