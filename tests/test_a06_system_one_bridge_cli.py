"""A06 E1 CLI tests on disposable, explicitly pinned synthetic JSON."""
from hashlib import sha256
import json
import os

import pytest

from scripts import a06_system_one_bridge as cli


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    folder = tmp_path / "artifacts" / "private"
    folder.mkdir(parents=True)
    source = folder / "input.json"
    source.write_text(json.dumps({"synthetic_only": True}), encoding="utf-8")
    digest = sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "check_checkout", lambda *a, **k: None)
    calls = []

    def bridge(report):
        calls.append(report)
        return {
            "schema_version": "tapi-a06-system-one-synthetic-av-bridge.v1",
            "status": "SYNTHETIC_TEXT_CANDIDATES_ONLY",
            "source_case_count": 1, "text_observation_count": 1,
            "scientific_admissions": 0, "production_approved": False,
        }

    monkeypatch.setattr(cli, "bridge_verified_synthetic_report", bridge)
    args = [
        "--expected-head", "a"*40,
        "--input-name", "input.json", "--input-sha256", digest,
        "--output-name", "output.json",
    ]
    return folder, calls, args


def test_explicit_pinned_synthetic_bridge_writes_one_private_receipt(sandbox, capsys):
    folder, calls, args = sandbox
    assert cli.main(args) == 0
    assert calls == [{"synthetic_only": True}]
    output = folder / "output.json"
    assert output.is_file()
    receipt = json.loads(output.read_text())
    assert receipt["production_approved"] is False
    assert receipt["scientific_admissions"] == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["output_sha256"] == sha256(output.read_bytes()).hexdigest()
    if os.name == "posix":
        assert (output.stat().st_mode & 0o077) == 0


def test_existing_output_cannot_be_overwritten(sandbox, capsys):
    folder, calls, args = sandbox
    output = folder / "output.json"
    output.write_text("existing")
    assert cli.main(args) == 2
    assert output.read_text() == "existing"
    assert calls == []
    assert "input.json" not in capsys.readouterr().out


def test_bad_input_sha_blocks_without_creating_output(sandbox):
    folder, calls, args = sandbox
    args[args.index("--input-sha256")+1] = "f"*64
    assert cli.main(args) == 2
    assert not (folder/"output.json").exists()
    assert calls == []


@pytest.mark.parametrize("arg,value", [
    ("--input-name", "../private/input.json"),
    ("--output-name", "../../outside.json"),
    ("--expected-head", "short"),
])
def test_invalid_paths_or_head_are_denied(sandbox, arg, value):
    folder, calls, args = sandbox
    args[args.index(arg)+1] = value
    assert cli.main(args) == 2
    assert calls == []


def test_failed_bridge_does_not_write_or_expose_payload(sandbox, monkeypatch, capsys):
    folder, calls, args = sandbox
    def fail(report):
        raise ValueError("secret source data should not appear")
    monkeypatch.setattr(cli, "bridge_verified_synthetic_report", fail)
    assert cli.main(args) == 2
    assert not (folder/"output.json").exists()
    output = capsys.readouterr().out
    assert "secret source" not in output
    assert json.loads(output)["production_approved"] is False


def test_missing_private_folder_is_not_created_implicitly(sandbox):
    folder, calls, args = sandbox
    (folder/"input.json").unlink()
    folder.rmdir()
    assert cli.main(args) == 2
    assert not folder.exists()
    assert calls == []


def test_failed_fsync_removes_partial_receipt(sandbox, monkeypatch, capsys):
    folder, calls, args = sandbox

    def fail_fsync(_fd):
        raise OSError("sensitive filesystem detail")

    monkeypatch.setattr(cli.os, "fsync", fail_fsync)
    assert cli.main(args) == 2
    assert len(calls) == 1
    assert not (folder / "output.json").exists()
    response = capsys.readouterr().out
    assert "sensitive filesystem detail" not in response
    assert json.loads(response)["production_approved"] is False
