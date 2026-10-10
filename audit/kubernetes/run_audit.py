#!/usr/bin/env python3
"""Read-only Kubernetes inventory using a dedicated ServiceAccount identity."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import collect
from collect import ConfigurationError, collect_snapshot
from create_reader_kubeconfig import create_reader_kubeconfig

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "audit/kubernetes/readonly-access.json"


class AuditSetupError(RuntimeError):
    pass


def validate_manifest(manifest: list[dict]) -> None:
    """Fail closed when declared RBAC diverges from the explicit collector scope."""
    if not isinstance(manifest, list) or not manifest:
        raise AuditSetupError("invalid access manifest")
    roles = [obj for obj in manifest if obj.get("kind") == "ClusterRole"]
    accounts = [obj for obj in manifest if obj.get("kind") == "ServiceAccount"]
    bindings = [obj for obj in manifest if obj.get("kind") == "ClusterRoleBinding"]
    if len(roles) != 1 or len(accounts) != 1 or len(bindings) != 1:
        raise AuditSetupError("manifest must define one ClusterRole, ServiceAccount, and binding")

    expected = set()
    for resource in collect.RESOURCES:
        group = resource.path.split("/")[2] if resource.path.startswith("/apis/") else ""
        expected.add((group, resource.path.rstrip("/").split("/")[-1]))
    actual = set()
    for rule in roles[0].get("rules", []):
        groups = rule.get("apiGroups", [])
        if len(groups) != 1 or set(rule.get("verbs", [])) != {"get", "list"}:
            raise AuditSetupError("manifest exceeds read-only permission policy")
        for name in rule.get("resources", []):
            pair = (groups[0], name)
            if pair not in expected or pair in actual or "/" in name:
                raise AuditSetupError("manifest includes unapproved or duplicate resources")
            actual.add(pair)
    if actual != expected:
        raise AuditSetupError("manifest permissions do not exactly match collector resources")
    account = accounts[0]
    if account.get("automountServiceAccountToken") is not False:
        raise AuditSetupError("ServiceAccount token automount must remain disabled")
    subject = {"kind": "ServiceAccount", "name": account["metadata"]["name"],
               "namespace": account["metadata"]["namespace"]}
    binding = bindings[0]
    if (binding.get("subjects") != [subject]
            or binding.get("roleRef", {}).get("name") != roles[0]["metadata"]["name"]):
        raise AuditSetupError("ClusterRoleBinding subject or role reference is inconsistent")


def collect_snapshot_with_reader(reader_kubeconfig: Path, output: Path, *,
                                 kubectl: str, timeout: int) -> dict[str, Any]:
    """Require an explicitly prepared least-privilege kubeconfig for API requests."""
    reader = reader_kubeconfig.expanduser().resolve()
    if not reader.is_file() or reader.stat().st_mode & 0o077:
        raise AuditSetupError("reader kubeconfig must be a private regular file")
    return collect_snapshot(reader, output, kubectl=kubectl, timeout=timeout)


def collect_with_admin(admin_kubeconfig: Path, output: Path, *, context: str | None,
                       kubectl: str, timeout: int) -> dict[str, Any]:
    """Mint a short-lived reader kubeconfig, collect, then remove the credential file."""
    destination = collect.prepare_output(output)
    reader_path = destination.parent / ("." + destination.name + ".reader.kubeconfig")
    if reader_path.exists() or reader_path.is_symlink():
        raise AuditSetupError("temporary reader kubeconfig path already exists")
    try:
        create_reader_kubeconfig(admin_kubeconfig, reader_path,
                                 context=context, kubectl=kubectl)
        return collect_snapshot(reader_path, destination, kubectl=kubectl, timeout=timeout)
    finally:
        reader_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--reader-kubeconfig", type=Path,
                        help="private kubeconfig for the dedicated read-only ServiceAccount")
    choice.add_argument("--admin-kubeconfig", type=Path,
                        help="private admin kubeconfig used only to mint a temporary reader token")
    parser.add_argument("--context", help="optional context from the admin kubeconfig")
    parser.add_argument("--output", required=True, type=Path,
                        help="new private snapshot path outside the repository")
    parser.add_argument("--kubectl", default="kubectl")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error("--timeout must be between 1 and 120 seconds")
    try:
        manifest = json.loads(MANIFEST.read_text())
        validate_manifest(manifest)
        if args.reader_kubeconfig:
            result = collect_snapshot_with_reader(args.reader_kubeconfig, args.output,
                                                  kubectl=args.kubectl, timeout=args.timeout)
        else:
            result = collect_with_admin(args.admin_kubeconfig, args.output,
                                        context=args.context, kubectl=args.kubectl,
                                        timeout=args.timeout)
    except (AuditSetupError, ConfigurationError, OSError, json.JSONDecodeError) as exc:
        message = str(exc) if isinstance(exc, (AuditSetupError, ConfigurationError)) else "local file operation failed"
        print("cluster inventory failed: " + message, file=sys.stderr)
        return 2
    counts = {}
    for record in result["resources"]:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    print(f"status={result['collection_status']} resources={len(result['resources'])} "
          f"output={args.output.expanduser().resolve()} outcomes={json.dumps(counts, sort_keys=True)}")
    return 0 if result["collection_status"] == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
