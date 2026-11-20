"""IMP-060 local fixture validation CLI must not expose sealed references."""
from hashlib import sha256
import json
from pathlib import Path

from scripts import a4_gold_registry_check as cli


def test_ct04_positive_fixture_pinned_and_aggregate_only(capsys):
    path = cli.ROOT / "tests" / "fixtures" / "CT-04_positive.json"
    assert path.is_file()
    digest = sha256(path.read_bytes()).hexdigest()
    assert cli.main(["--fixture", str(path), "--expected-sha256", digest]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == "SYNTHETIC_GOLD_REGISTRY_CONTRACT_VERIFIED"
    assert result["gold_relevance_judgments_available"] is False
    assert result["scientifically_validated"] is False
    assert result["production_approved"] is False
    assert result["external_data_accessed"] is False
    assert result["database_mutated"] is False
    for secret in ("sealed_test-query-1", "sealed_test-content-1",
                   "development-content-1", "fixture-tenant"):
        assert secret not in output


def test_ct04_tampered_sha_or_non_fixture_path_blocks_without_raw_data(
        tmp_path, monkeypatch, capsys):
    root = tmp_path
    allowed = root / "tests" / "fixtures"
    allowed.mkdir(parents=True)
    path = allowed / "CT-04_positive.json"
    path.write_text("private synthetic fake source", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", root)
    assert cli.main([
        "--fixture", str(path), "--expected-sha256", "a" * 64,
    ]) == 2
    assert "private synthetic fake source" not in capsys.readouterr().out
    other = tmp_path / "other.json"
    other.write_text("forbidden fixture", encoding="utf-8")
    assert cli.main([
        "--fixture", str(other), "--expected-sha256",
        sha256(other.read_bytes()).hexdigest(),
    ]) == 2
    output = capsys.readouterr().out
    assert "forbidden fixture" not in output
    assert json.loads(output)["status"] == "BLOCKED"
