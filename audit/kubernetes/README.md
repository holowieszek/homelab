# Read-only K3s inventory

This folder provides a **local, on-demand inventory** of the Kubernetes resources exposed by the cluster API. It complements the desired-state documentation: manifests and Helm values in Git describe what is configured, while a snapshot can show what the API currently reports. The collector does not install agents, schedule jobs, or change the cluster.

## Access model

`readonly-access.json` declares a dedicated `homelab-audit` namespace, a `cluster-inventory` ServiceAccount, and a ClusterRole/ClusterRoleBinding. The ServiceAccount has token automount disabled. Its ClusterRole grants only `get` and `list` on the explicitly named core, apps, batch, networking, storage, RBAC, API extensions, Argo CD, CloudNativePG, External Secrets, cert-manager, and Longhorn resources queried by `collect.py`. It does not grant wildcard resources, `watch`, mutation verbs, `secrets`, or `configmaps`.

The manifest is a **declaration**, not deployed state. Applying it is a separate operator action requiring normal change review and access to the cluster's administrative kubeconfig. The audit workflow never applies or modifies cluster resources. Keep the administrative kubeconfig separate from the generated reader kubeconfig.

The reader kubeconfig is generated with a TokenRequest for a requested 10-minute lifetime and automatically deleted after collection. The API server may cap the actual token lifetime. The helper copies only the selected cluster's HTTPS endpoint and CA data; admin user credentials are not copied into the reader kubeconfig.

The collector uses `kubectl proxy` bound to loopback, accepts only the resource paths in its allowlist, rejects mutating HTTP methods, and requests Kubernetes `Table` responses with `includeObject=None` to avoid including row objects. It projects an explicit set of columns and refuses full-object responses or table rows containing embedded objects as a second safety check; it never retries using full JSON objects. Snapshots are new files with mode `0600` in a private directory outside Git, and existing output files are not overwritten. Snapshot fields intentionally exclude pod specs, environment variables, Secret data, ConfigMaps, and raw events. Metadata included in allowed table columns can still reveal internal object names, namespaces, hostnames, or ingress hostnames; store snapshots as sensitive operational data.

This is read-only at the Kubernetes API permission layer, but collection of objects such as RBAC rules and custom-resource definitions exposes configuration details. Limit access to the generated snapshot. A restricted collector identity is not a substitute for securing the host running the collector or the administrative credential used to mint its temporary token.

## Operator workflow

Prerequisites: Python 3 and `kubectl` installed; a private admin kubeconfig with permission to create a TokenRequest for `homelab-audit/cluster-inventory`; the read-only manifest installed in advance by an operator; and a private destination directory. The workflow never applies or modifies cluster resources.

```sh
umask 077
PRIVATE_DIR="$HOME/.local/share/homelab-cluster-audit"
install -d -m 700 "$PRIVATE_DIR"
python3 audit/kubernetes/run_audit.py \
  --admin-kubeconfig "$HOME/.kube/config" \
  --context "YOUR_CLUSTER_CONTEXT" \
  --output "$PRIVATE_DIR/snapshot-$(date +%F-%H%M%S).json"
```

The runner creates the reader kubeconfig with mode `0600` beneath the private destination directory, uses it only for collection, then removes it. The token expires after its requested lifetime. The inventory calls never use the admin identity; it is used only to resolve the selected cluster's connection metadata and request a short-lived ServiceAccount token. Snapshots are retained as private files; apply the owner's normal retention policy.

The collector reports per-resource statuses, such as `OK`, `ABSENT`, `FORBIDDEN`, `UNAVAILABLE`, `TABLE_UNSUPPORTED`, and `UNSAFE_RESPONSE`. Optional custom resources may be absent when their CRD is not installed. Required-resource failures produce `PARTIAL` and a nonzero exit code. Review the status before treating a snapshot as complete. Do not share raw output publicly.

## Scope and extension

The collector inventories cluster nodes, namespaces, workloads, Services, storage claims/volumes/classes, ingress/network policies, RBAC declarations, CRDs, and selected installed-operator custom resources. It intentionally does not retrieve Secrets, ConfigMaps, arbitrary custom-resource definitions' instances, workload specs, environment values, logs, events, or host-level settings. Extend the resource and column allowlists and matching RBAC rules together, with tests; do not solve missing data by granting broad read access.

The repository's `bare/roles/k3s/tasks/main.yml` declares a K3s server on the `masters` group and agents on `workers`; the production inventory assigns `bare0` as master and `bare1`/`bare2` as workers. The cluster configuration file is copied to the controller during that provisioning workflow. These are checked-in provisioning declarations, not proof of current live membership or health. See [architecture](../../docs/architecture.md), [service catalog](../../docs/service-catalog.md), and [provisioning reference](../../docs/provisioning-reference.md) for the broader desired-state context.

## Validation and references

Run the local tests with:

```sh
python3 -m unittest discover -s audit/kubernetes/tests -v
```

Tests validate table-only response handling, allowlisted projection, refusal of embedded/full objects, read-only RBAC correspondence, short-lived kubeconfig construction, private output handling, and proxy restrictions. They do not connect to the live cluster. `kubectl` and `ansible-playbook` are not required to run these unit tests.

Primary references:

- Kubernetes RBAC authorization: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Kubernetes API concepts, content negotiation, and Table responses: https://kubernetes.io/docs/reference/using-api/api-concepts/
- Kubernetes ServiceAccounts and TokenRequest: https://kubernetes.io/docs/concepts/security/service-accounts/
- Kubernetes `kubectl proxy`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_proxy/
- K3s security hardening guide: https://docs.k3s.io/security/hardening-guide
