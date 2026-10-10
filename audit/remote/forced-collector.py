#!/usr/bin/env python3
"""Restricted OpenSSH ForceCommand collector; accepts category IDs, never SQL."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "osquery/queries/approved.json"
MAX_OUTPUT_BYTES = 1_000_000


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
        proc = subprocess.run(command, text=True, capture_output=True, timeout=15,
                              check=False, env=env)
        if len(proc.stdout.encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("collector output exceeds size limit")
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
