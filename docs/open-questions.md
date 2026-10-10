# Open questions and operator follow-up

Source snapshot: `d6ba04de243fdb722145dc556bfc28a32965ca61`. These questions concern repository configuration and do not imply a production fault. Verify runtime behavior before making changes.

## Provisioning and credentials

- Which storage devices and capacities are installed on each production host? The inventory lists three nodes but does not record disk hardware; see the [hardware inventory](hardware-inventory.md) for currently documented host specifications.

- Who supplies and rotates access keys for the IAM users, required Secrets Manager values, the SSM parameter value, and the bootstrap environment? The [IAM user module](../external/modules/iam/user/v1/main.tf) creates no keys; the [Secrets Manager module](../external/modules/secrets-manager/v1/main.tf) creates containers only; the [SSM module](../external/modules/parameter-store/v1/main.tf) ignores later value changes. Confirm ownership without recording credentials here.
- Are the declared PushSecret writers and their IAM permissions sufficient for the intended remote destinations? `speedtest_db_secrets` and `argocd_app_secrets` are commented out in [the root module file](../external/sm.tf), while their Kubernetes push flows remain declared. Source does not establish whether the destination objects or values exist.
- Should the ISO download enable its configured checksum, and should the GRUB ISO URL derive from `iso_uri`? The [PXE task](../bare/roles/pxe_server/tasks/main.yml) comments out verification; the [GRUB template](../bare/roles/pxe_server/templates/grub.cfg.j2) hard-codes the basename. Until changed separately, do not treat the variable as enforced verification.
- How is PXE DHCP isolated from existing LAN DHCP services? [Compose](../bare/roles/pxe_server/files/docker-compose.yml) gives dnsmasq host networking and `NET_ADMIN`, and its [template](../bare/roles/pxe_server/templates/dnsmasq.conf.j2) serves leases rather than proxy-DHCP. Review pool, router, interfaces, and exposure before starting it.

## Recovery and storage

- Do the configured historical recovery sources exist and support a controlled restore? [Linkding](../databases/linkding-db/cluster.yaml) reads `linkding-db-backup-v2` but writes recurring backups under `linkding-db-backup-v3`; [Speedtest](../databases/speedtest-db/cluster.yaml) reads `speedtest-db-backup-v5` but writes under `speedtest-db-backup-v6`. Current schedules and retention do not prove historical source availability.
- Which Longhorn volumes are assigned snapshot/backup jobs, and have restores been tested? [Values](../system/longhorn/values.yaml) configure `Retain` and an S3 target but comment out recurring-job selection; the [template](../system/longhorn/templates/recurringjob-snapshot.yaml) declares both jobs. Definitions alone do not prove assignment or successful execution.
- Is the pgAdmin existing claim available, and how will its literal initial login configuration be replaced and any deployed credential rotated? Both are declared in [pgAdmin values](../databases/pgadmin/values.yaml); neither claim existence nor credential use was verified.

## Reconciliation and cluster behavior

- Does the target K3s CoreDNS configuration import `coredns-custom`, and is its internal-domain upstream suitable and reachable? The [custom forwarding manifest](../system/coredns/upstream-dns.yaml) declares the block only. Do not infer runtime DNS behavior from that ConfigMap alone.
- Are the extra directory-derived namespaces intentional when manifests explicitly target application namespaces or `kube-system`? The [ApplicationSet](../system/argocd/values.yaml) sets the destination to the directory basename and enables namespace creation, while database/CoreDNS manifests specify other namespaces. Review rendered resources and Argo CD diffs in an authorized environment.
- Should bootstrap wait for webhook readiness instead of a fixed pause? The [bootstrap playbook](../system/bootstrap.yml) waits 180 seconds; source does not establish readiness after that interval.
- Should privileged VolSync mover annotations be narrowed, mutable image tags pinned, and automated validation added? These source-review follow-ups are detailed in [architecture](architecture.md#findings-and-follow-up-priorities); no infrastructure changes are included in this pass.

## Network, security, and storage runtime review

The [networking reference](networking.md) details transport and exposure boundaries;
[storage and backup declarations](storage.md) distinguish volume jobs, database
recovery inputs, and object-store protections; [security declarations and trust
boundaries](security.md) separate source-backed findings from potential risks.
The questions below concern unverified runtime controls, not observed faults.
The existing provisioning, recovery, and CoreDNS questions above still apply;
resolve these only in a separately authorized operator review.

- Which K3s networking components and policies are active, which nodes and networks expose services, and do ingress authentication, redirects, backend transport, proxy trust, and certificate readiness match intent?
- Which MQTT listeners, client authentication, topic permissions, and transport modes are effective, and is device pairing limited to an intended window? Dashboard TLS does not establish MQTT encryption.
- Do effective cloud permissions constrain DNS changes and backup access as intended, and do Kubernetes RBAC, admission controls, and encryption at rest protect shared secret-store access? Source declarations do not identify the principals behind supplied credentials.
- Are GitOps approval and deletion controls, artifact provenance, and workload hardening effective? Did the registry helper emit authentication material into logs, and who can access those logs? Verify handling without copying credential values.
- Which storage classes, replica placements, and shared failure domains apply to existing volumes and databases? Do backup integrity, object/version retention, and authorized recovery tests support the intended recovery objectives? Declared retention and replication are not durability guarantees.
