# Repository guidance

- Start with [README.md](README.md) and the [documentation index](docs/index.md); trace claims to source before editing.
- Layers: `bare/` (Ansible/PXE/K3s), `external/` (OpenTofu/AWS), `system/` (bootstrap/system services), `platform/`, `databases/`, and `apps/` (GitOps workloads).
- Keep changes focused and match surrounding conventions. For documentation-only tasks, edit only Markdown; do not change infrastructure, generated files, or dependency pins.
- Describe checked-in declarations, not live state. Verify active versus commented module calls, `Chart.yaml` versus `values.yaml`, explicit namespaces versus ApplicationSet defaults, and recovery inputs versus recurring backups. Refresh reviewed revision references together.
- Never read or expose local credential files, populated environment/backend configuration, kubeconfigs, state, plans, or secret values. Document identifiers only.
- Root/bare/system Make targets provision hosts or Kubernetes; `make -C external` includes apply. Never run deployments or access production without separate authorization. Documentation-only branches, commits, and PRs are permitted under the maintainer mission; never merge a PR without operator approval.
- New lifecycle maintenance playbooks under `bare/` are operator workflows, not bootstrap dependencies; never run them against production as validation. Keep update/reboot opt-in and preserve existing PXE/K3s bootstrap targets.
- Validate modified Markdown, relative links/anchors, and source claims; run `git diff --check`. Check public reference URLs without contacting internal service endpoints. Use [operations](docs/operations.md#safe-validation-no-applydeploy) for layer-specific checks only when relevant and authorized.
- Report exact changed files and actual checks, including skipped checks or blockers. Never equate local validation with deployment health.
