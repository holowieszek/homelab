#!/usr/bin/env python3
"""Run only repository-approved osquery queries; emit sanitized JSON snapshots."""
from __future__ import annotations
import argparse
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "audit/osquery/queries/approved.json"
SCHEMA_VERSION = "1.0"
MAX_OUTPUT_BYTES = 1_000_000
SENSITIVE = re.compile(r"(?i)(password|secret|token|private.?key|kubeconfig|serial|uuid|environment|dns.?query)")


class OutputLimitExceeded(ValueError):
    """Raised after terminating a collector that exceeds its byte budget."""


def _run_bounded(command: list[str], env: dict[str, str], timeout: int,
                 max_bytes: int = MAX_OUTPUT_BYTES) -> subprocess.CompletedProcess:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, start_new_session=(os.name == "posix"))
    selector = selectors.DefaultSelector()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    assert process.stdout is not None and process.stderr is not None
    stdout_pipe, stderr_pipe = process.stdout, process.stderr

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
        selector.register(stdout_pipe, selectors.EVENT_READ, "stdout")
        selector.register(stderr_pipe, selectors.EVENT_READ, "stderr")
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


def _run_osquery(arguments: list[str], transport: str, alias: str, timeout: int, category: str,
                ssh_config: str | None = None):
    env = {"PATH": os.defpath, "HOME": os.path.expanduser("~")}
    if transport == "local":
        command = ["osqueryi", *arguments]
    elif transport == "ssh":
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}", alias):
            raise ValueError("SSH host alias contains unsupported characters")
        if os.environ.get("SSH_AUTH_SOCK"):
            env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        action = "version" if arguments == ["--version"] else category
        command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes"]
        if ssh_config:
            command.extend(["-F", ssh_config])
        command.extend([alias, "homelab-audit " + action])
    else:
        raise ValueError("unsupported transport")
    return _run_bounded(command, env=env, timeout=timeout)


def collect(category: str, alias: str, role: str, sha: str, timeout: int = 15,
            transport: str = "local", ssh_config: str | None = None) -> dict:
    pack = json.loads(PACK.read_text())
    if category not in pack["queries"]:
        raise ValueError("category is not in the approved query pack")
    sql = pack["queries"][category]
    if not sql.lstrip().upper().startswith("SELECT ") or ";" in sql.rstrip("; "):
        raise ValueError("approved query violates read-only single-statement policy")
    version = "unknown"
    try:
        version_proc = _run_osquery(["--version"], transport, alias, timeout, category, ssh_config)
        if version_proc.returncode == 0:
            version = version_proc.stdout.strip()[:80] or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc = _run_osquery(["--json", sql], transport, alias, timeout, category, ssh_config)
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
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError, json.JSONDecodeError) as exc:
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
    ap.add_argument("--ssh-config", type=Path, help="Optional SSH config file for strict alias resolution")
    ap.add_argument("--output", type=Path, required=True, help="Private JSON destination outside the repository")
    args = ap.parse_args()
    if not 1 <= args.timeout <= 120:
        ap.error("--timeout must be between 1 and 120 seconds")
    if args.transport == "ssh" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}", args.host_alias):
        ap.error("SSH requires a simple OpenSSH Host alias (letters, digits, dot, underscore, hyphen)")
    if args.ssh_config and args.transport != "ssh":
        ap.error("--ssh-config is only valid with --transport ssh")
    ssh_config = args.ssh_config.expanduser().resolve() if args.ssh_config else None
    if ssh_config and not ssh_config.is_file():
        ap.error("--ssh-config must name an existing regular file")
    destination = args.output.expanduser().resolve()
    try:
        destination.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        ap.error("audit output must be outside the repository")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = collect(args.category, args.host_alias, args.host_role, args.commit, args.timeout,
                     args.transport, str(ssh_config) if ssh_config else None)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write(chr(10))
    print(f"status={result['collection_status']} output={destination}")
    return 0 if result["collection_status"] == "OK" else 2

if __name__ == "__main__":
    sys.exit(main())
