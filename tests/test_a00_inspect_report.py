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
