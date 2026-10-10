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

`audit/osquery/queries/approved.json` is the allowlist; `audit/collect.py --category CATEGORY --host-alias ALIAS --host-role ROLE --output /private/path/snapshot.json [--transport local|ssh] [--ssh-config /private/ssh_config] [--commit SHA]` accepts a category ID, never arbitrary SQL. It invokes `osqueryi --json`, applies a timeout/output cap, strips disallowed field names, and reports collection errors as `UNVERIFIED`. The CLI refuses an output destination inside the repository, creates a new file with mode `0600`, and prints only a status/path summary. The runner executes locally by default and supports opt-in `--transport ssh` using the supplied SSH alias, batch mode, strict host-key checking, and no privilege escalation. The SSH process receives only a minimal environment plus `SSH_AUTH_SOCK`; query arguments are built from the allowlist. The SSH client does not send SQL. `bare/audit-bootstrap.yml` automates osquery installation, forced collector deployment, approved query pack sync, creation of the restricted audit user, validation of an operator-managed controller key pair, and restricted `authorized_keys` setup (`restrict,command=...`). The wrapper accepts only `homelab-audit <approved-category>` (or `version`), invokes osquery without privilege escalation, and refuses arbitrary commands. For a local staging VM, use its external inventory and explicitly supplied audit key, for example: `make -C bare audit-bootstrap INVENTORY="$HOME/.config/homelab-staging/inventory.yml" HOSTS=lab-vm APPROVED=yes AUDIT_KEY="$HOME/.ssh/homelab-audit-staging"`. The playbook rejects multiple selected hosts before contact. Without this server-side forced-command boundary, do not enable `--transport ssh`. Raw results belong in an operator-controlled private path, never Git. Schema and clearly synthetic fixture: `audit/schema/snapshot.schema.json`, `audit/fixtures/example-snapshot.json`.

The per-host `preflight` policy entries below are review checklists, not implemented service probes. This release does not query Kubernetes readiness, Longhorn health, DNS availability, or backup systems, and does not perform cordon/drain/uncordon.

Queries rely on osquery Linux tables (`os_version`, `system_info`, `cpu_info`, `uptime`, `deb_packages`, `systemd_units`, `block_devices`, `kernel_info`, `system_controls`). The `hardware` category combines `system_info` with aggregated CPU clock fields from `cpu_info` (model in `cpu_brand`, core counts, `physical_memory_gib`, vendor/board strings, max/current clock in MHz). Legacy `system` remains a smaller subset for drift fixtures. Validate table/column availability against the exact deployed osquery build before use; unsupported columns/tables become `UNVERIFIED`. `bare/audit-bootstrap.yml` installs osquery from the upstream APT repository on Debian-family hosts. Installation is pinned to `5.23.1-1.linux` and guarded to Ansible architecture `x86_64` / APT `amd64`; Raspberry Pi ARM architectures are deliberately rejected until a trusted upstream `.deb` is verified. Do not use third-party binaries. See [official osquery table documentation](https://osquery.io/schema/).

### Operator run order

1. Prepare a separate operator-managed audit key pair, then bootstrap exactly one reviewed host. The playbook requires a private-key file with mode `0600`, its adjacent `.pub` file, an explicit host limit, and authorization; it never generates a private key.

```sh
ssh-keygen -t ed25519 -f "$HOME/.ssh/homelab-audit" -C homelab-audit
make -C bare audit-bootstrap INVENTORY=inventories/prod.yml HOSTS=__ONE_APPROVED_HOST__ APPROVED=yes AUDIT_KEY="$HOME/.ssh/homelab-audit"
```

2. Collect all approved categories for one host alias:

```sh
OUT_DIR=~/homelab-audit/run-$(date +%F-%H%M%S)/bare1-audit
make -C bare osquery-audit-all ALIAS=bare1-audit ROLE=worker TRANSPORT=ssh SSH_CONFIG=/private/ssh_config OUT_DIR="$OUT_DIR"
jq -s 'map({(.category): .}) | add' "$OUT_DIR"/*.json > "$OUT_DIR/observed.json"
```

3. Repeat collection for each production host alias:

```sh
OUT_ROOT=~/homelab-audit/prod-$(date +%F-%H%M%S)
mkdir -p -m 700 "$OUT_ROOT"
for spec in bare0-audit:master bare1-audit:worker bare2-audit:worker; do
  ALIAS="${spec%%:*}"
  ROLE="${spec##*:}"
  OUT_DIR="$OUT_ROOT/$ALIAS"
  make -C bare osquery-audit-all ALIAS="$ALIAS" ROLE="$ROLE" TRANSPORT=ssh OUT_DIR="$OUT_DIR"
  jq -s 'map({(.category): .}) | add' "$OUT_DIR"/*.json > "$OUT_DIR/observed.json"
done
```

4. Compare desired state for each host role:

```sh
make -C bare drift-report DESIRED=/private/desired/worker.json OBSERVED="$OUT_ROOT/bare1-audit/observed.json"
```

### Required SSH alias setup for remote audit transport

`collect.py` in SSH mode expects a valid OpenSSH host alias (`ALIAS`) resolving to `homelab-audit` on each host. Example controller-side config:

```sshconfig
Host bare0-audit
  HostName __REPLACE_WITH_PRIVATE_HOST_ADDRESS__
  User homelab-audit
  IdentityFile ~/.ssh/homelab-audit
  IdentitiesOnly yes
Host bare1-audit
  HostName __REPLACE_WITH_PRIVATE_HOST_ADDRESS__
  User homelab-audit
  IdentityFile ~/.ssh/homelab-audit
  IdentitiesOnly yes
Host bare2-audit
  HostName __REPLACE_WITH_PRIVATE_HOST_ADDRESS__
  User homelab-audit
  IdentityFile ~/.ssh/homelab-audit
  IdentitiesOnly yes
```

Use `ssh -T -o BatchMode=yes bare1-audit "homelab-audit version"` before collection to confirm alias resolution, key usage, and forced-command behavior.

### Troubleshooting notes

- `collection_status=UNVERIFIED` with `errors=["RuntimeError"]` usually means SSH transport failed or remote `osqueryi` returned an error; test the alias directly with `ssh -T`.
- `FileExistsError` from `collect.py` means the output file already exists. Results are intentionally write-once (`O_EXCL`); use a new output directory per run.
- `audit-bootstrap` uses explicit SSH connection arguments from `bare/Makefile` (`SSH_USER`, `SSH_KEY`; defaults `ubuntu` and `~/.ssh/test`) and requires a separate existing operator-managed controller key pair through `AUDIT_KEY` (default `~/.ssh/homelab-audit`).

### Staging VM with Multipass for runbook tests

The staging VM is disposable and its inventory and host variables must remain outside the repository. The repository ignores the legacy in-tree staging paths as a defense in depth; do not commit live VM addresses or generated audit results.

Prerequisites on the controller:

- Multipass installed and functional (`multipass version`).
- Hardware virtualization enabled in firmware (AMD SVM or Intel VT-x), with `/dev/kvm` available when using the QEMU driver.
- An operator-managed SSH key pair for the staging VM (default examples use `~/.ssh/test`).

Quick preflight checks:

```sh
multipass version
test -r "$HOME/.ssh/test.pub"
grep -Ewc 'vmx|svm' /proc/cpuinfo
ls -l /dev/kvm
```

Create a dedicated VM with the staging public key; keep the rendered cloud-init input local and never commit it.

```sh
multipass launch 24.04 --name lab-vm --cloud-init - <<EOF
users:
  - name: ubuntu
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - $(cat "$HOME/.ssh/test.pub")
package_update: true
packages:
  - openssh-server
  - python3
EOF
multipass info lab-vm
```

Generate a local inventory from Multipass state under the user's config directory, not in Git:

```sh
STAGING_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/homelab-staging"
install -d -m 700 "$STAGING_DIR/host_vars"
VM_IP="$(multipass info lab-vm --format json | jq -r '.info["lab-vm"].ipv4[0]')"
cat > "$STAGING_DIR/inventory.yml" <<EOF
bare:
  hosts:
    lab-vm:
      ansible_host: $VM_IP
EOF
cat > "$STAGING_DIR/host_vars/lab-vm.yml" <<'EOF'
os_maintenance:
  enabled: true
  approved: true
  reboot_allowed: false
os_maintenance_packages: [curl, openssh-server]
os_baseline_packages: [jq]
EOF
chmod 600 "$STAGING_DIR/inventory.yml" "$STAGING_DIR/host_vars/lab-vm.yml"
```

Run staging checks with an explicit inventory, host, and key. `patch-apply` changes only the package allowlist in this local staging profile and still requires a separate operator approval token; do not confuse it with production authorization.

```sh
make -C bare configure-check INVENTORY="$STAGING_DIR/inventory.yml" HOSTS=lab-vm SSH_USER=ubuntu SSH_KEY="$HOME/.ssh/test"
make -C bare patch-preview INVENTORY="$STAGING_DIR/inventory.yml" HOSTS=lab-vm SSH_USER=ubuntu SSH_KEY="$HOME/.ssh/test"
make -C bare patch-apply INVENTORY="$STAGING_DIR/inventory.yml" HOSTS=lab-vm APPROVED=yes SSH_USER=ubuntu SSH_KEY="$HOME/.ssh/test"
```

For an isolated audit-bootstrap test, create a separate operator-managed audit key pair first and pass its path explicitly; the playbook does not generate private keys. After bootstrap, write an SSH config fragment outside the repository, then make the first version probe to accept and pin the staging host key before collection:

```sh
ssh-keygen -t ed25519 -f "$HOME/.ssh/homelab-audit-staging" -C homelab-staging-audit
VM_IP="$(multipass info lab-vm --format json | jq -r '.info["lab-vm"].ipv4[0]')"
cat > "$STAGING_DIR/ssh_config" <<EOF
Host lab-vm-audit
  HostName $VM_IP
  User homelab-audit
  IdentityFile $HOME/.ssh/homelab-audit-staging
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  UserKnownHostsFile $STAGING_DIR/known_hosts
  BatchMode yes
EOF
chmod 600 "$STAGING_DIR/ssh_config"
ssh -T -F "$STAGING_DIR/ssh_config" lab-vm-audit "homelab-audit version"
OUT_DIR="$HOME/homelab-audit/staging-$(date +%F-%H%M%S)/lab-vm-audit"
make -C bare osquery-audit-all ALIAS=lab-vm-audit ROLE=staging TRANSPORT=ssh SSH_CONFIG="$STAGING_DIR/ssh_config" OUT_DIR="$OUT_DIR"
jq -s 'map({(.category): .}) | add' "$OUT_DIR"/*.json > "$OUT_DIR/observed.json"
```

Do not run this bootstrap command against production as part of staging validation.

Stop and permanently remove only this VM when finished:

```sh
multipass delete --purge lab-vm
rm -rf "$STAGING_DIR"
```

Do not use a global `multipass purge`; it can remove other previously deleted instances. Keep the staging VM if you still need it for further tests.

## Drift and status semantics

`audit/drift.py DESIRED.json OBSERVED.json [--exceptions EXCEPTIONS.json]` compares explicit fields only and produces sorted JSON. Unpinned/absent facts are not inferred as version drift. Statuses: MATCH (equal), DRIFT (observed value differs), REPO_ONLY (desired category absent), RUNTIME_ONLY (observed category/field absent from desired), UNVERIFIED (collection failed or field absent), APPROVED_EXCEPTION (documented exception overrides a drift). This initial implementation compares desired JSON to collected JSON; documented-state reconciliation is a human review, not automated inference. Results use synthetic fixtures in tests only.

## Safe operations and recovery

Existing provisioning commands remain unchanged, and top-level `make` remains `bare system`. New maintenance playbooks are never invoked by those targets. Review diff and policy, confirm host selection, backups, service window, trusted runner and separate maintenance credentials before any production operation. Audit and maintenance identities must be separate; no identity/account is created here and no credential is stored in Git. Never put audit snapshots in public repository.

APT changes may not be reversible; recovery requires verified independent backups, known-good images/reinstallation path, and tested application/data restore procedures. For K3s, validate etcd/datastore and Longhorn recovery plans separately. This PR contains no production verification and no deployment.
