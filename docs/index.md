# Documentation index

## Scope

Source snapshot: `43add6737b6c6a9d9fa45e48a451aeae5b34812a` (checked-out revision for this maintenance pass). Documentation describes tracked configuration only, not deployed versions, resource existence, health, credential validity, or backup success. No production systems or private repository were accessed.

## Guides

- [Repository overview](../README.md): layout and lifecycle boundaries.
- [Architecture](architecture.md): layers, GitOps, DNS, and trust boundaries.
- [Service and dependency catalog](service-catalog.md): applications, namespaces, PostgreSQL recovery/backup declarations, and secret-provider mappings.
- [Provisioning reference](provisioning-reference.md): PXE/DHCP, K3s, active AWS module calls, and operator-supplied inputs.
- [Operations guide](operations.md): prerequisites, state-changing command boundaries, validation, and recovery cautions.
- [Open questions](open-questions.md): source-backed uncertainties requiring an operator decision or controlled verification.
- [Contributor guidance](../AGENTS.md): repository safety and documentation conventions.

## Reading source accurately

`Chart.yaml` pins Helm dependencies; runtime settings generally live in `values.yaml` and templates. Raw manifests can explicitly target namespaces different from their ApplicationSet destination default. Commented-out OpenTofu calls are not active resources, and secret containers or backup schedules do not establish populated values or successful backups.

When updating these guides, verify claims against current source and refresh snapshot references together. Keep identifiers distinct from secret values; do not include credentials, generated manifests, state, plans, or kubeconfigs.
