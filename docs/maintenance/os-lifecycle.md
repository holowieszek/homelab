# OS lifecycle and maintenance

## Boundaries and inventory

Git declares intended configuration; Ansible handles provisioning and separately authorized maintenance; the local `osqueryi` collector and drift tool are read-only analysis utilities. No playbook in this change was run against hosts. Current tracked inventory is `bare/inventories/prod.yml`: `bare0` is in `masters`, and `bare1`/`bare2` are in `workers`. No Raspberry Pi, DNS host, or OPNsense appears there; profiles are prospective only. Existing `boot.yml`/`cluster.yml` and `make -C bare boot|cluster` bootstrap paths are retained. Existing `wake`, PXE, K3s, and dependencies roles may have provisioning side effects; they are not maintenance roles.

## Maintenance workflow

`configure.yml`, `patch-os.yml`, and `reboot.yml` are separate from bootstrapping. Configure and patch require an explicit `--limit` and authorization variables; patching is additionally restricted to one selected host per invocation. Policies default disabled; `patch-os.yml` only updates explicitly listed `os_maintenance_packages`, with the list empty by default. It uses Debian package state `latest` for those package names only, excludes kernel-named packages, and does not call dist-upgrade, change K3s, or reboot. It reports before/after selected package versions and checks `/var/run/reboot-required`. Use `make -C bare patch-apply HOSTS=bare1 APPROVED=yes` only after an operator has explicitly enabled/reviewed the inventory policy and package allowlist. Updates are not automatic.

Example reviewed operator invocations (do not run until an approved trusted runner and credentials exist):

```sh
cd bare
ansible-playbook -i inventories/prod.yml patch-os.yml --limit bare1 \
  -e maintenance_authorized=true
ansible-playbook -i inventories/prod.yml reboot.yml --limit HOST \
  -e maintenance_authorized=true -e reboot_authorized=true
```

The checked-in worker policy is intentionally not enabled/approved. Cluster hosts are blocked from generic reboot playbook; cordon/drain/uncordon and workload readiness require a separately reviewed runbook and live cluster health checks. Control-plane is single-inventory-host and no HA assumption is made. No automated Kubernetes maintenance behavior is implemented.

## Lifecycle policies

YAML profiles live in `audit/policies/host-maintenance.yml`: control-plane updates require explicit approval, backup review and a service window; workers are one-at-a-time with cluster/Longhorn/workload preflight and manual drain procedure; prospective Pi/DNS has DNS probes and no reboot; OPNsense is explicitly outside Linux APT/reboot automation and must use vendor-supported update methods. All changes remain opt-in. Before kernel changes, risky package updates, or reboot, operator must verify recoverable backups and a maintenance window; no rollback is implied by APT.

## osquery audit and output

`audit/osquery/queries/approved.json` is the allowlist; `audit/collect.py --category CATEGORY --host-alias ALIAS --host-role ROLE --output /private/path/snapshot.json [--transport local|ssh] [--commit SHA]` accepts a category ID, never arbitrary SQL. It invokes `osqueryi --json`, applies a timeout/output cap, strips disallowed field names, and reports collection errors as `UNVERIFIED`. The CLI refuses an output destination inside the repository, creates a new file with mode `0600`, and prints only a status/path summary. The runner executes locally by default and supports opt-in `--transport ssh` using the supplied SSH alias, batch mode, strict host-key checking, and no privilege escalation. The SSH process receives only a minimal environment plus `SSH_AUTH_SOCK`; query arguments are built from the allowlist. The SSH client does not send SQL. Install `audit/remote/forced-collector.py` with its approved query pack under a root-owned, non-writable-by-audit-user path on each audit target, then configure the separately created audit identity with an SSH `ForceCommand` to that script, no TTY, and no forwarding. The wrapper accepts only `homelab-audit <approved-category>` (or `version`), invokes osquery without privilege escalation, and refuses arbitrary commands. Do not create that identity or change sshd in this PR; those steps require separate operator authorization and version-specific review. Without this server-side forced-command boundary, do not enable `--transport ssh`. The collector itself has not been deployed or exercised on a remote host. Raw results belong in an operator-controlled private path, never Git. Schema and clearly synthetic fixture: `audit/schema/snapshot.schema.json`, `audit/fixtures/example-snapshot.json`.

The per-host `preflight` policy entries below are review checklists, not implemented service probes. This release does not query Kubernetes readiness, Longhorn health, DNS availability, or backup systems, and does not perform cordon/drain/uncordon.

Queries rely on osquery Linux tables (`os_version`, `system_info`, `uptime`, `deb_packages`, `systemd_units`, `block_devices`, `kernel_info`, `system_controls`). Validate table/column availability against the exact deployed osquery build before use; unsupported columns/tables become `UNVERIFIED`. Package installation is intentionally not automated. Raspberry Pi architecture package availability is not asserted. See [official osquery table documentation](https://osquery.io/schema/).

## Drift and status semantics

`audit/drift.py DESIRED.json OBSERVED.json [--exceptions EXCEPTIONS.json]` compares explicit fields only and produces sorted JSON. Unpinned/absent facts are not inferred as version drift. Statuses: MATCH (equal), DRIFT (observed value differs), REPO_ONLY (desired category absent), RUNTIME_ONLY (observed category/field absent from desired), UNVERIFIED (collection failed or field absent), APPROVED_EXCEPTION (documented exception overrides a drift). This initial implementation compares desired JSON to collected JSON; documented-state reconciliation is a human review, not automated inference. Results use synthetic fixtures in tests only.

## Safe operations and recovery

Existing provisioning commands remain unchanged, and top-level `make` remains `bare system`. New maintenance playbooks are never invoked by those targets. Review diff and policy, confirm host selection, backups, service window, trusted runner and separate maintenance credentials before any production operation. Audit and maintenance identities must be separate; no identity/account is created here and no credential is stored in Git. Never put audit snapshots in public repository.

APT changes may not be reversible; recovery requires verified independent backups, known-good images/reinstallation path, and tested application/data restore procedures. For K3s, validate etcd/datastore and Longhorn recovery plans separately. This PR contains no production verification and no deployment.
