#!/usr/bin/env python3
"""Restricted OpenSSH ForceCommand collector; accepts category IDs, never SQL."""
from __future__ import annotations
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "osquery/queries/approved.json"
MAX_OUTPUT_BYTES = 1_000_000


class OutputLimitExceeded(ValueError):
    """Raised after terminating a collector that exceeds its byte budget."""


def run_bounded(command: list[str], env: dict[str, str], timeout: int,
                max_bytes: int = MAX_OUTPUT_BYTES) -> subprocess.CompletedProcess:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, start_new_session=(os.name == "posix"))
    selector = selectors.DefaultSelector()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    assert process.stdout is not None and process.stderr is not None

    def terminate() -> None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        process.wait()

    try:
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        total = 0
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate()
                raise subprocess.TimeoutExpired(command, timeout)
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, min(65536, max_bytes - total + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > max_bytes:
                    terminate()
                    raise OutputLimitExceeded("collector output exceeds byte limit")
                output[key.data].extend(chunk)
        try:
            returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            terminate()
            raise subprocess.TimeoutExpired(command, timeout)
        return subprocess.CompletedProcess(
            command, returncode,
            output["stdout"].decode("utf-8", errors="replace"),
            output["stderr"].decode("utf-8", errors="replace"))
    except BaseException:
        if process.poll() is None:
            terminate()
        raise
    finally:
        selector.close()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


def requested_action(raw: str) -> str:
    match = re.fullmatch(r"homelab-audit ([a-z][a-z0-9_-]{0,63})", raw.strip())
    if not match:
        raise ValueError("invalid forced collector request")
    action = match.group(1)
    allowed = set(json.loads(PACK.read_text())["queries"]) | {"version"}
    if action not in allowed:
        raise ValueError("unknown approved collector category")
    return action


def main() -> int:
    try:
        action = requested_action(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
        if action == "version":
            command = ["osqueryi", "--version"]
        else:
            sql = json.loads(PACK.read_text())["queries"][action]
            command = ["osqueryi", "--json", sql]
        env = {"PATH": os.defpath, "HOME": os.path.expanduser("~")}
        proc = run_bounded(command, env=env, timeout=15)
        if proc.returncode or re.search(r"(?i)(no such table|no such column|permission denied|access denied|error)", proc.stderr):
            print("approved collection unavailable", file=sys.stderr)
            return 2
        sys.stdout.write(proc.stdout)
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        print("approved collection unavailable", file=sys.stderr)
        return 2

if __name__ == "__main__":
    sys.exit(main())
