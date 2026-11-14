#!/usr/bin/env python3
"""Run a command in an OS process container and retain subprocess.run semantics."""
import os
import signal
import subprocess
import sys


def _drain_after_kill(process, original_timeout):
    """Bound pipe draining if an escaped process still holds a pipe open."""
    try:
        return process.communicate(timeout=1)
    except subprocess.TimeoutExpired as exc:
        # POSIX communicate has no background reader threads. Preserve any
        # partial bytes reported by communicate and stop waiting for escaped FDs.
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        process.wait(timeout=1)
        return exc.output if exc.output is not None else original_timeout.output, \
            exc.stderr if exc.stderr is not None else original_timeout.stderr


def run(command, *, cwd, stdin, capture_output, text, encoding, errors, timeout):
    if sys.platform == "win32":
        import windows_job
        return windows_job.run(command, cwd=cwd, stdin=stdin, capture_output=capture_output,
                               text=text, encoding=encoding, errors=errors, timeout=timeout)
    if os.name != "posix":
        raise OSError("process containment is not supported on this platform")
    process = subprocess.Popen(command, cwd=cwd, stdin=stdin,
                               stdout=subprocess.PIPE if capture_output else None,
                               stderr=subprocess.PIPE if capture_output else None,
                               text=text, encoding=encoding, errors=errors, start_new_session=True)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as original_timeout:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = _drain_after_kill(process, original_timeout)
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        # Clear remaining group members after normal exit too.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
