#!/usr/bin/env python3
"""Start a gated process inside a Windows kill-on-close Job Object."""
import ctypes
import subprocess
import sys
import threading
from ctypes import wintypes
from pathlib import Path


class BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedLimit(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


BOOTSTRAP = ("import subprocess,sys; "
             "ok=sys.stdin.buffer.read(1); "
             "sys.exit(subprocess.call(sys.argv[1:],stdin=subprocess.DEVNULL) if ok==b'1' else 125)")


def bootstrap_python():
    # Only the stdlib-only gate uses the base interpreter. The requested command
    # retains its original executable and environment (including virtualenv).
    base = Path(sys.base_prefix) / "python.exe"
    return str(base) if base.is_file() else sys.executable


def run(command, *, cwd, stdin, capture_output, text, encoding, errors, timeout):
    if sys.platform != "win32" or not command:
        raise RuntimeError("Windows and a command are required")
    if stdin != subprocess.DEVNULL:
        raise ValueError("Windows job runner requires DEVNULL stdin")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # This evaluator owns the sole, non-inheritable job handle. Its death closes
    # the handle in the OS; no extra Python supervisor or parent monitor is needed.
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    process = None
    watcher = None
    close_lock = threading.Lock()

    def close_job():
        nonlocal job
        with close_lock:
            if job is not None:
                kernel.CloseHandle(job)
                job = None

    try:
        limits = ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE; breakaway disabled
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        # Bootstrap cannot start the requested program before it has been assigned to the job.
        process = subprocess.Popen([bootstrap_python(), "-I", "-S", "-B", "-c", BOOTSTRAP, *command], cwd=cwd,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE if capture_output else None,
                                   stderr=subprocess.PIPE if capture_output else None,
                                   text=text, encoding=encoding, errors=errors)
        if not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
            raise ctypes.WinError(ctypes.get_last_error())

        def close_after_root_exit():
            process.wait()
            # Descendants may hold stdout/stderr open after the root exits.
            # Closing the job here lets communicate() drain those pipes too.
            close_job()

        watcher = threading.Thread(target=close_after_root_exit, daemon=True)
        watcher.start()
        try:
            stdout, stderr = process.communicate("1" if process.text_mode else b"1", timeout=timeout)
        except subprocess.TimeoutExpired:
            close_job()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        close_job()
        if watcher is not None and watcher.ident is not None:
            watcher.join()
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
