#!/usr/bin/env python3
"""Run only repository-approved osquery queries; emit sanitized JSON snapshots."""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "audit/osquery/queries/approved.json"
SCHEMA_VERSION = "1.0"
MAX_OUTPUT_BYTES = 1_000_000
SENSITIVE = re.compile(r"(?i)(password|secret|token|private.?key|kubeconfig|serial|uuid|environment|dns.?query)")


def _run_osquery(arguments: list[str], transport: str, alias: str, timeout: int, category: str):
    env = {"PATH": os.defpath, "HOME": os.path.expanduser("~")}
    if transport == "local":
        command = ["osqueryi", *arguments]
    elif transport == "ssh":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}", alias):
            raise ValueError("SSH host alias contains unsupported characters")
        if os.environ.get("SSH_AUTH_SOCK"):
            env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        action = "version" if arguments == ["--version"] else category
        command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", alias,
                   "homelab-audit " + action]
    else:
        raise ValueError("unsupported transport")
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout,
                          check=False, env=env)


def collect(category: str, alias: str, role: str, sha: str, timeout: int = 15,
            transport: str = "local") -> dict:
    pack = json.loads(PACK.read_text())
    if category not in pack["queries"]:
        raise ValueError("category is not in the approved query pack")
    sql = pack["queries"][category]
    if not sql.lstrip().upper().startswith("SELECT ") or ";" in sql.rstrip("; "):
        raise ValueError("approved query violates read-only single-statement policy")
    version = "unknown"
    try:
        version_proc = _run_osquery(["--version"], transport, alias, timeout, category)
        if version_proc.returncode == 0:
            version = version_proc.stdout.strip()[:80] or "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        proc = _run_osquery(["--json", sql], transport, alias, timeout, category)
        raw = proc.stdout
        if len(raw.encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("collector output exceeds size limit")
        if proc.returncode:
            raise RuntimeError("osquery returned non-zero status")
        if re.search(r"(?i)(no such table|no such column|permission denied|access denied|error)", proc.stderr):
            raise RuntimeError("osquery reported a table, column, or permission error")
        rows = json.loads(raw or "[]")
        facts = [{k: v for k, v in row.items() if not SENSITIVE.search(k)} for row in rows]
        status, errors = "OK", []
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        facts, status, errors = [], "UNVERIFIED", [type(exc).__name__]
    return {"schema_version": SCHEMA_VERSION,
            "audit_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "host_alias": alias, "host_role": role,
            "collector": {"name": "osqueryi", "version": version},
            "git_commit_sha": sha, "category": category, "observed_facts": facts,
            "collection_status": status, "errors": errors,
            "source": {"query_pack": "audit/osquery/queries/approved.json", "query_id": category}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", required=True, choices=json.loads(PACK.read_text())["queries"])
    ap.add_argument("--host-alias", required=True)
    ap.add_argument("--host-role", required=True)
    ap.add_argument("--commit", default="unknown")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--transport", choices=["local", "ssh"], default="local")
    ap.add_argument("--output", type=Path, required=True, help="Private JSON destination outside the repository")
    args = ap.parse_args()
    if args.transport == "ssh" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}", args.host_alias):
        ap.error("SSH requires a simple OpenSSH Host alias (letters, digits, dot, underscore, hyphen)")
    destination = args.output.expanduser().resolve()
    try:
        destination.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        ap.error("audit output must be outside the repository")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = collect(args.category, args.host_alias, args.host_role, args.commit, args.timeout, args.transport)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write(chr(10))
    print(f"status={result['collection_status']} output={destination}")
    return 0 if result["collection_status"] == "OK" else 2

if __name__ == "__main__":
    sys.exit(main())
