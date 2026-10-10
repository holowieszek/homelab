import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

collector = load("collector", "audit/collect.py")

def load_drift():
    return load("drift", "audit/drift.py")

forced = load("forced_collector", "audit/remote/forced-collector.py")
drift = load_drift()

class AuditTests(unittest.TestCase):
    def test_bounded_runner_terminates_on_output_limit(self):
        command = [sys.executable, "-c", "import sys; sys.stdout.write('x' * 4096)"]
        with self.assertRaises(collector.OutputLimitExceeded):
            collector._run_bounded(command, os.environ.copy(), timeout=5, max_bytes=64)

    def test_bounded_runner_terminates_on_timeout(self):
        command = [sys.executable, "-c", "import time; time.sleep(2)"]
        with self.assertRaises(subprocess.TimeoutExpired):
            collector._run_bounded(command, os.environ.copy(), timeout=0.1, max_bytes=64)

    def test_forced_collector_enforces_output_limit(self):
        command = [sys.executable, "-c", "import sys; sys.stdout.write('x' * 4096)"]
        with self.assertRaises(forced.OutputLimitExceeded):
            forced.run_bounded(command, os.environ.copy(), timeout=5, max_bytes=64)

    def test_collect_uses_allowlisted_category_and_sanitizes_fields(self):
        fake = [SimpleNamespace(returncode=0, stdout="osqueryi version 5.x", stderr=""),
                SimpleNamespace(returncode=0, stdout='[{"platform":"ubuntu","password":"nope","serial":"nope"}]', stderr="")]
        with patch.object(collector, "_run_bounded", side_effect=fake) as run:
            result = collector.collect("os", "fixture-host", "worker", "fixture-sha")
        self.assertEqual(result["collection_status"], "OK")
        self.assertEqual(result["observed_facts"], [{"platform": "ubuntu"}])
        self.assertEqual(run.call_args_list[1].args[0][2], collector.json.loads(collector.PACK.read_text())["queries"]["os"])

    def test_schema_or_permission_errors_are_unverified(self):
        fake = [SimpleNamespace(returncode=0, stdout="osqueryi version 5.x", stderr=""),
                SimpleNamespace(returncode=0, stdout="[]", stderr="Error: no such table: system_info")]
        with patch.object(collector, "_run_bounded", side_effect=fake):
            result = collector.collect("system", "fixture-host", "worker", "fixture-sha")
        self.assertEqual(result["collection_status"], "UNVERIFIED")
        self.assertTrue(result["errors"])

    def test_ssh_transport_is_batch_strict_and_allowlisted(self):
        fake = [SimpleNamespace(returncode=0, stdout="osqueryi version 5.x", stderr=""),
                SimpleNamespace(returncode=0, stdout='[{"platform":"ubuntu"}]', stderr="")]
        with patch.object(collector, "_run_bounded", side_effect=fake) as run:
            result = collector.collect("os", "test-host", "worker", "fixture-sha", transport="ssh")
        self.assertEqual(result["collection_status"], "OK")
        args, kwargs = run.call_args_list[1].args[0], run.call_args_list[1].kwargs
        self.assertEqual(args[:2], ["ssh", "-T"])
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertEqual(args[-2], "test-host")
        self.assertEqual(args[-1], "homelab-audit os")
        self.assertNotIn("GITHUB_PAT", kwargs["env"])

    def test_forced_command_parser_allows_categories_not_sql(self):
        self.assertEqual(forced.requested_action("homelab-audit os"), "os")
        with self.assertRaises(ValueError):
            forced.requested_action("osqueryi --json SELECT * FROM users")
        with self.assertRaises(ValueError):
            forced.requested_action("homelab-audit missing-category")

    def test_ssh_transport_uses_explicit_config_when_requested(self):
        fake = [SimpleNamespace(returncode=0, stdout="osqueryi version 5.x", stderr=""),
                SimpleNamespace(returncode=0, stdout='[{"platform":"ubuntu"}]', stderr="")]
        with patch.object(collector, "_run_bounded", side_effect=fake) as run:
            result = collector.collect("os", "test-host", "worker", "fixture-sha",
                                       transport="ssh", ssh_config="/private/ssh_config")
        self.assertEqual(result["collection_status"], "OK")
        args = run.call_args_list[1].args[0]
        self.assertEqual(args[args.index("-F") + 1], "/private/ssh_config")

    def test_invalid_ssh_alias_is_rejected_before_execution(self):
        with patch.object(collector, "_run_bounded") as run:
            with self.assertRaises(ValueError):
                collector.collect("os", "-oProxyCommand=bad", "worker", "fixture-sha", transport="ssh")
        run.assert_not_called()

    def test_missing_collector_is_unverified(self):
        with patch.object(collector, "_run_bounded", side_effect=FileNotFoundError):
            result = collector.collect("os", "fixture-host", "worker", "fixture-sha")
        self.assertEqual(result["collection_status"], "UNVERIFIED")
        self.assertEqual(result["observed_facts"], [])

    def test_schema_fixture_has_required_fields_and_allowed_status(self):
        schema = collector.json.loads((ROOT / "audit/schema/snapshot.schema.json").read_text())
        fixture = collector.json.loads((ROOT / "audit/fixtures/example-snapshot.json").read_text())
        self.assertTrue(set(schema["required"]) <= set(fixture))
        self.assertIn(fixture["collection_status"], schema["properties"]["collection_status"]["enum"])
        self.assertIsInstance(fixture["observed_facts"], list)

    def test_allowlisted_queries_are_explicit_selects(self):
        queries = collector.json.loads(collector.PACK.read_text())["queries"]
        self.assertTrue(queries)
        for sql in queries.values():
            self.assertTrue(sql.lstrip().upper().startswith("SELECT "))
            self.assertNotIn("SELECT *", sql.upper())
            self.assertNotIn(";", sql)

    def test_arbitrary_sql_category_is_rejected(self):
        with self.assertRaises(ValueError):
            collector.collect("SELECT * FROM users", "fixture-host", "worker", "fixture-sha")

class DriftTests(unittest.TestCase):
    def test_comparison_statuses_and_deterministic_order(self):
        desired = {"os": {"platform": "ubuntu", "version": "24.04"}, "pkg": {"name": "ansible"}, "missing": {"x": 1}}
        observed = {"os": {"collection_status": "OK", "observed_facts": [{"platform": "ubuntu", "version": "22.04", "extra": 1}]},
                    "pkg": {"collection_status": "UNVERIFIED", "observed_facts": []},
                    "runtime": {"collection_status": "OK", "observed_facts": [{"x": 1}]}}
        got = drift.compare(desired, observed)
        statuses = {row["status"] for row in got}
        self.assertTrue({"MATCH", "DRIFT", "UNVERIFIED", "REPO_ONLY", "RUNTIME_ONLY"} <= statuses)
        self.assertEqual(got, sorted(got, key=lambda x: (x["category"], x["key"])))

    def test_missing_observed_field_is_unverified(self):
        got = drift.compare({"os": {"version": "24.04"}}, {"os": {"collection_status": "OK", "observed_facts": [{"platform": "ubuntu"}]}})
        version_row = next(row for row in got if row["key"] == "version")
        self.assertEqual(version_row["status"], "UNVERIFIED")

    def test_approved_exception_relabels_only_a_drift(self):
        desired = {"os": {"version": "24.04"}}
        observed = {"os": {"collection_status": "OK", "observed_facts": [{"version": "22.04"}]}}
        rows = drift.compare(desired, observed, {"os.version": "approved maintenance window"})
        self.assertEqual(rows[0]["status"], "APPROVED_EXCEPTION")
        self.assertEqual(rows[0]["exception"], "approved maintenance window")

class AnsibleSafetyTests(unittest.TestCase):
    def test_audit_bootstrap_is_scoped_and_never_generates_controller_keys(self):
        playbook = (ROOT / "bare/audit-bootstrap.yml").read_text()
        self.assertIn("ansible_play_hosts_all | length == 1", playbook)
        self.assertIn("audit_bootstrap_authorized | bool", playbook)
        self.assertIn('audit_key_files.results[0].stat.mode == "0600"', playbook)
        self.assertNotIn("ssh-keygen", playbook)

    def test_reboot_single_host_gate_runs_before_host_tasks(self):
        playbook = (ROOT / "bare/reboot.yml").read_text()
        pre_tasks = playbook.split("  tasks:", 1)[0]
        self.assertIn("ansible_play_hosts_all | length == 1", pre_tasks)
        self.assertIn("reboot_authorized | default(false) | bool", pre_tasks)

if __name__ == "__main__":
    unittest.main()
