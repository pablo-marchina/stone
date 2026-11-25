"""A07.3 loopback CDP driver orchestration; no browser needed in these tests.

These are MOCKED lifecycle tests, not proof of actual Chrome raster parity.
"""
from pathlib import Path

from scripts import a07_browser_cdp as driver
from scripts import a07_browser_visual_parity as runner


def _output(status, passed, text):
    return (f'<output id="a073-result" data-status="{status}" '
            f'data-passed="{passed}" data-total="7">{text}</output>')


class FakeProcess:
    def __init__(self, argv):
        self.argv = argv
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.terminated = True


class FakeCDP:
    calls = []
    reports = []

    def __init__(self, port, path):
        assert port == 49273
        assert path == "/devtools/browser/a073"
        self.closed = False

    def call(self, method, params=None, session=None):
        self.calls.append((method, params, session))
        if method == "Target.createTarget":
            assert params == {"url": "about:blank"}
            return {"targetId": "a073-target"}
        if method == "Target.attachToTarget":
            assert params["flatten"] is True
            return {"sessionId": "a073-session"}
        if method == "Page.enable":
            return {}
        if method == "Runtime.evaluate":
            expr = params["expression"]
            if expr.startswith("document.open();document.write("):
                assert "root.StoneExport=" in expr
                assert "A073_BROWSER_PARITY_PASS" in expr
                return {"result": {"type": "undefined"}}
            assert session == "a073-session"
            return {"result": {"value": self.reports.pop(0)}}
        raise AssertionError("Unexpected CDP command")

    def close(self):
        self.closed = True


def _patch_browser(monkeypatch, reports):
    processes = []
    FakeCDP.calls = []
    FakeCDP.reports = list(reports)

    def fake_popen(args, **kwargs):
        processes.append(FakeProcess(args))
        return processes[-1]

    monkeypatch.setattr(driver.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        driver, "_port_from_profile",
        lambda profile, process: (49273, "/devtools/browser/a073"),
    )
    monkeypatch.setattr(driver, "LocalCDP", FakeCDP)
    return processes


def test_cdp_waits_for_async_completion_and_never_uses_virtual_time(monkeypatch):
    processes = _patch_browser(monkeypatch, [
        _output("RUNNING", 0, "A073_RUNNING"),
        _output("RUNNING", 2, "A073_RUNNING_CHECKS 2/7"),
        _output("PASS", 7, "A073_BROWSER_PARITY_PASS"),
    ])
    html = driver.run_browser_cdp(
        Path("fictional-chrome"), runner.FIXTURE, runner.ENGINE,
    )
    assert runner.read_result(html) == (True, "A073_BROWSER_PARITY_PASS 7/7")
    assert len(processes) == 1
    assert processes[0].terminated is True
    flags = processes[0].argv
    assert "--headless=new" in flags
    assert "--remote-debugging-address=127.0.0.1" in flags
    assert "--remote-debugging-port=0" in flags
    assert "--disable-background-networking" in flags
    assert not any("virtual-time-budget" in x or "--dump-dom" in x for x in flags)
    assert any(x.startswith("--user-data-dir=") for x in flags)
    assert any(x.startswith("--host-resolver-rules=") for x in flags)
    assert len([x for x in FakeCDP.calls if x[0] == "Runtime.evaluate"]) == 4


def test_cdp_timeout_returns_incomplete_dom_not_a_fake_pass(monkeypatch):
    processes = _patch_browser(monkeypatch, [
        _output("RUNNING", 0, "A073_RUNNING"),
    ] * 20)
    html = driver.run_browser_cdp(
        Path("fictional-chrome"), runner.FIXTURE, runner.ENGINE,
        timeout_seconds=0.3,
    )
    ok, reason = runner.read_result(html)
    assert ok is False
    assert reason.startswith("A073_BROWSER_INCOMPLETE")
    assert processes[0].terminated is True


def test_cdp_fail_status_is_returned_not_overridden_by_runner(monkeypatch):
    processes = _patch_browser(monkeypatch, [
        _output("FAIL", 4, "A073_FAIL PNG_VISUAL_MISMATCH"),
    ])
    html = driver.run_browser_cdp(
        Path("fictional-chrome"), runner.FIXTURE, runner.ENGINE,
    )
    ok, reason = runner.read_result(html)
    assert ok is False
    assert reason.startswith("A073_BROWSER_CHECK_FAILED")
    assert processes[0].terminated is True
