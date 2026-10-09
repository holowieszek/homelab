# Recovery first response

## Scope and safety boundary

This runbook describes tracked declarations and read-only triage, not a tested
restore procedure. It does not establish backup existence, integrity,
restorability, or live deployment health. No RPO or RTO is established here;
obtain recovery objectives from the accountable operator rather than deriving
them from schedules or retention settings.

Start with the [documentation index](../index.md),
[service and dependency catalog](../service-catalog.md), and
[operations recovery cautions](../operations.md#recovery-and-safety-notes).
Repository facts below are declarations; commands are optional live checks for
an explicitly authorized operator workstation. They were not run against a
cluster while authoring this document.

Do not run provisioning, sync, restart, deletion, restore, or rollback commands
during first response. Do not retrieve or print Secret values, kubeconfigs,
tokens, S3 contents, or internal addresses. Avoid full object dumps, rendered
manifests, `describe`, logs, environment dumps, and unfiltered Argo CD diffs:
these can disclose sensitive values or addresses. The commands below select
identifiers, status codes, counts, and timestamps only. Keep even this evidence
in an access-controlled incident record; do not enable shell tracing.

If any read fails, stop that diagnostic path. Do not broaden permissions,
refresh credentials by printing them, or proceed with an unverified target.

## 1. Establish ownership and the correct cluster

Before accessing Kubernetes, identify the incident lead and recovery owner,
authorized cluster, affected application, and workload namespace. If the
recovery owner or target identity is unknown, stop and escalate to the
infrastructure operator and service owner; this repository does not supply an
on-call contact or recovery authority.

Use an already configured trusted workstation. Obtain the approved context
identifier and a previously recorded `kube-system` namespace UID from a trusted
operator baseline, not from the suspect cluster itself. Do not read or print a
kubeconfig. Context names alone are not proof of cluster identity.

```sh
set +x
: "${RECOVERY_CONTEXT:?Set the approved context identifier privately}"
: "${EXPECTED_KUBE_SYSTEM_UID:?Obtain the trusted cluster identity baseline}"
: "${WORKLOAD_NAMESPACE:?Set the verified affected workload namespace}"
: "${ARGO_APPLICATION:?Set the verified Argo CD application name}"

# Compare without displaying the configured context or kubeconfig.
if ! test "$(kubectl config current-context 2>/dev/null)" = "$RECOVERY_CONTEXT"; then
  printf "%s\n" "STOP: current context does not match the approved context."
  return 1 2>/dev/null || exit 1
fi

# Pin every live read; suppress errors that may contain an internal endpoint.
kread() {
  kubectl --context="$RECOVERY_CONTEXT" --request-timeout=10s "$@" 2>/dev/null || {
    printf "%s\n" "STOP: read failed; escalate without printing raw errors." >&2
    return 1
  }
}

if ! test "$(kread get namespace kube-system -o=jsonpath="{.metadata.uid}")" = "$EXPECTED_KUBE_SYSTEM_UID"; then
  printf "%s\n" "STOP: cluster identity is unverified or differs from baseline."
  return 1 2>/dev/null || exit 1
fi

kread get namespace "$WORKLOAD_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,UID:.metadata.uid,PHASE:.status.phase"
```

Do not switch contexts automatically. Resolve a mismatch outside this runbook
with the authorized operator. A rebuilt cluster may have a different UID;
that requires a new independently approved baseline, not bypassing the check.
Run subsequent commands in the same shell, and stop on any failure.

Source declaration: the
[Argo CD ApplicationSets](../../system/argocd/values.yaml) default application
names and destination namespaces to directory basenames. Explicit database
manifest namespaces take precedence: `linkding-db` is in `linkding`, and
`speedtest-db` is in `speedtest`. Confirm the actual resource namespace rather
than treating the Argo CD destination default as workload placement.

## 2. Inspect Argo CD and application health

Source declaration: [Argo CD values](../../system/argocd/values.yaml) place the
ApplicationSets in `argocd` and enable automated sync, pruning, and self-healing.
A manual change can be reconciled away; a Git rollback may trigger deletion or
application migrations. Neither is a read-only diagnostic step.

```sh
kread get deployments,statefulsets -n argocd \
  -o "custom-columns=NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas"
kread get applications.argoproj.io -n argocd \
  -o "custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,OPERATION:.status.operationState.phase"
kread get applications.argoproj.io "$ARGO_APPLICATION" -n argocd \
  -o "custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision,DESTINATION_NS:.spec.destination.namespace,OPERATION:.status.operationState.phase"
```

Record the selected revision, sync/health status, and any running operation.
Distinguish controller unavailability, reconciliation failure, and workload
failure. `Synced` or `Healthy` does not prove application data correctness or
backup success. Missing resources, unavailable CRDs, or denied access are
unknowns, not evidence that there is no incident. Escalate to the GitOps operator
before considering any reconciliation changes.

## 3. Inspect pods, events, and persistent claims

```sh
kread get pods -n "$WORKLOAD_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount,WAITING:.status.containerStatuses[*].state.waiting.reason,INIT_WAITING:.status.initContainerStatuses[*].state.waiting.reason"
kread get events -n "$WORKLOAD_NAMESPACE" --sort-by=.metadata.creationTimestamp \
  -o "custom-columns=TIME:.metadata.creationTimestamp,TYPE:.type,REASON:.reason,KIND:.involvedObject.kind,OBJECT:.involvedObject.name,COUNT:.count"
kread get persistentvolumeclaims -n "$WORKLOAD_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,PHASE:.status.phase,PV:.spec.volumeName,CLASS:.spec.storageClassName,REQUESTED:.spec.resources.requests.storage,CAPACITY:.status.capacity.storage"
```

Look for pending claims, attachment/mount or scheduling reason codes, failing
init containers, and restarting database/application pods. Event messages are
intentionally excluded; events also expire, so an empty list is not proof of
absence of failure. Blank status fields are unknowns, not successful checks.
Do not delete pods or PVCs as a diagnostic experiment.

Set `PV_NAME` only from the affected bound PVC, then read its safe mapping:

```sh
: "${PV_NAME:?Set the exact PV identifier from the affected PVC}"
kread get persistentvolumes "$PV_NAME" \
  -o "custom-columns=NAME:.metadata.name,PHASE:.status.phase,CLAIM_NS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,DRIVER:.spec.csi.driver"
```

Confirm claim namespace/name and driver, then correlate the PV name with the
Longhorn volume's Kubernetes status fields in step 5. Do not print volume handles.
If unbound or ambiguous, stop the storage path and escalate. A `Bound` PVC does
not demonstrate filesystem or database integrity.

## 4. Inspect CloudNativePG clusters and backup metadata

Source declarations: the
[service catalog database table](../service-catalog.md#postgresql-cluster-and-backup-declarations)
identifies clusters and explicit namespaces. The
[operator chart](../../platform/cloudnative-pg/Chart.yaml) pins a Helm dependency;
its presence does not demonstrate that the operator or CRDs are available.

For an affected PostgreSQL-backed service, set `CNPG_CLUSTER` to its confirmed
cluster identifier and keep `WORKLOAD_NAMESPACE` at the explicit database
namespace. Inspect metadata only:

```sh
: "${CNPG_CLUSTER:?Set the verified CloudNativePG cluster identifier}"
kread get clusters.postgresql.cnpg.io "$CNPG_CLUSTER" -n "$WORKLOAD_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,PHASE:.status.phase,DESIRED:.spec.instances,READY:.status.readyInstances,PRIMARY:.status.currentPrimary,LAST_SUCCESS:.status.lastSuccessfulBackup"
kread get clusters.postgresql.cnpg.io "$CNPG_CLUSTER" -n "$WORKLOAD_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,CONDITION:.status.conditions[*].type,STATUS:.status.conditions[*].status,REASON:.status.conditions[*].reason"
kread get scheduledbackups.postgresql.cnpg.io -n "$WORKLOAD_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,CLUSTER:.spec.cluster.name,SCHEDULE:.spec.schedule,SUSPENDED:.spec.suspend,LAST_SCHEDULE:.status.lastScheduleTime"
kread get backups.postgresql.cnpg.io -n "$WORKLOAD_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,CLUSTER:.spec.cluster.name,PHASE:.status.phase,START:.status.startedAt,STOP:.status.stoppedAt"
```

Associate each schedule/Backup with the affected cluster; other resources in
the namespace are not recovery evidence for it. Record completed/failed phases
and timestamps without reading object-store contents, credentials, or error
messages. A completed Backup or `lastSuccessfulBackup` reports controller
metadata, not independent proof that the required backup/WAL is still present,
intact, or restorable. Missing Backup resources do not prove S3 is empty.

### Bootstrap source is not current recurring output

The [Linkding manifest](../../databases/linkding-db/cluster.yaml) and
[Speedtest manifest](../../databases/speedtest-db/cluster.yaml) declare different
bootstrap recovery inputs and recurring backup outputs:

| Cluster | Bootstrap recovery source | Current backup server name |
| --- | --- | --- |
| `linkding-db` | `linkding-db-backup-v2` | `linkding-db-backup-v3` |
| `speedtest-db` | `speedtest-db-backup-v5` | `speedtest-db-backup-v6` |

See the
[service catalog recovery table](../service-catalog.md#bootstrap-recovery-versus-recurring-backups).
Bootstrap recovery is an initialization input, not a periodic restore. Current
schedules, `immediate: true`, and declared retention do not establish existence
or retention of the historical bootstrap source. Do not change the bootstrap
source to match current output, recreate a Cluster, or select a restore target
based only on these names. Home Assistant, LiteLLM, and MeshCore Telemetry
instead declare `bootstrap.initdb`, as documented in the catalog.

If the required backup and WAL availability cannot be independently confirmed
by an authorized backup owner, stop before restoration. This runbook does not
include S3 listing, downloading, or restore commands.

## 5. Inspect Longhorn volume and recurring-job assignment

Source declarations: [Longhorn values](../../system/longhorn/values.yaml)
configure a default storage class, `reclaimPolicy: Retain`, and an S3 backup
target. The recurring-job selector is commented out. The
[RecurringJob template](../../system/longhorn/templates/recurringjob-snapshot.yaml)
defines separate `snapshot-default` and `backup-default` tasks, each with a
same-named group, cron `0 */6 * * *`, retain count `4`, and concurrency `5`.
Neither a target nor job definitions establish volume assignment or successful
execution. A local snapshot is not an independent off-cluster backup; `Retain`
is not a backup guarantee.

The ApplicationSet defaults the chart destination to `longhorn`; do not assume
that either `longhorn` or the upstream `longhorn-system` is the live namespace.
Discover namespaced volume metadata, match the PV/PVC from step 3, and only then
set `LONGHORN_NAMESPACE` and `LONGHORN_VOLUME` to the exact observed identifiers.

```sh
kread get volumes.longhorn.io --all-namespaces \
  -o "custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PV:.status.kubernetesStatus.pvName,CLAIM_NS:.status.kubernetesStatus.namespace,PVC:.status.kubernetesStatus.pvcName,STATE:.status.state,ROBUSTNESS:.status.robustness"
: "${LONGHORN_NAMESPACE:?Set the verified Longhorn resource namespace}"
: "${LONGHORN_VOLUME:?Set the exact Longhorn volume matching the PV handle}"
kread get volumes.longhorn.io "$LONGHORN_VOLUME" -n "$LONGHORN_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,STATE:.status.state,ROBUSTNESS:.status.robustness,LAST_BACKUP:.status.lastBackup,LAST_BACKUP_AT:.status.lastBackupAt"
kread get recurringjobs.longhorn.io -n "$LONGHORN_NAMESPACE" \
  -o "custom-columns=NAME:.metadata.name,TASK:.spec.task,GROUPS:.spec.groups,CRON:.spec.cron,RETAIN:.spec.retain,CONCURRENCY:.spec.concurrency"
```

Do not interpret job existence or a backup timestamp as proof of assignment or
restorability. Use the approved Longhorn UI to inspect this exact volume and
its recurring-job selection (both direct jobs and groups) without opening
credential settings, endpoint details, or restore actions. The UI review must
not copy credential values, endpoints, volume handles, or internal addresses.
Compare selections with the live job/group names above, not merely the declared defaults. Record
whether snapshot and backup assignments are present, disabled, or unknown.
If the UI cannot be used safely or assignment cannot be established, stop and
escalate to the storage operator; do not enable jobs as a diagnostic step.

## Stop gates and recovery hand-off

Stop all data-changing recovery work and escalate when any of the following
is unresolved:

- **Unknown owner or approval authority:** the infrastructure operator and
  service owner must identify an accountable recovery owner before proceeding.
- **Unknown or mismatched target:** require the approved context/cluster
  identity, namespace, application, database, PVC/PV, and volume mappings.
- **Unknown backup existence or usable recovery point:** the backup/database or
  storage owner must independently establish the required source, backup/WAL
  availability, snapshot provenance, and retained history. A schedule, healthy
  application, completed resource, or timestamp does not satisfy this gate.
- **Unknown restore procedure:** require a version-appropriate, reviewed
  procedure and evidence of a controlled recovery test; do not improvise a
  restore from a chart, bootstrap declaration, or upstream example.
- **Ambiguous volume assignment, failed reads, or conflicting evidence:** retain
  safe observations and escalate rather than deleting, recreating, or guessing.

Any operator-initiated data-changing restoration or rollback requires conscious
approval by the accountable recovery owner, pre-restore backup/snapshot review,
and a verified destination. This includes application/Git rollback if it can
change schema or data, as well as database, filesystem, or volume restoration.
Before approval, document:

1. The incident evidence, intended recovery point, acceptable data loss, and
   owner-agreed objectives; do not invent RPO/RTO values.
2. The reviewed procedure, source identifiers, compatibility constraints, and
   evidence supporting backup integrity and recoverability.
3. Pre-restore backup/snapshot review of existing destination data, including
   how it will be preserved. If creating new protection is necessary, that is
   itself a separately approved data-changing action, not first-response triage.
4. The verified destination cluster, namespace, database/PVC/PV/volume, and
   isolation from unintended writers. Prefer an isolated verification target
   where the reviewed procedure supports it; never assume an empty destination.
5. How application writes and Argo CD reconciliation will be coordinated under
   approval, plus abort criteria and a plan to preserve the original data.
6. Read-only post-recovery checks and owner-approved functional/data validation.
   A ready pod or healthy Argo CD application alone is insufficient acceptance.

No command in this runbook initiates restore, deletes a PVC, overwrites data,
changes bootstrap sources, or applies infrastructure. For unresolved source
questions, see [recovery and storage follow-up](../open-questions.md#recovery-and-storage).
Until the gates are satisfied, report diagnosis and unknowns only; do not claim
that a backup works, recovery is complete, or deployment health is verified.
