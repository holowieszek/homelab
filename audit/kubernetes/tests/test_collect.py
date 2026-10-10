import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "audit/kubernetes/collect.py"
spec = importlib.util.spec_from_file_location("cluster_collect", MODULE_PATH)
assert spec is not None and spec.loader is not None
collector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = collector
spec.loader.exec_module(collector)
sys.path.insert(0, str(MODULE_PATH.parent))
import create_reader_kubeconfig as reader_config


class TableProjectionTests(unittest.TestCase):
    def test_parser_keeps_allowlisted_table_cells_and_never_row_objects(self):
        resource = collector.RESOURCES_BY_NAME["pods"]
        table = {
            "apiVersion": "meta.k8s.io/v1",
            "kind": "Table",
            "columnDefinitions": [
                {"name": "Name"}, {"name": "Namespace"}, {"name": "Ready"},
                {"name": "Status"}, {"name": "Restarts"}, {"name": "Age"},
                {"name": "Credential"},
            ],
            "rows": [{
                "cells": ["memo-abc", "notes", "1/1", "Running", 0, "3d", "TOPSECRET"],
            }],
        }
        result = collector.parse_table(table, resource)
        self.assertEqual(result["columns"], ["Name", "Namespace", "Ready", "Status", "Restarts", "Age"])
        self.assertEqual(result["items"], [{"Name": "memo-abc", "Namespace": "notes", "Ready": "1/1", "Status": "Running", "Restarts": 0, "Age": "3d"}])
        self.assertNotIn("TOPSECRET", json.dumps(result))

    def test_parser_rejects_full_object_response_without_fallback(self):
        resource = collector.RESOURCES_BY_NAME["pods"]
        with self.assertRaises(collector.UnsafeResponse):
            collector.parse_table({"apiVersion": "v1", "kind": "PodList", "items": []}, resource)

    def test_parser_rejects_table_rows_with_embedded_objects(self):
        resource = collector.RESOURCES_BY_NAME["pods"]
        payload = {"apiVersion": "meta.k8s.io/v1", "kind": "Table",
                   "columnDefinitions": [{"name": "Name"}],
                   "rows": [{"cells": ["pod"], "object": {"data": "secret"}}]}
        with self.assertRaises(collector.UnsafeResponse):
            collector.parse_table(payload, resource)

    def test_page_url_encodes_continue_token(self):
        url = collector.page_url("http://127.0.0.1:8000/api/v1/pods", "a+b/c==")
        self.assertIn("continue=a%2Bb%2Fc%3D%3D", url)
        self.assertIn("limit=200", url)

    def test_request_uses_table_only_accept_and_never_retries_as_full_json(self):
        resource = collector.RESOURCES_BY_NAME["pods"]

        class FakeOpener:
            requests = []

            def open(self, request, timeout):
                self.requests.append(request)
                body = json.dumps({
                    "apiVersion": "meta.k8s.io/v1", "kind": "Table",
                    "columnDefinitions": [{"name": "Name"}],
                    "rows": [{"cells": ["pod-a"]}],
                }).encode()
                return BytesIO(body)

        opener = FakeOpener()
        result = collector.request_table("http://127.0.0.1:8000", resource, opener)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(opener.requests[0].get_header("Accept"), collector.TABLE_ACCEPT)

        class NotAcceptable:
            calls = 0

            def open(self, request, timeout):
                self.calls += 1
                raise urllib.error.HTTPError(request.full_url, 406, "unsupported", Message(), None)

        blocked = NotAcceptable()
        result = collector.request_table("http://127.0.0.1:8000", resource, blocked)
        self.assertEqual(result["status"], "TABLE_UNSUPPORTED")
        self.assertEqual(blocked.calls, 1)


class CredentialAndProxyTests(unittest.TestCase):
    def test_minimal_kubeconfig_contains_only_server_ca_and_ephemeral_token(self):
        view = {
            "clusters": [{"name": "prod", "cluster": {
                "server": "https://127.0.0.1:6443",
                "certificate-authority-data": "Y2EtZGF0YQ==",
                "insecure-skip-tls-verify": False,
            }}],
            "contexts": [{"name": "prod", "context": {"cluster": "prod", "user": "admin"}}],
            "users": [{"name": "admin", "user": {"client-key-data": "PRIVATE-KEY", "token": "ADMIN-TOKEN"}}],
        }
        config = collector.minimal_kubeconfig(view, "SHORT-LIVED-TOKEN")
        encoded = json.dumps(config)
        self.assertEqual(config["clusters"][0]["cluster"], {
            "server": "https://127.0.0.1:6443", "certificate-authority-data": "Y2EtZGF0YQ=="})
        self.assertIn("SHORT-LIVED-TOKEN", encoded)
        self.assertNotIn("PRIVATE-KEY", encoded)
        self.assertNotIn("ADMIN-TOKEN", encoded)

    def test_kubeconfig_refuses_insecure_tls_or_missing_ca(self):
        for cluster in (
            {"server": "https://api", "insecure-skip-tls-verify": True},
            {"server": "https://api"},
        ):
            with self.subTest(cluster=cluster), self.assertRaises(collector.ConfigurationError):
                collector.minimal_kubeconfig({"clusters": [{"cluster": cluster}]}, "token")

    def test_reader_config_helper_writes_token_only_kubeconfig_private(self):
        view = {"clusters": [{"name": "prod", "cluster": {
            "server": "https://127.0.0.1:6443",
            "certificate-authority-data": "Y2EtZGF0YQ==",
        }}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            admin = Path(tmp) / "admin.kubeconfig"
            admin.write_text("not read by helper")
            admin.chmod(0o600)
            output = Path(tmp) / "private" / "reader.kubeconfig"
            with patch.object(reader_config, "_admin_view", return_value=view), \
                 patch.object(reader_config, "_run_bounded") as run:
                run.return_value = type("Completed", (), {"returncode": 0, "stdout": "SHORT-TOKEN\n"})()
                created = reader_config.create_reader_kubeconfig(admin, output)
            config = json.loads(created.read_text())
            self.assertEqual(stat.S_IMODE(created.stat().st_mode), 0o600)
            self.assertEqual(config["users"][0]["user"], {"token": "SHORT-TOKEN"})
            self.assertNotIn("admin", created.read_text())
            self.assertIn("--duration", run.call_args.args[0])

    def test_proxy_binds_loopback_and_rejects_mutating_methods(self):
        command = collector.proxy_command("kubectl", Path("/private/reader.kubeconfig"))
        self.assertIn("--address=127.0.0.1", command)
        self.assertIn("--port=0", command)
        self.assertIn("--reject-methods=^(POST|PUT|PATCH|DELETE|CONNECT)$", command)
        self.assertTrue(any("--accept-paths=" in arg for arg in command))
        self.assertFalse(any("--disable-filter" in arg for arg in command))
        accept_paths = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--accept-paths="))
        self.assertNotIn("/api/v1/secrets", accept_paths)
        self.assertNotIn("/api/v1/configmaps", accept_paths)

    def test_proxy_accepts_only_ephemeral_or_valid_fixed_local_port(self):
        self.assertIn("--port=0", collector.proxy_command("kubectl", Path("/private/reader")))
        self.assertIn("--port=12345", collector.proxy_command("kubectl", Path("/private/reader"), 12345))
        with self.assertRaises(collector.ConfigurationError):
            collector.proxy_command("kubectl", Path("/private/reader"), 65536)


class ReadOnlyPolicyTests(unittest.TestCase):
    def test_manifest_grants_only_get_list_and_no_secret_or_configmap_access(self):
        manifest = json.loads((ROOT / "audit/kubernetes/readonly-access.json").read_text())
        role = next(obj for obj in manifest if obj.get("kind") == "ClusterRole")
        for rule in role["rules"]:
            self.assertEqual(set(rule["verbs"]), {"get", "list"})
            self.assertNotIn("*", rule["resources"])
            self.assertFalse(any("/" in resource for resource in rule["resources"]))
            self.assertNotIn("secrets", rule["resources"])
            self.assertNotIn("configmaps", rule["resources"])
        sa = next(obj for obj in manifest if obj.get("kind") == "ServiceAccount")
        self.assertFalse(sa["automountServiceAccountToken"])

    def test_allowlist_has_no_secrets_configmaps_or_event_resources(self):
        all_resources = {r.name for r in collector.RESOURCES}
        self.assertTrue({"secrets", "configmaps", "events"}.isdisjoint(all_resources))
        self.assertGreaterEqual(len(all_resources), 20)


class OutputSafetyTests(unittest.TestCase):
    def test_output_must_be_outside_repository_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            with self.assertRaises(collector.ConfigurationError):
                collector.prepare_output(root / "audit.json", root)
            destination = Path(tmp) / "private" / "audit.json"
            prepared = collector.prepare_output(destination, root)
            self.assertEqual(prepared, destination.resolve())
            self.assertEqual(stat.S_IMODE(prepared.parent.stat().st_mode), 0o700)
            destination.write_text("existing")
            with self.assertRaises(collector.ConfigurationError):
                collector.prepare_output(destination, root)


if __name__ == "__main__":
    unittest.main()
