# Storage and backup declarations

Source snapshot: `d6ba04de243fdb722145dc556bfc28a32965ca61`.

## Scope

This guide describes current tracked configuration and existing documentation,
not deployed resources. It makes no assertions about backup execution, backup
integrity, restore success, or achievable recovery objectives. Concrete storage
targets and credential identifiers are intentionally omitted.

## Longhorn volumes and recurring jobs

The [chart declaration](../system/longhorn/Chart.yaml) pins Longhorn `1.8.1`.
[Values](../system/longhorn/values.yaml) set `persistence.defaultClass: true`
and `persistence.reclaimPolicy: Retain`: the chart declares Longhorn as a default
StorageClass, with retained backing storage after claim deletion rather than
automatic reclamation. Retention requires deliberate cleanup; it is not a backup.
This does not establish which StorageClasses or volumes exist in a cluster.

The same values declare an S3 backup target and a Kubernetes Secret reference
for backup credentials. A configured target and reference do not establish
credential availability, access permissions, or successful uploads.

The [RecurringJob template](../system/longhorn/templates/recurringjob-snapshot.yaml)
declares two separate jobs:

| Task | Five-field cron | Cadence | Retain | Concurrency |
| --- | --- | --- | ---: | ---: |
| `snapshot` | `0 */6 * * *` | Every six hours, at minute zero | 4 | 5 |
| `backup` | `0 */6 * * *` | Every six hours, at minute zero | 4 | 5 |

`retain` is a per-volume, per-job snapshot/backup count, and `concurrency` limits
concurrent executions of that job; neither is a global storage retention limit.
Snapshots are volume-local; the backup task creates snapshots and backs them up
to the configured backup store. These are distinct operations [3].

The StorageClass `recurringJobSelector`, its enable flag, and its volume job list
are commented out in values. Each job declares its own group, not the special
`default` group that automatically selects otherwise unassigned volumes [3].
The definitions therefore do not establish volume assignment or execution.
See the [catalog storage note](service-catalog.md#shared-platform-services).

## PostgreSQL data and backups

The [operator chart](../platform/cloudnative-pg/Chart.yaml) pins the
CloudNativePG Helm chart to `0.23.0`; that is a chart version, not an assertion
about a running operator version. The versioned reference below is
CloudNativePG `1.25` [10].

| Cluster manifest | Instances | Data PVC size per instance | Explicit storage class |
| --- | ---: | --- | --- |
| [Home Assistant](../databases/home-assistant-db/cluster.yaml) | 3 | `10Gi` | `longhorn` |
| [Linkding](../databases/linkding-db/cluster.yaml) | 1 | `1Gi` | Not set |
| [LiteLLM](../databases/litellm-db/cluster.yaml) | 1 | `1Gi` | Not set |
| [MeshCore telemetry](../databases/meshcore-telemetry-db/cluster.yaml) | 3 | `1Gi` | Not set |
| [Speedtest](../databases/speedtest-db/cluster.yaml) | 3 | `1Gi` | Not set |

All five Cluster manifests configure Barman object-store backups to S3, with
Secret-backed credentials, gzip compression for data and WAL, and
`retentionPolicy: 21d`. This is a recovery-window policy, not an S3 object
expiration rule [10]. Their ScheduledBackup declarations set `immediate: true`
and `schedule: "0 0 */6 * * *"`: a six-field expression including seconds,
requesting a backup every six hours at second and minute zero [10]. These are
PostgreSQL backup declarations, separate from Longhorn volume backups.

Linkding and Speedtest declare bootstrap recovery from historical external
sources whose backup server names differ from their recurring backup outputs.
Recovery is an initialization input, not a scheduled restore. See
[historical recovery versus recurring backups](service-catalog.md#bootstrap-recovery-versus-recurring-backups)
and the [database catalog](service-catalog.md#postgresql-cluster-and-backup-declarations)
for the source-backed distinction; no historical backup availability or restore
success is implied.

Without an explicit storage class, CNPG relies on the Kubernetes default [11];
Longhorn being declared default does not prove the effective class of existing
PVCs. One PostgreSQL instance provides no standby; three instances declare a
primary with two standbys [12], not a proven failure-tolerance guarantee. The cluster
manifests do not specify synchronous replication or placement constraints, and
Longhorn values do not explicitly override volume replica counts. PostgreSQL
replicas and storage replicas are different layers. Effective defaults, replica
placement, shared failure domains, storage health, and loss-free failover remain
unverified; no node-failure tolerance or backup/restore success is asserted.

## S3 module protections and omissions

The active [S3 callers](../external/s3.tf) use the
[S3 module](../external/modules/s3/v1/main.tf), which declares:

- Default server-side encryption using `AES256` (SSE-S3).
- Versioning, with all callers setting its status to `Enabled`.
- Public-access blocks, with all callers setting `block_public_acls`,
  `block_public_policy`, `ignore_public_acls`, and `restrict_public_buckets`
  to `true`.

No object expiration/lifecycle rules, Object Lock, or replication are declared
in this module. Application/job retention is not equivalent to S3 lifecycle
cleanup, including cleanup of noncurrent object versions.

Callers pass `acl = "private"`, but the module only
[declares that input](../external/modules/s3/v1/variables.tf): it does not consume
it or create an ACL resource. Do not attribute an applied ACL to that setting.
Access logging is conditional on a nonempty logging target bucket; the input
default is empty and callers do not set a target, so these calls do not declare
logging resources. These are source-level controls, not verified bucket state.

## Sources

[3] [Longhorn 1.8.1: Scheduling Backups and Snapshots](https://longhorn.io/docs/archives/1.8.1/snapshots-and-backups/scheduling-backups-and-snapshots)
[10] [CloudNativePG 1.25: Backup](https://cloudnative-pg.io/docs/1.25/backup)
[11] [CloudNativePG 1.25: Storage](https://cloudnative-pg.io/docs/1.25/storage)
[12] [CloudNativePG 1.25: Replication](https://cloudnative-pg.io/docs/1.25/replication)
