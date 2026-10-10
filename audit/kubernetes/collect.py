#!/usr/bin/env python3
"""Collect a secret-free, read-only inventory using Kubernetes Table responses."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN_NAMESPACE = "homelab-audit"
TOKEN_SERVICE_ACCOUNT = "cluster-inventory"
TOKEN_DURATION = "10m"
TABLE_ACCEPT = "application/json;as=Table;g=meta.k8s.io;v=v1"
PAGE_SIZE = 200
MAX_PAGES = 100
MAX_ROWS = 20_000
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PROCESS_OUTPUT_BYTES = 8 * 1024 * 1024
PROCESS_TIMEOUT_SECONDS = 60


class AuditError(RuntimeError):
    """A safe-to-report audit failure; contains no credential or API body."""


class ConfigurationError(AuditError):
    pass


class UnsafeResponse(AuditError):
    pass


@dataclass(frozen=True)
class Resource:
    name: str
    path: str
    scope: str
    columns: tuple[str, ...]
    required: bool = True


def _r(name: str, path: str, columns: str = "Name|Namespace|Age", *,
       scope: str = "namespaced", required: bool = True) -> Resource:
    return Resource(name, path, scope, tuple(columns.split("|")), required)


RESOURCES = (
    _r("namespaces", "/api/v1/namespaces", "Name|Status|Age", scope="cluster"),
    _r("nodes", "/api/v1/nodes", "Name|Status|Roles|Age|Version", scope="cluster"),
    _r("pods", "/api/v1/pods", "Name|Namespace|Ready|Status|Restarts|Age"),
    _r("services", "/api/v1/services", "Name|Namespace|Type|Ports|Age"),
    _r("serviceaccounts", "/api/v1/serviceaccounts"),
    _r("persistentvolumeclaims", "/api/v1/persistentvolumeclaims", "Name|Namespace|Status|Volume|Capacity|Access Modes|StorageClass|Age"),
    _r("persistentvolumes", "/api/v1/persistentvolumes", "Name|Capacity|Access Modes|Reclaim Policy|Status|Claim|StorageClass|Age", scope="cluster"),
    _r("deployments", "/apis/apps/v1/deployments", "Name|Namespace|Ready|Up-to-date|Available|Age"),
    _r("daemonsets", "/apis/apps/v1/daemonsets", "Name|Namespace|Desired|Current|Ready|Up-to-date|Available|Age"),
    _r("replicasets", "/apis/apps/v1/replicasets", "Name|Namespace|Desired|Current|Ready|Age"),
    _r("statefulsets", "/apis/apps/v1/statefulsets", "Name|Namespace|Ready|Age"),
    _r("jobs", "/apis/batch/v1/jobs", "Name|Namespace|Completions|Duration|Age"),
    _r("cronjobs", "/apis/batch/v1/cronjobs", "Name|Namespace|Schedule|Suspend|Active|Last Schedule|Age"),
    _r("ingresses", "/apis/networking.k8s.io/v1/ingresses", "Name|Namespace|Class|Hosts|Ports|Age"),
    _r("networkpolicies", "/apis/networking.k8s.io/v1/networkpolicies"),
    _r("storageclasses", "/apis/storage.k8s.io/v1/storageclasses", "Name|Provisioner|ReclaimPolicy|VolumeBindingMode|AllowVolumeExpansion|Age", scope="cluster"),
    _r("roles", "/apis/rbac.authorization.k8s.io/v1/roles"),
    _r("rolebindings", "/apis/rbac.authorization.k8s.io/v1/rolebindings"),
    _r("clusterroles", "/apis/rbac.authorization.k8s.io/v1/clusterroles", scope="cluster"),
    _r("clusterrolebindings", "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings", scope="cluster"),
    _r("customresourcedefinitions", "/apis/apiextensions.k8s.io/v1/customresourcedefinitions", scope="cluster"),
    _r("applications.argoproj.io", "/apis/argoproj.io/v1alpha1/applications", required=False),
    _r("applicationsets.argoproj.io", "/apis/argoproj.io/v1alpha1/applicationsets", required=False),
    _r("appprojects.argoproj.io", "/apis/argoproj.io/v1alpha1/appprojects", required=False),
    _r("clusters.postgresql.cnpg.io", "/apis/postgresql.cnpg.io/v1/clusters", required=False),
    _r("scheduledbackups.postgresql.cnpg.io", "/apis/postgresql.cnpg.io/v1/scheduledbackups", required=False),
    _r("externalsecrets.external-secrets.io", "/apis/external-secrets.io/v1beta1/externalsecrets", required=False),
    _r("pushsecrets.external-secrets.io", "/apis/external-secrets.io/v1alpha1/pushsecrets", required=False),
    _r("certificates.cert-manager.io", "/apis/cert-manager.io/v1/certificates", required=False),
    _r("issuers.cert-manager.io", "/apis/cert-manager.io/v1/issuers", required=False),
    _r("clusterissuers.cert-manager.io", "/apis/cert-manager.io/v1/clusterissuers", scope="cluster", required=False),
    _r("volumes.longhorn.io", "/apis/longhorn.io/v1beta2/volumes", required=False),
    _r("recurringjobs.longhorn.io", "/apis/longhorn.io/v1beta2/recurringjobs", required=False),
)
RESOURCES_BY_NAME = {resource.name: resource for resource in RESOURCES}


def _normal_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def parse_table(payload: dict[str, Any], resource: Resource) -> dict[str, Any]:
    """Project a Table response to explicitly approved columns only."""
    if payload.get("apiVersion") != "meta.k8s.io/v1" or payload.get("kind") != "Table":
        raise UnsafeResponse("API did not return a Table response; refusing object fallback")
    definitions = payload.get("columnDefinitions")
    rows = payload.get("rows")
    if not isinstance(definitions, list) or not isinstance(rows, list):
        raise UnsafeResponse("malformed Table response")
    allowed = {_normal_column(name): name for name in resource.columns}
    selected: list[tuple[int, str]] = []
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict) or not isinstance(definition.get("name"), str):
            raise UnsafeResponse("malformed Table column")
        canonical = allowed.get(_normal_column(definition["name"]))
        if canonical:
            selected.append((index, canonical))
    if "Name" not in {name for _, name in selected}:
        raise UnsafeResponse("Table response has no approved name column")

    projected = []
    for row in rows:
        if not isinstance(row, dict) or row.get("object") is not None:
            raise UnsafeResponse("Table response unexpectedly contains full objects")
        cells = row.get("cells")
        if not isinstance(cells, list) or len(cells) != len(definitions):
            raise UnsafeResponse("malformed Table row")
        item: dict[str, Any] = {}
        for index, name in selected:
            value = cells[index]
            if value is None or isinstance(value, (dict, list)):
                continue
            if isinstance(value, str):
                if len(value) > 256 or any(ord(char) < 32 and char not in "\t" for char in value):
                    continue
            elif not isinstance(value, (int, float, bool)):
                continue
            item[name] = value
        if "Name" not in item:
            raise UnsafeResponse("Table row has no approved name")
        projected.append(item)
    projected.sort(key=lambda item: (str(item.get("Namespace", "")), str(item["Name"])))
    columns = [name for _, name in selected]
    return {"columns": columns, "items": projected}


def page_url(base_url: str, continue_token: str | None = None) -> str:
    query = {"limit": str(PAGE_SIZE), "includeObject": "None"}
    if continue_token:
        query["continue"] = continue_token
    return base_url + "?" + urllib.parse.urlencode(query)


def request_table(base_url: str, resource: Resource, opener: Any,
                  timeout: int = 30) -> dict[str, Any]:
    """Retrieve only server-side Table responses; never fall back to full JSON."""
    items: list[dict[str, Any]] = []
    columns: list[str] = []
    continue_token: str | None = None
    for _ in range(MAX_PAGES):
        req = urllib.request.Request(
            page_url(base_url + resource.path, continue_token),
            headers={"Accept": TABLE_ACCEPT, "User-Agent": "homelab-cluster-inventory/1"},
            method="GET",
        )
        try:
            with opener.open(req, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            code = {403: "FORBIDDEN", 404: "NOT_FOUND", 406: "TABLE_UNSUPPORTED"}.get(exc.code, "API_ERROR")
            exc.close()
            if code == "NOT_FOUND" and not resource.required:
                code = "ABSENT"
            elif code == "NOT_FOUND":
                code = "UNAVAILABLE"
            return {"resource": resource.name, "status": code, "columns": [], "items": []}
        except (urllib.error.URLError, TimeoutError, OSError):
            return {"resource": resource.name, "status": "UNAVAILABLE", "columns": [], "items": []}
        if len(raw) > MAX_RESPONSE_BYTES:
            return {"resource": resource.name, "status": "RESPONSE_TOO_LARGE", "columns": [], "items": []}
        try:
            payload = json.loads(raw)
            table = parse_table(payload, resource)
        except (json.JSONDecodeError, UnsafeResponse):
            return {"resource": resource.name, "status": "UNSAFE_RESPONSE", "columns": [], "items": []}
        if not columns:
            columns = table["columns"]
        items.extend(table["items"])
        if len(items) > MAX_ROWS:
            return {"resource": resource.name, "status": "ROW_LIMIT", "columns": [], "items": []}
        continue_token = payload.get("metadata", {}).get("continue")
        if not continue_token:
            return {"resource": resource.name, "status": "OK", "columns": columns, "items": items}
    return {"resource": resource.name, "status": "PAGE_LIMIT", "columns": [], "items": []}


def minimal_kubeconfig(view: dict[str, Any], token: str) -> dict[str, Any]:
    """Build a token-only kubeconfig; never copy admin user credentials."""
    clusters = view.get("clusters", [])
    if len(clusters) != 1 or not isinstance(clusters[0].get("cluster"), dict):
        raise ConfigurationError("admin kubeconfig must resolve to exactly one cluster context")
    source = clusters[0]["cluster"]
    server = source.get("server")
    ca_data = source.get("certificate-authority-data")
    if not isinstance(server, str) or not server.startswith("https://"):
        raise ConfigurationError("cluster endpoint must use HTTPS")
    if source.get("insecure-skip-tls-verify") or not isinstance(ca_data, str):
        raise ConfigurationError("verified TLS CA data is required")
    try:
        base64.b64decode(ca_data, validate=True)
    except (ValueError, binascii.Error):
        raise ConfigurationError("invalid cluster CA data") from None
    if not isinstance(token, str) or not token.strip() or "\n" in token:
        raise ConfigurationError("TokenRequest returned no usable token")
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": "homelab-audit-target", "cluster": {
            "server": server, "certificate-authority-data": ca_data}}],
        "users": [{"name": "homelab-audit-reader", "user": {"token": token.strip()}}],
        "contexts": [{"name": "homelab-audit-reader", "context": {
            "cluster": "homelab-audit-target", "user": "homelab-audit-reader"}}],
        "current-context": "homelab-audit-reader",
    }


def _kubectl_prefix(kubectl: str, kubeconfig: Path, context: str | None = None) -> list[str]:
    args = [kubectl, "--kubeconfig", str(kubeconfig)]
    if context:
        args += ["--context", context]
    return args


def _run_bounded(command: list[str], timeout: int = PROCESS_TIMEOUT_SECONDS,
                 max_bytes: int = PROCESS_OUTPUT_BYTES) -> subprocess.CompletedProcess:
    """Bound local CLI output and runtime, and never include stderr in exceptions."""
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=(os.name == "posix"))
    except OSError:
        raise AuditError("kubectl executable could not be started") from None
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout

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
                raise AuditError("local kubectl command timed out")
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, min(65536, max_bytes - total + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > max_bytes:
                    terminate()
                    raise AuditError("local kubectl output exceeded its limit")
                output[key.data].extend(chunk)
        returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return subprocess.CompletedProcess(command, returncode,
            output["stdout"].decode("utf-8", errors="replace"),
            output["stderr"].decode("utf-8", errors="replace"))
    except BaseException:
        if process.poll() is None:
            terminate()
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()


def prepare_output(path: Path, repo_root: Path = REPO_ROOT) -> Path:
    destination = path.expanduser().resolve()
    root = repo_root.resolve()
    try:
        destination.relative_to(root)
    except ValueError:
        pass
    else:
        raise ConfigurationError("audit output must be outside the repository")
    if destination.exists() or destination.is_symlink():
        raise ConfigurationError("refusing to overwrite an existing output file")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not destination.parent.is_dir() or destination.parent.stat().st_mode & 0o077:
        raise ConfigurationError("output directory must be private (mode 0700)")
    return destination


def _write_private(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, 0o600)


def proxy_command(kubectl: str, kubeconfig: Path, listen_port: int = 0) -> list[str]:
    if not 0 <= listen_port <= 65535:
        raise ConfigurationError("proxy listen port must be between 0 and 65535")
    paths = "|".join(re.escape(resource.path) for resource in RESOURCES)
    accept_paths = "^(" + paths + ")$"
    return _kubectl_prefix(kubectl, kubeconfig) + [
        "proxy", "--address=127.0.0.1", f"--port={listen_port}",
        "--accept-hosts=^127\\.0\\.0\\.1$", "--accept-paths=" + accept_paths,
        "--reject-methods=^(POST|PUT|PATCH|DELETE|CONNECT)$",
    ]


def _start_proxy(command: list[str], timeout: int = 10) -> tuple[subprocess.Popen, str]:
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=(os.name == "posix"))
    except OSError:
        raise AuditError("kubectl proxy could not be started") from None
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    buffered = bytearray()
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AuditError("kubectl proxy exited before startup")
            events = selector.select(max(0.0, deadline - time.monotonic()))
            if not events:
                break
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            buffered.extend(chunk)
            match = re.search(rb"Starting to serve on 127\.0\.0\.1:(\d+)", buffered)
            if match:
                return process, "http://127.0.0.1:" + match.group(1).decode("ascii")
        raise AuditError("kubectl proxy did not report a loopback listener")
    except BaseException:
        _stop_proxy(process)
        raise
    finally:
        selector.close()


def _stop_proxy(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.stdout:
        process.stdout.close()


def collect_snapshot(kubeconfig: Path, output: Path, *,
                     kubectl: str = "kubectl", timeout: int = 30) -> dict[str, Any]:
    destination = prepare_output(output)
    reader_config = kubeconfig.expanduser().resolve()
    if not reader_config.is_file():
        raise ConfigurationError("read-only kubeconfig path is not a file")
    if reader_config.stat().st_mode & 0o077:
        raise ConfigurationError("read-only kubeconfig must be private (no group/other access)")
    process, base_url = _start_proxy(proxy_command(kubectl, reader_config))
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        records = [request_table(base_url, resource, opener, timeout) for resource in RESOURCES]
    finally:
        _stop_proxy(process)

    required_failures = [record["resource"] for record in records
                         if record["status"] not in ("OK", "ABSENT")
                         and RESOURCES_BY_NAME[record["resource"]].required]
    snapshot = {
        "schema_version": "1.0",
        "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "collection_mode": "read-only Kubernetes Table API",
        "resources": records,
        "collection_status": "PARTIAL" if required_failures else "OK",
        "required_resource_failures": required_failures,
    }
    _write_private(destination, json.dumps(snapshot, sort_keys=True, indent=2) + "\n")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", required=True, type=Path,
                        help="private kubeconfig for the dedicated read-only service account")
    parser.add_argument("--output", required=True, type=Path,
                        help="new private snapshot path outside the repository")
    parser.add_argument("--kubectl", default="kubectl", help="kubectl executable")
    parser.add_argument("--timeout", default=30, type=int, help="per-request timeout in seconds")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    try:
        snapshot = collect_snapshot(args.kubeconfig, args.output,
                                    kubectl=args.kubectl,
                                    timeout=args.timeout)
    except AuditError as exc:
        print("cluster inventory failed: " + str(exc), file=sys.stderr)
        return 2
    except OSError:
        print("cluster inventory failed: local file operation was unavailable", file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    for record in snapshot["resources"]:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    print(f"status={snapshot['collection_status']} resources={len(snapshot['resources'])} "
          f"output={args.output.expanduser().resolve()} outcomes={json.dumps(counts, sort_keys=True)}")
    return 0 if snapshot["collection_status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
