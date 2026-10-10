# Documentation index

## Scope

Source snapshot: `004d097fe82384043520a1e43d1f085f59f0b852` (checked-out revision for this maintenance pass). Documentation describes tracked configuration only, not deployed versions, resource existence, health, credential validity, or backup success. No production systems or private repository were accessed.

## Guides

- [Repository overview](../README.md): layout and lifecycle boundaries.
- [Architecture](architecture.md): layers, GitOps, DNS, and trust boundaries.
- [Service and dependency catalog](service-catalog.md): applications, namespaces, PostgreSQL recovery/backup declarations, and secret-provider mappings.
- [Provisioning reference](provisioning-reference.md): PXE/DHCP, K3s, active AWS module calls, and operator-supplied inputs.
- [Operations guide](operations.md): prerequisites, state-changing command boundaries, validation, and recovery cautions.
- [Networking reference](networking.md): qualified K3s defaults, ingress/TLS, DNS credential boundaries, MQTT transport, and PXE exposure.
- [Storage and backup declarations](storage.md): Longhorn jobs, PostgreSQL backup/recovery inputs, and S3 protection and retention limits.
- [Security declarations and trust boundaries](security.md): GitOps and credential flows, access-control declarations, potential risks, and authorized operator verification.
- [Recovery first response](runbooks/recovery.md): safe read-only triage, evidence limits, and stop gates before any data-changing recovery.
- [OS lifecycle and maintenance](maintenance/os-lifecycle.md): opt-in Ansible maintenance, host policies, local osquery snapshots, drift comparison, and production approval boundaries.
- [Open questions](open-questions.md): source-backed uncertainties requiring an operator decision or controlled verification.
- [Contributor guidance](../AGENTS.md): repository safety and documentation conventions.

## Reading source accurately

`Chart.yaml` pins Helm dependencies; runtime settings generally live in `values.yaml` and templates. Raw manifests can explicitly target namespaces different from their ApplicationSet destination default. Commented-out OpenTofu calls are not active resources, and secret containers or backup schedules do not establish populated values or successful backups.

When updating these guides, verify claims against current source and refresh snapshot references together. Keep identifiers distinct from secret values; do not include credentials, generated manifests, state, plans, or kubeconfigs.
