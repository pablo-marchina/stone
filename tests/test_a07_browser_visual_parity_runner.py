"""A07.3 stdlib browser-runner fail-closed contract; no browser required here."""
from pathlib import Path
from types import SimpleNamespace

from scripts import a07_browser_visual_parity as runner


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


def test_success_requires_browser_exit_zero_and_completed_real_dom(
        monkeypatch, capsys):
    monkeypatch.setattr(runner, "find_browser", lambda _: Path(__file__))
    called = []

    def fake_run(argv, **kwargs):
        called.append(argv)
        assert "--headless=new" in argv
        assert "--disable-background-networking" in argv
        assert "--dump-dom" in argv
        assert any(a.startswith("--host-resolver-rules=") for a in argv)
        assert any(a.startswith("--user-data-dir=") for a in argv)
        return SimpleNamespace(returncode=0, stdout=_dom(), stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main([]) == 0
    assert len(called) == 1
    assert "7/7" in capsys.readouterr().out


def test_browser_process_error_and_incomplete_dom_fail_closed(monkeypatch):
    monkeypatch.setattr(runner, "find_browser", lambda _: Path(__file__))
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout=_dom(), stderr=""),
    )
    assert runner.main([]) == 1
    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="<html></html>", stderr=""),
    )
    assert runner.main([]) == 1


def test_browser_timeout_does_not_fake_success(monkeypatch):
    from subprocess import TimeoutExpired

    monkeypatch.setattr(runner, "find_browser", lambda _: Path(__file__))

    def timeout(*_args, **_kwargs):
        raise TimeoutExpired(cmd=["fixture"], timeout=45)

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    assert runner.main([]) == 1
