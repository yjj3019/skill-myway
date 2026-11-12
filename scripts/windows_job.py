#!/usr/bin/env python3
"""Start a gated process inside a Windows kill-on-close Job Object."""
import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes


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


def main(parent_pid, command):
    if sys.platform != "win32" or not command or parent_pid <= 0:
        raise RuntimeError("Windows and a command are required")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    parent = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE
    if not parent:
        raise ctypes.WinError(ctypes.get_last_error())
    if kernel.WaitForSingleObject(parent, 0) != 0x00000102:  # WAIT_TIMEOUT
        kernel.CloseHandle(parent)
        raise RuntimeError("parent is no longer running")
    def stop_if_parent_exits():
        # Exiting the supervisor closes its job handle and terminates the job members.
        kernel.WaitForSingleObject(parent, 0xFFFFFFFF)
        os._exit(125)
    threading.Thread(target=stop_if_parent_exits, daemon=True).start()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    process = None
    try:
        limits = ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE; breakaway disabled
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        # Bootstrap cannot start the requested program before it has been assigned to the job.
        process = subprocess.Popen([sys.executable, "-c", BOOTSTRAP, *command], stdin=subprocess.PIPE)
        if not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
            raise ctypes.WinError(ctypes.get_last_error())
        process.stdin.write(b"1")
        process.stdin.close()
        return process.wait()
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        kernel.CloseHandle(job)
        # Keep the parent handle open while the daemon thread is waiting; process exit closes it.


if __name__ == "__main__":
    try:
        sys.exit(main(int(sys.argv[1]), sys.argv[2:]))
    except (OSError, RuntimeError, ValueError, IndexError) as exc:
        print(f"job setup failed: {exc}", file=sys.stderr)
        sys.exit(125)
