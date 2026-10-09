# Open questions and operator follow-up

Source snapshot: `43add6737b6c6a9d9fa45e48a451aeae5b34812a`. These questions arise from tracked configuration, not observed production faults. Resolve live-state questions only in an explicitly authorized operator environment; this documentation pass did not access production.

## Provisioning and credentials

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
