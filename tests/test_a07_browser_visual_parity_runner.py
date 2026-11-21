"""A07.3 stdlib browser-runner fail-closed contract; no browser required here."""
from pathlib import Path

import pytest

from scripts import a07_browser_visual_parity as runner
from scripts.a07_browser_cdp import BrowserDiagnostic, compose_fixture


def _dom(*, status="PASS", passed="7", total="7",
         body="A073_BROWSER_PARITY_PASS"):
    return (f'<!doctype html><output id="a073-result" data-status="{status}" '
            f'data-passed="{passed}" data-total="{total}">{body}</output>')


def test_full_browser_result_must_be_exactly_seven_actual_checks():
    assert runner.read_result(_dom()) == (True, "A073_BROWSER_PARITY_PASS 7/7")
    for html in (
        _dom(passed="6"),
        _dom(total="8"),
        _dom(status="PENDING"),
        _dom(body="A073_BROWSER_PARITY_PASS_FAKE"),
        _dom(status="FAIL", body="A073_FAIL"),
        '<output id="other" data-status="PASS" data-passed="7" data-total="7">'
        'A073_BROWSER_PARITY_PASS</output>',
        "<html></html>",
    ):
        assert runner.read_result(html)[0] is False


def test_explicit_nonexistent_browser_cannot_fall_back_to_another_browser(tmp_path):
    assert runner.find_browser(str(tmp_path / "missing-browser")) is None


def test_no_local_browser_is_failure_not_skip_or_pass(monkeypatch, capsys):
    monkeypatch.setattr(runner, "find_browser", lambda _: None)
    assert runner.main([]) == 2
    assert "nenhum PASS" in capsys.readouterr().out


def test_success_requires_completed_real_dom_from_cdp(monkeypatch, capsys):
    monkeypatch.setattr(runner, "find_browser", lambda _: Path(__file__))
    called = []

    def fake_cdp(browser, fixture, exporter):
        called.append((browser, fixture, exporter))
        assert browser == Path(__file__)
        assert fixture == runner.FIXTURE
        assert exporter == runner.ENGINE
        return _dom()

    monkeypatch.setattr(runner, "run_browser_cdp", fake_cdp)
    assert runner.main([]) == 0
    assert len(called) == 1
    assert "7/7" in capsys.readouterr().out


def test_browser_driver_error_and_incomplete_dom_fail_closed(monkeypatch):
    monkeypatch.setattr(runner, "find_browser", lambda _: Path(__file__))

    def failed_cdp(*_args, **_kwargs):
        raise BrowserDiagnostic("A073_CDP_PROCESS_FAILED")

    monkeypatch.setattr(runner, "run_browser_cdp", failed_cdp)
    assert runner.main([]) == 1
    monkeypatch.setattr(runner, "run_browser_cdp",
                        lambda *_a, **_k: "<html></html>")
    assert runner.main([]) == 1


def test_browser_timeout_does_not_fake_success(monkeypatch):
    monkeypatch.setattr(runner, "find_browser", lambda _: Path(__file__))

    def timeout(*_args, **_kwargs):
        raise BrowserDiagnostic("A073_CDP_COMMAND_TIMEOUT")

    monkeypatch.setattr(runner, "run_browser_cdp", timeout)
    assert runner.main([]) == 1


def test_unexecuted_html_script_and_incomplete_async_are_not_acceptance():
    assert runner.read_result(_dom(
        status="PENDING", passed="0", body="A073_PENDING",
    )) == (False, "A073_SCRIPT_NOT_EXECUTED")
    ok, reason = runner.read_result(_dom(
        status="RUNNING", passed="2", body="A073_RUNNING_CHECKS 2/7",
    ))
    assert ok is False
    assert reason == "A073_BROWSER_INCOMPLETE A073_RUNNING_CHECKS 2/7"


def test_inline_fixture_contains_no_literal_premature_script_closer():
    import re

    source = runner.FIXTURE.read_text(encoding="utf-8")
    # One external <script src> end and one inline script end. A literal
    # '</script>' inside an inline JS string would end its enclosing element.
    assert len(re.findall(r"</script\s*>", source, flags=re.IGNORECASE)) == 2
    assert r"\x3C/script>" in source
    assert "A073_BROWSER_PARITY_PASS" in source


def test_composed_browser_fixture_embeds_only_local_exporter():
    composed = compose_fixture(runner.FIXTURE, runner.ENGINE)
    assert '<script src=' not in composed
    assert composed.count('</script>') == 2
    assert 'root.StoneExport=' in composed
    assert 'A073_BROWSER_PARITY_PASS' in composed
    assert composed.count("await run('") == 7


def test_browser_fixture_rejects_new_external_resource(tmp_path):
    html = runner.FIXTURE.read_text(encoding="utf-8")
    modified = tmp_path / "untrusted.html"
    modified.write_text(html.replace(
        "A073_PENDING", "A073_PENDING https://example.org/escape"
    ), encoding="utf-8")
    with pytest.raises(BrowserDiagnostic, match="A073_LOCAL_FIXTURE_NOT_ISOLATED"):
        compose_fixture(modified, runner.ENGINE)
