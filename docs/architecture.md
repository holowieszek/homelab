# Architecture and repository analysis

## Scope and method

This document describes the tracked configuration at reviewed revision `43add6737b6c6a9d9fa45e48a451aeae5b34812a`. It is a source-based architecture review, not a live-cluster audit: no cluster credentials or AWS state were queried. Values, resource names, IPs, hostnames, image tags and behavior below are transcribed from repository configuration; live availability and deployed versions may differ. For per-service dependencies, secret references, database declarations, and chart versions, see the [service and dependency catalog](service-catalog.md); for provisioning internals, see the [provisioning reference](provisioning-reference.md).

## System at a glance

The repository separates infrastructure into five operational layers:

1. **Bare metal (`bare/`)** — Ansible starts a local PXE service, wakes inventory machines, then provisions K3s and master-node dependencies. The production inventory declares one control-plane host and two workers on a private `192.168.88.0/24` network.
2. **Cloud resources (`external/`)** — OpenTofu configures AWS resources, with modules for private/public ECR, IAM users and OIDC identity, Route 53, S3, SSM Parameter Store and Secrets Manager. It is deliberately excluded from the root default target.
3. **Cluster bootstrap (`system/`)** — Ansible creates namespaces, places AWS access credentials in an `external-secrets` Kubernetes Secret, installs External Secrets, waits 180 seconds, then installs Argo CD.
4. **Cluster platform (`platform/` and `system/`)** — Helm charts define cert-manager, Longhorn, Prometheus/Grafana monitoring, CloudNativePG and EMQX.
5. **Applications and databases (`apps/`, `databases/`)** — Argo CD ApplicationSets discover chart directories and database resources from the repositories.

## GitOps and reconciliation

`system/argocd/values.yaml` configures two repositories: this public repository and `holowieszek/homelab-private`. The public ApplicationSet scans `apps/*`, `system/*`, `platform/*` and `databases/*`; the private ApplicationSet scans `apps/*` in the private repository. The ApplicationSet destination namespace defaults to the directory basename, with automated sync, pruning, self-heal, retries, namespace creation and server-side apply. Explicit `metadata.namespace` in manifests can target a different namespace: for example, `databases/linkding-db/cluster.yaml` targets `linkding`, and `system/coredns/upstream-dns.yaml` targets `kube-system`. The configured policy permits automatic reconciliation of changes to `main`; this does not establish that an Argo CD instance is running or has reconciled them.

The charts use upstream Helm dependencies declared in each `Chart.yaml`; the repository ignores `Chart.lock` and packaged charts. Chart rendering depends on fetching these external dependencies.

## Workload inventory

### Apps

| Directory | Role evident in configuration |
|---|---|
| `esphome` | ESPHome dashboard, ingress/TLS, Longhorn-backed config volume |
| `home-assistant` | Home Assistant, HACS init container, ingress/TLS, persistent config |
| `homepage` | Home dashboard, service links and Kubernetes/monitoring widgets |
| `linkding` | Bookmark manager with PostgreSQL credentials from External Secrets |
| `litellm` | LiteLLM proxy with PostgreSQL and secret-backed keys/config |
| `memos` | Notes service with persistent data |
| `meshcore-telemetry` | MQTT telemetry processor writing to PostgreSQL; no Service enabled |
| `opnsense-backup` | Kubernetes CronJob/RBAC manifests and ECR-token helper resources |
| `speedtest` | Scheduled Speedtest Tracker backed by PostgreSQL |
| `zigbee2mqtt` | Zigbee2MQTT using network-attached coordinator and EMQX |

### Databases and platform

CloudNativePG clusters are declared for Home Assistant, Linkding, LiteLLM, MeshCore Telemetry and Speedtest. `databases/pgadmin` defines the database UI. Platform charts install CloudNativePG, EMQX and Grafana; system charts bootstrap Argo CD and External Secrets and manage cert-manager, Longhorn and kube-prometheus-stack.

### Cluster DNS

[`system/coredns/upstream-dns.yaml`](../system/coredns/upstream-dns.yaml) declares the `coredns-custom` ConfigMap in `kube-system`, with a `custom.server` block forwarding the configured internal DNS zone to a private upstream on port `53`. This is a raw manifest discovered under `system/coredns`, not a Helm chart or a bootstrap-playbook task. The file does not demonstrate that the deployed CoreDNS configuration imports the custom block or that the upstream is reachable; the concrete zone and upstream address are intentionally not duplicated here.

### External modules

`external/` contains AWS provider and backend configuration, root resources and versioned modules for ECR, IAM, Parameter Store, Route 53, S3 and Secrets Manager. The production backend and variable files are intentionally absent from version control; `.example` files contain placeholders. The IAM user module creates users and policy attachments, not access keys; the Secrets Manager module creates containers, not secret values. Operators must provision required values and bootstrap credentials separately; see the [provisioning reference](provisioning-reference.md#operator-supplied-aws-values-and-bootstrap-environment).

## Configuration and trust boundaries

- AWS access keys are injected into bootstrap from `HOMELAB_ESO_ACCESS_KEY` and `HOMELAB_ESO_SECRET_ACCESS_KEY`, then stored in `awssm-secret` in the cluster. External Secrets uses that credential to access Secrets Manager in `eu-central-1`.
- Workload credentials are generally referenced through Kubernetes Secret names/keys; application values avoid embedding most runtime secrets directly.
- The public Git repository is an Argo CD source of truth and controls resources with automated prune/self-heal. Protect its write access and review changes as production changes.
- The inventory and chart values contain private-network IPs, MAC addresses, internal hostnames, and infrastructure endpoints. Assess whether their disclosure is acceptable for this repository's public visibility.

## Findings and follow-up priorities

These are source-review observations, not proof of a current exploit or live misconfiguration.

1. **Mitigated in the follow-up remediation.** Bootstrap now validates that both AWS credential environment variables are set and constructs the Kubernetes Secret directly from those values, without writing a plaintext manifest to disk. The Secret-creation task uses Ansible `no_log` to suppress credential-bearing task output. Static AWS credentials remain a separate concern; least privilege, rotation, and workload identity are still follow-up items.
2. **High — Static AWS credentials are bootstrapped into the cluster.** The External Secrets store authenticates via a Kubernetes Secret containing access keys. Verify the IAM principal is least-privileged, rotated, and restricted to the required Secrets Manager paths; consider workload identity/OIDC where supported.
3. **High — pgAdmin values include a literal default password.** [`databases/pgadmin/values.yaml`](../databases/pgadmin/values.yaml) contains literal initial login settings, including a default password; values are deliberately not repeated here. Replace with External Secrets and rotate any deployed credential before exposing/reusing this chart.
4. **Medium — Mutable image tags reduce deployment reproducibility.** Several workloads use `latest`, `stable`, or `main-stable` (including Speedtest Tracker, pgAdmin, Memos and LiteLLM). Pin versions or digests and define an update process.
5. **Medium — Bootstrap waits a fixed 180 seconds for the External Secrets webhook.** A fixed pause can be unnecessarily slow or fail on slower starts. Prefer a readiness/condition wait with a timeout.
6. **Medium — External provisioning target files are local prerequisites.** The Makefile expects populated `config/backend/prod.tfbackend` and `config/environment/prod.tfvars`, while only examples are tracked. Documented safety checks are important because `make -C external` executes `tofu apply` after planning.
7. **Medium — No automated validation is checked in.** There is no test suite or CI workflow visible in the tracked source inventory. Add checks for YAML/Helm rendering, Ansible syntax, Terraform/OpenTofu formatting and validation, with secrets and live apply excluded.
8. **Review — broad privileged-mover namespace annotation.** The Argo CD ApplicationSet annotates all managed namespaces for privileged VolSync movers; assess whether this broad default remains necessary and narrow it if possible.
9. **Review — public infrastructure metadata.** Hostnames, IP addresses and hardware MACs appear in tracked configuration. Confirm the intended disclosure boundary and move sensitive inventory to a private source if needed.

## Validation boundaries

This review was performed from tracked files. It did not connect to Kubernetes, query AWS, render Helm charts, execute Ansible against hosts, or apply OpenTofu. Those actions can be destructive or expose credentials and require an operator-controlled environment. Refer to `operations.md` for safe, non-deploying validation commands.
