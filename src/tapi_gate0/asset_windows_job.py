"""Windows-only kernel job for trusted synthetic probes, not a security sandbox.

No arbitrary processor/command is exposed by this module. The trusted child must
block on its stdin before any work, spawning or reading assets; assignment occurs
before the parent supplies bytes. An unnamed process handle and a session-local
named job prevent PID reuse and overlapping supervised probes respectively.
No network, token, filesystem, GPU or hostile-host isolation is claimed.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import dataclass
import os
import subprocess
import sys
import time


class JobError(RuntimeError):
    pass


# Windows ABI types have fixed widths, including on the portable test host.
DWORD = C.c_uint32
SIZE_T = C.c_size_t
HANDLE = C.c_void_p
BOOL = C.c_int32
LARGE_INTEGER = C.c_int64
JOB_NAME = r"Local\TAPI.Stone.A02.Synthetic.v2"
JOB_TIME = 0x00000004
ACTIVE_PROCESS = 0x00000008
JOB_MEMORY = 0x00000200
KILL_ON_CLOSE = 0x00002000
FLAGS = JOB_TIME | ACTIVE_PROCESS | JOB_MEMORY | KILL_ON_CLOSE
ERROR_ALREADY_EXISTS = 183
EXTENDED = 9
ACCOUNTING = 1
END_OF_JOB_TIME = 6


class BasicLimits(C.Structure):
    _fields_ = [("PerProcessUserTimeLimit", LARGE_INTEGER),
                ("PerJobUserTimeLimit", LARGE_INTEGER), ("LimitFlags", DWORD),
                ("MinimumWorkingSetSize", SIZE_T), ("MaximumWorkingSetSize", SIZE_T),
                ("ActiveProcessLimit", DWORD), ("Affinity", SIZE_T),
                ("PriorityClass", DWORD), ("SchedulingClass", DWORD)]


class IOCounters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedLimits(C.Structure):
    _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IOCounters),
                ("ProcessMemoryLimit", SIZE_T), ("JobMemoryLimit", SIZE_T),
                ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T)]


class Accounting(C.Structure):
    _fields_ = [(name, LARGE_INTEGER) for name in ("TotalUserTime", "TotalKernelTime",
        "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")] + [(name, DWORD) for name in (
        "TotalPageFaultCount", "TotalProcesses", "ActiveProcesses", "TotalTerminatedProcesses")]


@dataclass(frozen=True)
class JobLimits:
    memory_mib: int = 128
    cpu_user_seconds: int = 4
    active_processes: int = 2
    wall_seconds: int = 15

    def __post_init__(self):
        for value, low, high in ((self.memory_mib, 64, 512), (self.cpu_user_seconds, 1, 10),
                                 (self.active_processes, 1, 4), (self.wall_seconds, 1, 30)):
            if type(value) is not int or not low <= value <= high:
                raise JobError("LIMIT_INVALID")


def _native_api():
    if sys.platform != "win32" or C.sizeof(HANDLE) != 8:
        raise JobError("WINDOWS_X64_REQUIRED")
    k = C.WinDLL("kernel32", use_last_error=True)
    declarations = {
        "CreateJobObjectW": ([C.c_void_p, C.c_wchar_p], HANDLE),
        "SetInformationJobObject": ([HANDLE, C.c_int, C.c_void_p, DWORD], BOOL),
        "QueryInformationJobObject": ([HANDLE, C.c_int, C.c_void_p, DWORD, C.c_void_p], BOOL),
        "AssignProcessToJobObject": ([HANDLE, HANDLE], BOOL),
        "TerminateJobObject": ([HANDLE, DWORD], BOOL),
        "CloseHandle": ([HANDLE], BOOL),
    }
    for name, (args, result) in declarations.items():
        fn = getattr(k, name)
        fn.argtypes, fn.restype = args, result
    return k


class WindowsJob:
    """One session-local trusted supervisor at a time; no breakaway flags."""
    def __init__(self, limits: JobLimits):
        if not isinstance(limits, JobLimits):
            raise JobError("LIMIT_INVALID")
        self.api = _native_api()
        self.handle = None
        C.set_last_error(0)
        h = self.api.CreateJobObjectW(None, JOB_NAME)
        error = C.get_last_error()
        if not h:
            raise JobError("CREATE_FAILED")
        if error == ERROR_ALREADY_EXISTS:
            self.api.CloseHandle(h)
            raise JobError("SESSION_JOB_BUSY")
        self.handle = h
        try:
            info = ExtendedLimits()
            basic = info.BasicLimitInformation
            basic.LimitFlags = FLAGS
            basic.PerJobUserTimeLimit = limits.cpu_user_seconds * 10_000_000
            basic.ActiveProcessLimit = limits.active_processes
            info.JobMemoryLimit = limits.memory_mib * 1024 * 1024
            self._set(EXTENDED, info)
            # JOB_OBJECT_TERMINATE_AT_END_OF_JOB (0), explicit not default-only.
            self._set(END_OF_JOB_TIME, DWORD(0))
            actual = self._query(EXTENDED, ExtendedLimits)
            b = actual.BasicLimitInformation
            if (b.LimitFlags != FLAGS or b.PerJobUserTimeLimit != basic.PerJobUserTimeLimit
                    or b.ActiveProcessLimit != limits.active_processes
                    or actual.JobMemoryLimit != info.JobMemoryLimit
                    or self._query(END_OF_JOB_TIME, DWORD).value != 0):
                raise JobError("LIMIT_READBACK_MISMATCH")
        except BaseException:
            self.close()
            raise

    def _set(self, cls, value):
        if not self.api.SetInformationJobObject(self.handle, cls, C.byref(value), C.sizeof(value)):
            raise JobError("LIMIT_SET_FAILED")

    def _query(self, cls, typ):
        value = typ()
        if not self.api.QueryInformationJobObject(self.handle, cls, C.byref(value), C.sizeof(value), None):
            raise JobError("QUERY_FAILED")
        return value

    def assign(self, process):
        # CPython Windows Popen owns this live process handle. No PID reopening.
        handle = getattr(process, "_handle", None)
        if handle is None or not self.api.AssignProcessToJobObject(self.handle, HANDLE(int(handle))):
            raise JobError("ASSIGN_FAILED")

    def active(self):
        return self._query(ACCOUNTING, Accounting).ActiveProcesses

    def terminate(self):
        if not self.api.TerminateJobObject(self.handle, 1):
            raise JobError("TERMINATE_FAILED")

    def wait_empty(self, timeout=5):
        deadline = time.monotonic() + timeout
        while self.active():
            if time.monotonic() >= deadline:
                raise JobError("TREE_NOT_EMPTY")
            time.sleep(0.025)

    def close(self):
        if self.handle is not None:
            h, self.handle = self.handle, None
            if not self.api.CloseHandle(h):
                raise JobError("CLOSE_FAILED")


def _run_trusted_fixture(code, data, expected, check, *, limits=JobLimits()):
    """Private host/test primitive; fixed trusted child code and tiny input/output.

    Child must block on stdin before work and have bounded output by construction.
    Not a generic command runner: communicate buffers trusted output, and no
    untrusted adapter is allowed. Wall deadline is checked between calls; a
    blocking rights/DB check or OS call may delay observation. Kernel limits apply
    after assignment. No input sent until assignment and rights check succeed.
    """
    if type(data) is not bytes or not 1 <= len(data) <= 64 or type(expected) is not bytes or len(expected) > 64:
        raise JobError("FIXTURE_BOUNDS")
    check()
    deadline = time.monotonic() + limits.wall_seconds
    job = WindowsJob(limits)
    process = None
    assigned = False
    try:
        env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ}
        process = subprocess.Popen([sys.executable, "-I", "-S", "-c", code],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, shell=False, close_fds=True)
        job.assign(process)
        assigned = True
        first = True
        while True:
            check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JobError("TIMEOUT")
            try:
                output, _ = process.communicate(input=data if first else None, timeout=min(0.25, remaining))
                break
            except subprocess.TimeoutExpired:
                first = False
        check()
        if time.monotonic() > deadline:
            raise JobError("TIMEOUT")
        if process.returncode != 0 or output != expected:
            raise JobError("PROBE_OUTPUT_INVALID")
        if job.active():
            raise JobError("DESCENDANTS_REMAIN")
    finally:
        try:
            if process is not None:
                if assigned:
                    # Terminate all descendants on *any* return/error before
                    # releasing the kernel singleton. No receipt if cleanup fails.
                    if job.active():
                        job.terminate()
                elif process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
                process.wait(timeout=5)
            job.wait_empty()
        finally:
            # Also kills associated children if a previous cleanup call failed.
            job.close()
    check()
    return output
