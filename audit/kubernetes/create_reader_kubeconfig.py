#!/usr/bin/env python3
"""Mint a short-lived kubeconfig for the homelab inventory service account."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from collect import (
    TOKEN_DURATION,
    TOKEN_NAMESPACE,
    TOKEN_SERVICE_ACCOUNT,
    ConfigurationError,
    _kubectl_prefix,
    _run_bounded,
    _write_private,
    minimal_kubeconfig,
    prepare_output,
)


def _admin_view(kubectl: str, admin_kubeconfig: Path, context: str | None) -> dict[str, Any]:
    command = _kubectl_prefix(kubectl, admin_kubeconfig, context)
    result = _run_bounded(command + ["config", "view", "--minify", "--flatten", "-o", "json"])
    if result.returncode:
        raise ConfigurationError("kubectl could not read the selected cluster connection settings")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ConfigurationError("kubectl returned invalid connection metadata") from None


def create_reader_kubeconfig(admin_kubeconfig: Path, output: Path, *,
                             context: str | None = None,
                             kubectl: str = "kubectl") -> Path:
    admin_config = admin_kubeconfig.expanduser().resolve()
    if not admin_config.is_file():
        raise ConfigurationError("admin kubeconfig path is not a file")
    if admin_config.stat().st_mode & 0o077:
        raise ConfigurationError("admin kubeconfig must be private (no group/other access)")
    destination = prepare_output(output)
    view = _admin_view(kubectl, admin_config, context)
    prefix = _kubectl_prefix(kubectl, admin_config, context)
    result = _run_bounded(prefix + ["create", "token", TOKEN_SERVICE_ACCOUNT,
                                    "--namespace", TOKEN_NAMESPACE,
                                    "--duration", TOKEN_DURATION])
    if result.returncode:
        raise ConfigurationError("could not issue a short-lived inventory token")
    token = result.stdout.strip()
    if not token or "\n" in token:
        raise ConfigurationError("TokenRequest returned no usable token")
    config = minimal_kubeconfig(view, token)
    del token
    _write_private(destination, json.dumps(config, separators=(",", ":")))
    del config
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-kubeconfig", required=True, type=Path,
                        help="private owner-managed kubeconfig used to mint the reader token")
    parser.add_argument("--context", help="context to use from the admin kubeconfig")
    parser.add_argument("--output", required=True, type=Path,
                        help="new mode-0600 kubeconfig path outside the repository")
    parser.add_argument("--kubectl", default="kubectl", help="kubectl executable")
    args = parser.parse_args()
    try:
        path = create_reader_kubeconfig(args.admin_kubeconfig, args.output,
                                        context=args.context, kubectl=args.kubectl)
    except ConfigurationError as exc:
        print("reader kubeconfig creation failed: " + str(exc), file=sys.stderr)
        return 2
    except OSError:
        print("reader kubeconfig creation failed: local file operation was unavailable", file=sys.stderr)
        return 2
    print(f"reader kubeconfig created at {path}; requested token lifetime={TOKEN_DURATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
