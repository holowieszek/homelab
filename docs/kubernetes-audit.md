# Read-only K3s inventory

`audit/kubernetes/` contains a local, on-demand collector for resources exposed by the Kubernetes API. It complements the repository's desired-state documentation: Git describes provisioning and declared workloads, while an inventory snapshot records selected API-reported state at collection time. This is not a deployment, drift-remediation, or compliance-enforcement system.

## Production inventory snapshot

The read-only collection completed on `2026-10-10T20:58:44Z`. The API returned `OK` for all 33 requested resource types and the snapshot contains 956 rows across those collections. This is a point-in-time inventory, not a health check; retain the raw snapshot only in the private audit directory.

| Area | Observed at collection time |
|---|---|
| K3s nodes | 3 of 3 reported `Ready`; all reported `v1.31.6+k3s1`. |
| Namespaces | 39 Namespace objects. |
| Pods | 96 objects: 85 `Running`, 11 `Completed`; 3 rows had nonzero restart counters, totaling 82. Restart counters are cumulative, not a recent-failure rate. |
| Workload controllers | 34 Deployments reported ready/desired replica counts equal; 7 of 7 DaemonSets reported 3/3 desired/current/ready; 6 StatefulSets reported ready/desired counts equal. |
| Jobs | 70 of 72 reported `1/1` completions; 2 reported `0/1`. The selected Table columns do not distinguish pending, active, suspended, or failed Jobs. |
| GitOps and operators | 25 Argo CD Application objects, 5 CloudNativePG Cluster objects, and 19 ExternalSecret objects were returned. Their presence does not establish sync, health, secret synchronization, or database readiness. |
| Storage | 18 of 18 PVCs reported `Bound` and `longhorn`; 18 PVs reported `Bound`; 3 StorageClass objects and 18 Longhorn Volume objects were listed. These fields do not establish replica health, capacity in use, or successful backups/restores. |
| Network policy | 0 standard Kubernetes NetworkPolicy objects were returned. The collector did not inspect the active CNI, host firewalls, or other network enforcement. |

The `Roles` column showed `control-plane,master` for one node and `<none>` for the other two. This is Kubernetes node-role label output; the Ansible `masters`/`workers` inventory groups remain the provisioning declaration and should not be inferred solely from this display.

For this production collection, the documented reader-access objects had been installed with operator approval. RBAC validation allowed all 66 expected `get`/`list` permission pairs; checks for Secret and ConfigMap reads, Pod creation, and Pod `watch` were denied. These checks describe the reader identity at validation time, not a guarantee against later RBAC changes.

Kubernetes documents that NetworkPolicy enforcement depends on a supporting network plugin; in a namespace with no applicable NetworkPolicy, Kubernetes' standard policy model allows ingress and egress by default ([NetworkPolicy concepts](https://kubernetes.io/docs/concepts/services-networking/network-policies/)). The zero-object result therefore warrants a review of whether this is intended, but does not prove the absence of other isolation controls; see the [K3s networking services](https://docs.k3s.io/networking/networking-services) documentation.

The collection did not retrieve pod specifications, resource requests/limits, actual CPU or memory usage, event/log details, PVC usage, Argo CD sync/health fields, CNPG readiness, Longhorn replica health, backup outcomes, or effective CNI configuration. Do not convert the counts above into claims about those properties.

## Access model

`readonly-access.json` declares a dedicated `homelab-audit` namespace and `cluster-inventory` ServiceAccount. Its ClusterRole grants only `get` and `list` on the collector's explicitly enumerated core, apps, batch, networking, storage, RBAC, API extensions, Argo CD, CloudNativePG, External Secrets, cert-manager, and Longhorn resources. It contains no wildcard grants, `watch`, mutation verbs, Secret access, or ConfigMap access; automatic ServiceAccount token mounting is disabled.

The manifest is a declaration, not evidence that these resources are installed. Applying it is a separate operator action requiring normal change review and an administrative kubeconfig. The documented audit workflow never applies or modifies cluster resources. Keep the admin kubeconfig separate from the generated reader credential.

The runner requests a ServiceAccount token with a requested lifetime of 10 minutes; the API server may cap it. The admin identity is used only to resolve cluster endpoint/CA metadata and request the token. API inventory requests use the token-only reader kubeconfig. That file is written with mode `0600` in the private output directory and removed when collection finishes.

The collector connects through `kubectl proxy` on loopback, allows only its enumerated resource paths, rejects mutating HTTP methods, and requests Kubernetes `Table` responses with `includeObject=None`. It projects allowlisted columns and refuses full objects or Table rows containing embedded objects rather than falling back to full JSON. Snapshots are new files with mode `0600` outside the repository; output paths must not already exist. The included fields omit workload specs, environment values, Secret data, ConfigMaps, logs, and raw events. Object names, namespaces, node names, and ingress hostnames may still be sensitive; protect snapshots as operational data.

RBAC/API access is read-only, but inventory of RBAC rules, CRDs, and selected operator resources reveals configuration. Protect both the machine running the collector and the administrative credentials used to mint the temporary token.

## Run an inventory

Prerequisites: Python 3, `kubectl`, a private admin kubeconfig able to create a TokenRequest for `homelab-audit/cluster-inventory`, the access manifest installed in advance by an operator, and a private destination directory.

```sh
umask 077
PRIVATE_DIR="$HOME/.local/share/homelab-cluster-audit"
install -d -m 700 "$PRIVATE_DIR"
python3 audit/kubernetes/run_audit.py \
  --admin-kubeconfig "$HOME/.kube/config" \
  --context "YOUR_CLUSTER_CONTEXT" \
  --output "$PRIVATE_DIR/snapshot-$(date +%F-%H%M%S).json"
```

Omit `--context` if the kubeconfig's current context is the intended cluster. The workflow does not print tokens or raw API responses. The token-only kubeconfig is removed after collection; snapshots remain in the private directory for the operator's retention policy.

The collector includes per-resource statuses such as `OK`, `ABSENT`, `FORBIDDEN`, `UNAVAILABLE`, `TABLE_UNSUPPORTED`, and `UNSAFE_RESPONSE`. Optional custom resources can be absent if the corresponding CRD is not installed. Required-resource failures make the overall collection `PARTIAL` and return a nonzero exit code. Review all statuses before treating the snapshot as complete; do not publish raw snapshots.

## Scope

The allowlist covers nodes, namespaces, workloads, Services, storage claims/volumes/classes, ingresses and network policies, RBAC declarations, CRDs, and selected installed-operator custom resources. It intentionally excludes Secrets, ConfigMaps, events, logs, pod specifications, environment values, and host-level settings. Add a resource only by updating the collector, RBAC manifest, tests, and documentation together; do not grant broad read access to fill gaps.

The repository declares a K3s server on the `masters` group and agents on `workers`; production inventory assigns `bare0` as master and `bare1`/`bare2` as workers. These are provisioning declarations, not confirmation of live membership or health. See [architecture](architecture.md), [service catalog](service-catalog.md), and [provisioning reference](provisioning-reference.md).

## Local validation

```sh
python3 -m unittest discover -s audit/kubernetes/tests -v
```

Tests cover safe Table projection, refusal of embedded/full objects, exact RBAC-to-collector resource correspondence, token-only kubeconfig construction, private output behavior, and proxy restrictions. They do not connect to a live cluster or validate the deployed K3s API version.

## Primary references

- Kubernetes RBAC authorization: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Kubernetes API concepts and Table responses: https://kubernetes.io/docs/reference/using-api/api-concepts/
- Kubernetes ServiceAccounts and TokenRequest: https://kubernetes.io/docs/concepts/security/service-accounts/
- Kubernetes `kubectl proxy`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_proxy/
- K3s security hardening guide: https://docs.k3s.io/security/hardening-guide
