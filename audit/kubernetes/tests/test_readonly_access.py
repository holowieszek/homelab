import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "audit/kubernetes/readonly-access.json"
sys.path.insert(0, str(MANIFEST_PATH.parent))
import collect
import run_audit


class LeastPrivilegeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST_PATH.read_text())
        self.objects = {(item["kind"], item.get("metadata", {}).get("name")): item
                        for item in self.manifest}
        self.role = self.objects[("ClusterRole", "homelab-cluster-inventory")]

    def test_every_collected_resource_is_authorized_and_no_uncollected_resource_is(self):
        declared = {}
        for rule in self.role["rules"]:
            for api_resource in rule["resources"]:
                declared[(tuple(rule["apiGroups"]), api_resource)] = set(rule["verbs"])
        expected = set()
        for resource in collect.RESOURCES:
            group = resource.path.split("/")[2] if resource.path.startswith("/apis/") else ""
            name = resource.path.rstrip("/").split("/")[-1]
            expected.add(((group,), name))
            with self.subTest(resource=resource.name):
                self.assertEqual(declared.get(((group,), name)), {"get", "list"})
        self.assertEqual(set(declared), expected)

    def test_serviceaccount_is_bound_only_to_readonly_clusterrole(self):
        bindings = [item for item in self.manifest if item["kind"] == "ClusterRoleBinding"]
        self.assertEqual(len(bindings), 1)
        binding = bindings[0]
        self.assertEqual(binding["roleRef"]["name"], "homelab-cluster-inventory")
        self.assertEqual(binding["subjects"], [{"kind": "ServiceAccount", "name": "cluster-inventory", "namespace": "homelab-audit"}])
        account = self.objects[("ServiceAccount", "cluster-inventory")]
        self.assertFalse(account["automountServiceAccountToken"])

    def test_manifest_validation_fails_closed_on_secret_or_wildcard_grants(self):
        for bad in ("secrets", "*"):
            mutated = json.loads(json.dumps(self.manifest))
            role = next(obj for obj in mutated if obj["kind"] == "ClusterRole")
            role["rules"][0]["resources"].append(bad)
            with self.subTest(resource=bad), self.assertRaises(run_audit.AuditSetupError):
                run_audit.validate_manifest(mutated)

    def test_admin_identity_is_only_used_to_mint_the_reader_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "private"
            output_dir.mkdir(mode=0o700)
            admin = root / "admin.kubeconfig"
            admin.write_text("placeholder")
            admin.chmod(0o600)
            output = output_dir / "snapshot.json"
            response = {"collection_status": "OK", "resources": []}
            with patch.object(run_audit, "MANIFEST", MANIFEST_PATH), \
                 patch.object(run_audit, "create_reader_kubeconfig") as create, \
                 patch.object(run_audit, "collect_snapshot") as api_collect:
                create.side_effect = lambda _admin, path, **_kwargs: path
                api_collect.return_value = response
                result = run_audit.collect_with_admin(admin, output, context="prod",
                                                     kubectl="kubectl", timeout=10)
            self.assertEqual(result, response)
            create.assert_called_once_with(admin, ANY,
                                           context="prod", kubectl="kubectl")
            reader = Path(api_collect.call_args.args[0])
            self.assertEqual(api_collect.call_args.kwargs["timeout"], 10)
            self.assertFalse(reader.exists())
            self.assertFalse(output.exists())

    def test_snapshot_output_refuses_repo_paths_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            with self.assertRaises(collect.ConfigurationError):
                collect.prepare_output(repo / "snapshot.json", repo)
            destination = root / "private" / "snapshot.json"
            prepared = collect.prepare_output(destination, repo)
            self.assertEqual(stat.S_IMODE(prepared.parent.stat().st_mode), 0o700)
            prepared.write_text("existing")
            with self.assertRaises(collect.ConfigurationError):
                collect.prepare_output(prepared, repo)


if __name__ == "__main__":
    unittest.main()
