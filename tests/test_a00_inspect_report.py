import json
from hashlib import sha256

import pytest

from scripts import a00_inspect_report as inspect
from scripts.a00_baseline import BaselineError


def fixture(root):
    p=root/"artifacts"/"private"/"old-run"
    p.mkdir(parents=True)
    xml=b'<testsuite><testcase classname="tests.test_example" name="test_ok"/><testcase classname="tests.test_example" name="test_bad"><failure>private traceback</failure></testcase></testsuite>'
    (p/"pytest.xml").write_bytes(xml)
    steps=[]
    for step in ("legacy_gate0","zero_spend","pytest","node"):
        raw=step.encode()
        (p/(step+".log")).write_bytes(raw)
        steps.append({"step":step,"log":step+".log","log_sha256":sha256(raw).hexdigest()})
    data={"policy_version":"a00-local-baseline.v1","profile":"full",
          "inventory":{"commit":"a"*40,"tree":"b"*40},"steps":steps,
          "pytest":{"tests":2,"passed":1,"failed":1,"errors":0,"skipped":0,"skipped_tests":[]},
          "checks_passed":False}
    (p/"summary.json").write_text(json.dumps(data),encoding="utf-8")
    return p,data,xml


def test_old_report_extracts_failed_id_without_trace(tmp_path):
    p,data,xml=fixture(tmp_path)
    result=inspect.inspect_report(tmp_path,"old-run")
    assert result["failed_tests"]==[{"class":"tests.test_example","name":"test_bad","kind":"failure"}]
    assert result["logs_match_recorded_digests"]
    assert not result["xml_digest_previously_recorded"] and not result["tests_rerun"]
    assert not result["checks_passed"]
    assert "private traceback" not in json.dumps(result)
    assert result["pytest_xml_sha256"]==sha256(xml).hexdigest()


def test_report_rejects_modified_log(tmp_path):
    p,_,_=fixture(tmp_path)
    (p/"pytest.log").write_text("changed")
    with pytest.raises(BaselineError,match="LOG_HASH_MISMATCH"):
        inspect.inspect_report(tmp_path,"old-run")


def test_report_rejects_xml_digest_or_count_mismatch(tmp_path):
    p,data,xml=fixture(tmp_path)
    data["pytest_xml_sha256"]="c"*64
    (p/"summary.json").write_text(json.dumps(data))
    with pytest.raises(BaselineError,match="XML_HASH_MISMATCH"):
        inspect.inspect_report(tmp_path,"old-run")
    del data["pytest_xml_sha256"]
    data["pytest"]["failed"]=0
    (p/"summary.json").write_text(json.dumps(data))
    with pytest.raises(BaselineError,match="COUNTS_MISMATCH"):
        inspect.inspect_report(tmp_path,"old-run")


def test_report_rejects_traversal(tmp_path):
    with pytest.raises(BaselineError,match="NAME_INVALID"):
        inspect.inspect_report(tmp_path,"../old-run")


def _upgrade_to_v2(report_dir, data):
    data["policy_version"] = "a00-local-baseline.v2"
    raw = b"PASS_ESPELHO_DOCUMENTAL fixture"
    (report_dir/"documentary_mirror.log").write_bytes(raw)
    data["steps"].append({
        "step": "documentary_mirror",
        "log": "documentary_mirror.log",
        "log_sha256": sha256(raw).hexdigest(),
    })
    (report_dir/"summary.json").write_text(json.dumps(data), encoding="utf-8")


def test_current_v2_full_report_inspects_documentary_mirror_and_old_v1_unchanged(tmp_path):
    p, data, xml = fixture(tmp_path)
    old = inspect.inspect_report(tmp_path, "old-run")
    assert old["policy_version"] == "a00-local-baseline.v1"
    _upgrade_to_v2(p, data)
    current = inspect.inspect_report(tmp_path, "old-run")
    assert current["policy_version"] == "a00-local-baseline.v2"
    assert current["logs_match_recorded_digests"] is True
    assert current["pytest_xml_sha256"] == sha256(xml).hexdigest()
    assert current["checks_passed"] is False
    assert current["failed_tests"] == old["failed_tests"]


def test_current_v2_full_report_requires_documentary_mirror_and_hash(tmp_path):
    p, data, _ = fixture(tmp_path)
    data["policy_version"] = "a00-local-baseline.v2"
    (p/"summary.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BaselineError, match="A00_REPORT_STEPS_INVALID"):
        inspect.inspect_report(tmp_path, "old-run")
    _upgrade_to_v2(p, data)
    (p/"documentary_mirror.log").write_text("tampered after baseline")
    with pytest.raises(BaselineError, match="A00_REPORT_LOG_HASH_MISMATCH"):
        inspect.inspect_report(tmp_path, "old-run")


def test_current_v2_semantic_report_does_not_require_documentary_mirror(tmp_path):
    p, data, _ = fixture(tmp_path)
    data["policy_version"] = "a00-local-baseline.v2"
    data["profile"] = "semantic"
    data["steps"] = [s for s in data["steps"] if s["step"] != "node"]
    (p/"summary.json").write_text(json.dumps(data), encoding="utf-8")
    result = inspect.inspect_report(tmp_path, "old-run")
    assert result["policy_version"] == "a00-local-baseline.v2"
    assert result["profile"] == "semantic"
    assert result["logs_match_recorded_digests"] is True
