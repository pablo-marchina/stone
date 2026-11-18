"""Portable contract + native Windows synthetic resource/cleanup checks."""
import ctypes
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import time

import pytest

from tapi_gate0 import asset_windows_job as w


NATIVE = pytest.mark.skipif(sys.platform != "win32" or ctypes.sizeof(ctypes.c_void_p) != 8,
                            reason="requires native Windows x64 Job Objects")
PRE = "import sys\nassert sys.stdin.buffer.read() == b'x'\n"
OK = PRE + "sys.stdout.buffer.write(b'ok')"
SLEEP = PRE + "import time\ntime.sleep(30)"
TREE = PRE + "import subprocess\nsubprocess.Popen([sys.executable,'-I','-S','-c','import time; time.sleep(30)'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)\nsys.stdout.buffer.write(b'ok')"


def test_x64_layout():
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert [ctypes.sizeof(t) for t in (w.BasicLimits, w.ExtendedLimits, w.Accounting)] == [64, 144, 48]
    assert w.FLAGS == 0x220C  # no breakaway flags


@pytest.mark.parametrize("updates", [{"memory_mib": 63}, {"cpu_user_seconds": 0},
    {"active_processes": 5}, {"wall_seconds": True}, {"wall_seconds": 31}])
def test_limit_rejects_invalid_budget(updates):
    with pytest.raises(w.JobError, match="LIMIT_INVALID"):
        replace(w.JobLimits(), **updates)


def test_unsupported_platform_fails_closed(monkeypatch):
    monkeypatch.setattr(w.sys, "platform", "linux")
    with pytest.raises(w.JobError, match="WINDOWS_X64_REQUIRED"):
        w.WindowsJob(w.JobLimits())


@pytest.mark.parametrize("data,expected", [(b'', b'ok'), (b'x'*65, b'ok'), (b'x', b'y'*65)])
def test_bounds_before_check_or_spawn(data, expected):
    with pytest.raises(w.JobError, match="FIXTURE_BOUNDS"):
        w._run_trusted_fixture(OK, data, expected, lambda: pytest.fail("check called"))


class FakeProcess:
    def __init__(self, events):
        self.events, self.returncode = events, None
    def communicate(self, input=None, timeout=None):
        self.events.append(("communicate", input))
        self.returncode = 0
        return b'ok', None
    def poll(self):
        return self.returncode
    def kill(self):
        self.events.append("kill_direct")
        self.returncode = 1
    def wait(self, timeout):
        self.events.append("wait")


class FakeJob:
    def __init__(self, events, fail_assign=False, remain=False):
        self.events, self.fail_assign, self.remain = events, fail_assign, remain
    def assign(self, proc):
        self.events.append("assign")
        if self.fail_assign:
            raise w.JobError("ASSIGN_FAILED")
    def active(self):
        return int(self.remain)
    def terminate(self):
        self.events.append("terminate_tree")
        self.remain = False
    def wait_empty(self):
        self.events.append("empty")
        assert not self.remain
    def close(self):
        self.events.append("close")


def fake_run(monkeypatch, *, fail_assign=False, remain=False):
    events = []
    proc = FakeProcess(events)
    job = FakeJob(events, fail_assign, remain)
    monkeypatch.setattr(w, "WindowsJob", lambda limits: job)
    def spawn(*args, **kwargs):
        assert kwargs["shell"] is False and kwargs["close_fds"] is True
        assert "TAPI_DATABASE_URL" not in kwargs["env"]
        events.append("spawn")
        return proc
    monkeypatch.setattr(w.subprocess, "Popen", spawn)
    return events


def test_assignment_precedes_data_and_cleanup_precedes_success(monkeypatch):
    events = fake_run(monkeypatch)
    assert w._run_trusted_fixture(OK, b'x', b'ok', lambda: events.append("check")) == b'ok'
    assert events.index("assign") < events.index(("communicate", b'x'))
    assert events[-3:] == ["empty", "close", "check"]


def test_assignment_failure_never_sends_bytes(monkeypatch):
    events = fake_run(monkeypatch, fail_assign=True)
    with pytest.raises(w.JobError, match="ASSIGN_FAILED"):
        w._run_trusted_fixture(OK, b'x', b'ok', lambda: None)
    assert ("communicate", b'x') not in events and "kill_direct" in events
    assert events[-2:] == ["empty", "close"]


def test_cancel_before_sending_bytes_terminates_tree(monkeypatch):
    events = fake_run(monkeypatch, remain=True)
    def check():
        if "assign" in events:
            raise ValueError("revoked")
    with pytest.raises(ValueError, match="revoked"):
        w._run_trusted_fixture(OK, b'x', b'ok', check)
    assert ("communicate", b'x') not in events and "terminate_tree" in events
    assert events[-2:] == ["empty", "close"]


def test_descendants_prevent_success_and_are_cleaned(monkeypatch):
    events = fake_run(monkeypatch, remain=True)
    with pytest.raises(w.JobError, match="DESCENDANTS_REMAIN"):
        w._run_trusted_fixture(OK, b'x', b'ok', lambda: None)
    assert "terminate_tree" in events and events[-2:] == ["empty", "close"]


@NATIVE
def test_native_success_and_exclusive_job():
    job = w.WindowsJob(w.JobLimits())
    try:
        with pytest.raises(w.JobError, match="SESSION_JOB_BUSY"):
            w.WindowsJob(w.JobLimits())
    finally:
        job.close()
    assert w._run_trusted_fixture(OK, b'x', b'ok', lambda: None) == b'ok'


@NATIVE
def test_native_wall_timeout_and_reacquire():
    with pytest.raises(w.JobError, match="TIMEOUT"):
        w._run_trusted_fixture(SLEEP, b'x', b'ok', lambda: None, limits=w.JobLimits(wall_seconds=2))
    assert w._run_trusted_fixture(OK, b'x', b'ok', lambda: None) == b'ok'


@NATIVE
def test_native_descendant_is_terminated_even_after_root_exits():
    with pytest.raises(w.JobError, match="DESCENDANTS_REMAIN"):
        w._run_trusted_fixture(TREE, b'x', b'ok', lambda: None)
    assert w._run_trusted_fixture(OK, b'x', b'ok', lambda: None) == b'ok'


@NATIVE
def test_native_user_cpu_time_terminates_job():
    code = PRE + "while True: pass"
    with pytest.raises(w.JobError, match="PROBE_OUTPUT_INVALID"):
        w._run_trusted_fixture(code, b'x', b'ok', lambda: None,
                               limits=w.JobLimits(cpu_user_seconds=1, wall_seconds=15))


@NATIVE
def test_native_commit_memory_cap():
    code = PRE + "try:\n    bytearray(256*1024*1024)\nexcept MemoryError:\n    sys.stdout.buffer.write(b'limited')\nelse:\n    sys.exit(3)"
    assert w._run_trusted_fixture(code, b'x', b'limited', lambda: None) == b'limited'


@NATIVE
def test_native_active_process_limit():
    code = PRE + "import subprocess\ntry:\n    p=subprocess.Popen([sys.executable,'-I','-S','-c','import time; time.sleep(30)'])\nexcept OSError:\n    sys.stdout.buffer.write(b'limited')\nelse:\n    p.wait(timeout=5)\n    assert p.returncode != 0\n    sys.stdout.buffer.write(b'limited')"
    assert w._run_trusted_fixture(code, b'x', b'limited', lambda: None,
                                  limits=w.JobLimits(active_processes=1)) == b'limited'


@NATIVE
def test_native_host_crash_closes_job_and_kills_child(tmp_path):
    # Observe via a process handle with SYNCHRONIZE only, never terminate by PID.
    host_code = """
import sys, subprocess, time
sys.path.insert(0, sys.argv[1])
from tapi_gate0.asset_windows_job import WindowsJob, JobLimits
job=WindowsJob(JobLimits())
child=subprocess.Popen([sys.executable,'-I','-S','-c',
    'import sys,time; assert sys.stdin.buffer.read()==b\\\'x\\\'; time.sleep(30)'],
    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
job.assign(child)
child.stdin.write(b'x'); child.stdin.close()
print(child.pid, flush=True)
time.sleep(30)
"""
    src = str(Path(w.__file__).resolve().parents[1])
    marker = tmp_path / "host.stdout"
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    k.WaitForSingleObject.restype = w.DWORD
    k.CloseHandle.argtypes = [w.HANDLE]
    k.CloseHandle.restype = w.BOOL
    child_handle = None
    with marker.open("wb") as out:
        host = subprocess.Popen([sys.executable, "-I", "-S", "-c", host_code, src],
                                stdout=out, stderr=subprocess.DEVNULL, close_fds=True)
        try:
            deadline = time.monotonic() + 10
            while not marker.read_bytes().strip():
                assert host.poll() is None and time.monotonic() < deadline
                time.sleep(0.05)
            pid = int(marker.read_text().strip())
            child_handle = k.OpenProcess(0x00100000, False, pid)
            assert child_handle and k.WaitForSingleObject(child_handle, 0) == 258
            host.kill()
            host.wait(timeout=5)
            assert k.WaitForSingleObject(child_handle, 5000) == 0
        finally:
            if host.poll() is None:
                host.kill(); host.wait(timeout=5)
            if child_handle:
                k.CloseHandle(child_handle)
    # Allow kernel disposal after the terminated process handle is released.
    deadline = time.monotonic() + 5
    while True:
        try:
            job = w.WindowsJob(w.JobLimits())
            job.close()
            break
        except w.JobError as exc:
            if str(exc) != "SESSION_JOB_BUSY" or time.monotonic() >= deadline:
                raise
            time.sleep(0.05)
