# Operations guide

This guide documents the commands represented by the repository. Run them only from a trusted operator workstation with the intended inventory, cloud account, and cluster credentials. Commands that apply infrastructure or cluster changes are explicitly marked.

## Prerequisites

Install and configure the versions/modules needed for the relevant layer:

- Git and GNU Make.
- Ansible with `kubernetes.core` collection and Python Kubernetes dependencies for playbooks.
- SSH access and the private key referenced by `bare/group_vars/all.yml` (currently `~/.ssh/test`); the matching public key must be readable.
- Docker Compose for the PXE helper service.
- OpenTofu, AWS credentials/permissions, and populated backend/variable files for `external/`.
- A functioning K3s kubeconfig at `bare/k3s.yaml`; Helm and chart repository network access for rendering/installing charts.
- Bootstrap environment variables `HOMELAB_ESO_ACCESS_KEY` and `HOMELAB_ESO_SECRET_ACCESS_KEY` for External Secrets.

Do not copy production credentials into tracked files. Example configuration files are placeholders; create local production files from them and keep them untracked.

## Deployment order

### 1. Prepare and provision bare metal

Review the host addresses, MAC addresses, control-plane endpoint, SSH user/key, ISO URL/checksum and PXE server endpoint in `bare/` first. These values are environment-specific.

- `make -C bare boot` runs `ansible-playbook --inventory inventories/prod.yml boot.yml`.
- `make -C bare cluster` runs the K3s cluster playbook followed by master dependency setup.
- `make -C bare` runs both targets in sequence.

These commands contact physical hosts and alter their state. Inspect playbooks and Ansible diffs/plan before running against a live system.

### 2. Provision AWS resources (separate, state-changing)

Create local `external/config/backend/prod.tfbackend` and `external/config/environment/prod.tfvars` from the tracked examples. Fill them from the intended AWS account and remote state configuration, not from this guide. Then review the OpenTofu plan before applying.

`make -C external` runs `tofu init`, `tofu plan -var-file=config/environment/prod.tfvars -out=tfplan`, and `tofu apply tfplan`. The final command changes AWS resources. Do not run it unattended or against an unverified account. `external` is omitted from the top-level default target intentionally.

### 3. Bootstrap the cluster

Ensure `bare/k3s.yaml` exists and points to the intended cluster. `make -C system bootstrap` runs `ansible-playbook bootstrap.yml`. The playbook creates namespaces, writes an AWS Kubernetes Secret, installs External Secrets, waits a fixed 180 seconds, then installs Argo CD. It requires the two `HOMELAB_ESO_*` environment variables. Bootstrap writes a rendered secret manifest under `system/files/`; the path is ignored by Git but contains sensitive values and should be securely removed after use.

### 4. GitOps operations

After Argo CD is healthy and has access to the configured repositories, its ApplicationSets discover chart directories described in `docs/architecture.md`. Merge to the configured `main` branch may trigger automated reconciliation, pruning and self-healing. Check application health and diff in Argo CD before/after any production change. The private repository needs its own valid repository credentials.

## Safe validation (no apply/deploy)

Run only the checks for tools installed in the current environment:

```sh
# Ansible syntax checks; does not execute plays against hosts
cd bare
ansible-playbook --syntax-check --inventory inventories/prod.yml boot.yml
ansible-playbook --syntax-check --inventory inventories/prod.yml cluster.yml

# OpenTofu static validation (init may access backend/provider registries;
# do not use -upgrade or apply for this validation)
cd ../external
tofu fmt -check -recursive
tofu init -backend=false
tofu validate

# Helm dependency build/render each chart locally; this fetches dependencies,
# but does not install them into Kubernetes.
cd ..
for chart in apps/* databases/* platform/* system/*; do
  [ -f "$chart/Chart.yaml" ] || continue
  helm dependency build "$chart"
  helm template "$(basename "$chart")" "$chart"
done
```

The Helm loop writes dependency artifacts (for example `charts/`) into chart directories; run it in a disposable worktree or clean generated artifacts afterward. The repository does not currently define CI, so successful local checks are not proof of live deployment health.

## Recovery and safety notes

- Longhorn has `reclaimPolicy: Retain` and an S3 backup target configured in `system/longhorn/Chart.yaml`; validate backup credentials and restoration procedures independently. A configured backup target alone does not prove backups are succeeding.
- Database clusters are separately declared under `databases/`; coordinate schema/application rollouts and verify backups before storage or PVC changes.
- Argo CD automated pruning can delete resources removed from Git. Review diffs for deletions and data-bearing PVC changes carefully.
- Never paste secret values, kubeconfigs, state files, plan files, or rendered Secret manifests into issues, logs, or pull requests.
- For changes involving credentials, rotate affected credentials in the provider and deployed Secret store; removing a value from Git alone does not revoke it.
