"""Disposable local fixtures, no Stone checkout or external services needed."""
from pathlib import Path

from scripts.a05_python_source_preflight import audit


def _folder(tmp_path):
    folder = tmp_path / "src" / "tapi_gate0"
    folder.mkdir(parents=True)
    return folder


def _check(tmp_path):
    return audit(tmp_path, directories=("src/tapi_gate0",), required=())


def test_clean_python_file_passes_without_running_module(tmp_path):
    source = _folder(tmp_path) / "module.py"
    source.write_text("raise RuntimeError('never executed')\n")
    result = _check(tmp_path)
    assert result["status"] == "PASS"
    assert result["files_checked"] == 1
    assert result["deployment_authorized"] is False


def test_duplicate_keyword_star_is_rejected_under_python_311(tmp_path):
    source = _folder(tmp_path) / "creative_reference_pep_a05.py"
    source.write_text("def require(self, *, tenant, *, operation):\n    pass\n")
    result = _check(tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["errors"][0]["code"] == "SOURCE_SYNTAX_INVALID"


def test_missing_required_source_fails_closed(tmp_path):
    _folder(tmp_path)
    result = audit(tmp_path, directories=("src/tapi_gate0",),
                   required=("src/tapi_gate0/missing.py",))
    assert result["status"] == "BLOCKED"
    assert any(x["code"] == "SOURCE_REQUIRED_MISSING" for x in result["errors"])


def test_invalid_python311_grammar_fails_even_under_newer_interpreter(tmp_path):
    source = _folder(tmp_path) / "too_new.py"
    source.write_text("type Alias = list[int]\n")  # Python 3.12-only syntax
    result = _check(tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["python_grammar"] == "3.11"
