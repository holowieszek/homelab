# Security declarations and trust boundaries

## Scope and evidence

This review describes checked-in declarations and potential risks, not runtime
state or evidence of compromise. Source was inspected at revision
`d6ba04de243fdb722145dc556bfc28a32965ca61`, alongside existing documentation and
the networking and storage guides in this working tree. No production system,
private repository, cloud state, credential file, or secret value was accessed.
Concrete domains, addresses, hostnames, cloud resource names, and internal
identifiers are deliberately omitted; source links use relative repository paths.

Start with the [repository overview](../README.md) and
[documentation index](index.md). Findings below establish what source declares;
risk statements describe possible consequences, not observed incidents. Open
questions and recommended operator verification are separated at the end.
Verification requires separate authorization and does not prescribe changes to
infrastructure.

## Source-backed findings and potential risks

### Public GitOps source is a supply-chain trust boundary

[Argo CD values](../system/argocd/values.yaml) declare a public Git source on a
moving branch, discover directories across applications, system components,
platform services, and databases, and enable automated synchronization with
`prune: true` and `selfHeal: true`. Namespace creation is also enabled.
[Chart declarations](../system/argocd/Chart.yaml) pin chart dependencies; they do
not make the Git branch immutable or establish artifact provenance.

Accepted source changes can therefore become cluster changes without a separate
manual sync step. Pruning can remove resources deleted from source, while
self-healing can overwrite manual drift. Repository write/merge authority,
upstream chart and image integrity, and controller authorization form the trust
boundary; public readability alone does not grant write access. This is a
potential supply-chain and deletion risk, not evidence that unauthorized code
has been accepted or that reconciliation is running.

### Ingress TLS is not authentication or backend encryption

[Argo CD](../system/argocd/templates/ingress.yaml),
[Longhorn](../system/longhorn/templates/ingress.yaml), and
[Grafana](../platform/grafana/templates/ingress.yaml) ingress templates declare
Traefik, certificate-issuer annotations, TLS hosts, and certificate Secrets.
Their backend service port is `80`;
[Argo CD values](../system/argocd/values.yaml) enable insecure server mode.
[Application values](../apps/memos/values.yaml) also distinguish ingress TLS
from an HTTP backend declaration.

These settings express intended edge TLS, not certificate readiness, login
requirements, authorization, network isolation, redirects, or encryption between
ingress and pods. A certificate is not an access-control policy. The templates
do not establish an additional ingress authentication layer; application-level
authentication remains a separate question. See
[networking: ingress and TLS boundaries](networking.md#ingress-and-tls-declaration-boundaries)
for transport and proxy-trust qualifications.

### DNS API credentials and solver selectors have different authority

The [issuer template](../system/cert-manager/templates/clusterissuer.yaml)
declares ACME DNS-01 through Route 53, with DNS-zone solver selectors and
Secret-backed access-key authentication. The
[ExternalSecret template](../system/cert-manager/templates/secret.yaml)
retrieves both access-key components into a Kubernetes Secret for cert-manager.
Upstream documents the DNS API permissions required for challenge changes [2].

Solver selectors decide which solver cert-manager uses for a request. They are
not IAM boundaries: they do not constrain what an AWS credential can authorize
outside that solver selection. AWS policy scope is a separate control. The
[IAM source](../external/iam.tf) declares zone-scoped record-list/change access,
zone discovery, and change-status access, without a TXT-only record-change
condition. The issuer does not set an explicit hosted-zone ID. The upstream
Route 53 guide discusses zone scoping, TXT restrictions, and the discovery
permission associated with omitting that ID [2].

DNS authority can affect certificate validation and other records within the
credential permissions. Source does not identify the actual principal behind
the supplied credential, prove its effective policy, or establish successful
DNS challenges. See [networking: DNS credential trust boundary](networking.md#acme-dns-01-and-route-53-credential-trust-boundary).

### Shared secret-store eligibility is not remote-path isolation

[External Secrets values](../system/external-secrets/values.yaml) declare a
shared `ClusterSecretStore` using Secret-backed AWS authentication and an
explicit namespace eligibility list. Upstream describes this cluster-scoped
store and its namespace conditions [5]. Those conditions decide where an
ExternalSecret may use the store; they do not map each eligible namespace to a
distinct allowed remote-secret path.

[Certificate credentials](../system/cert-manager/templates/secret.yaml),
[Longhorn credentials](../system/longhorn/templates/secret.yaml), and
[registry-helper credentials](../apps/opnsense-backup/ecr-token/secret.yaml)
are separate consumers of the shared store. The latter two request access-key
properties from the same remote configuration object. Separate destination
Secrets and namespaces do not prove separate AWS credentials or permissions.

If a subject can create or modify ExternalSecrets in an eligible namespace,
it could request other remote paths permitted by the store credentials unless
additional controls restrict those requests. Namespace eligibility alone does
not establish tenant isolation. Actual Kubernetes RBAC, admission controls,
controller configuration, and AWS authorization remain unverified.

### External provisioning and cluster bootstrap are separate credential flows

The [IAM user module](../external/modules/iam/user/v1/main.tf) declares a user,
policy, and attachment, but no access keys. The
[Secrets Manager module](../external/modules/secrets-manager/v1/main.tf)
declares containers without secret versions or payloads. Active and commented
calls in [the caller file](../external/sm.tf) must be distinguished; commented
calls do not establish provisioned destinations.

The [AWS provider/backend declaration](../external/main.tf) and
[cluster bootstrap](../system/bootstrap.yml) have separate credential inputs.
Bootstrap validates two operator-supplied environment inputs and creates the
initial Kubernetes credential Secret before rendering/applying External Secrets
and Argo CD. Its credential-creation task uses `no_log: true` and base64 encoding.
Suppressed task output limits that logging path; base64 is encoding, not
encryption, and neither establishes API-server encryption at rest [8].

External provisioning does not create or export the bootstrap credentials or
populate all remote values. Credential ownership, delivery, rotation, and
Secret storage protections are separate operator responsibilities, not outcomes
proven by these declarations. No credential identity or validity was tested.

### IAM breadth is visible in source, not attributable to runtime credentials

The active policies in [IAM source](../external/iam.tf) declare:

- A shared policy with read/describe access across several application and
  configuration secrets, including wildcard-suffixed remote-resource patterns;
  create/tag/write access on selected credential destinations; and list plus
  object read/write/delete access for database and volume backup storage.
- DNS record-list/change authority for the declared zone, broader than TXT-only
  challenges, plus discovery/change-status access and registry-token retrieval.
- A separate backup policy with bucket-list and object-write access to its
  declared backup target; it does not declare object-read/delete in that policy.
- An OIDC-associated policy with registry-token and service-bearer-token actions
  on wildcard resources and image-upload actions on selected public registries.
  The service-name condition shown for bearer-token retrieval is commented out.

The [OIDC module](../external/modules/iam/identity-provider/v1/main.tf) declares
audience and repository-subject trust conditions whose values are supplied as
inputs. Source therefore shows combined privilege breadth and trust conditions,
not an unrestricted trust policy or the effective runtime authorization chain.
A shared credential carrying the combined privileges could span secrets, DNS,
and backup integrity. These are policy declarations only: no supplied access
key, workload, or operator is identified as the principal using those policies,
and no effective permissions or live attachments were queried.

### Backup jobs have namespace-wide Secret RBAC

The [backup Role](../apps/opnsense-backup/role.yaml) permits `get` and `list` on
Secrets. The [registry-helper Role](../apps/opnsense-backup/ecr-token/role.yaml)
also permits `create`, `update`, and `delete`. Neither has a `resourceNames`
restriction. Their [backup binding](../apps/opnsense-backup/rolebinding.yaml)
and [helper binding](../apps/opnsense-backup/ecr-token/rolebinding.yaml) target
separate service accounts in the same namespace, and the respective
[backup job](../apps/opnsense-backup/cronjob.yaml) and
[helper job](../apps/opnsense-backup/ecr-token/cronjob.yaml) select those accounts.
All are included by [Kustomize](../apps/opnsense-backup/kustomization.yaml).

These are namespaced grants, not cluster-wide grants, but they cover all Secrets
in that namespace rather than only a named backup or image-pull Secret. Secret
listing can return Secret contents; helper write/delete authority can affect
other credentials there. Kubernetes documents RBAC resource-name restrictions
and their limitations, including restrictions on top-level creation [6], and
recommends least-privilege Secret access [8]. The risk is broader credential
access or modification if a job is misused; no such use was observed.

### Registry-helper output is a potential logging exposure

The [ECR helper job](../apps/opnsense-backup/ecr-token/cronjob.yaml) declares a
standalone authentication-token retrieval in its shell sequence whose output
is not captured or redirected, before a separate retrieval used to create an
image-pull Secret. Successful execution may place generated authentication
material in stdout and consequently container logs or a log collector.

This is a potential logging exposure visible in source, not proof that the job
ran, generated a token, or leaked a value. No token, exact command, or production
log is reproduced or inspected here. Kubernetes guidance explicitly warns
against logging Secret data after reading it [8].

### MQTT and Zigbee pairing are unverified operational exposure

[EMQX values](../platform/emqx/values.yaml) declare a LoadBalancer Service and
TLS for the dashboard ingress, but do not explicitly set MQTT listener TLS,
client authentication, or topic authorization. Missing local overrides do not
prove permissive chart defaults or anonymous access.
[Zigbee2MQTT values](../apps/zigbee2mqtt/values.yaml) declare an `mqtt://`
transport and `permit_join: true`.
[MeshCore values](../apps/meshcore-telemetry/values.yaml) explicitly disable MQTT
TLS. Dashboard HTTPS does not encrypt these MQTT client connections.

Plaintext transport can expose messages to parties able to observe that path;
a permit-join setting can allow device onboarding if effective and the relevant
pairing conditions are met. These are potential operational risks, not claims
of broker reachability, unauthorized clients, an active pairing window, or
unwanted devices. See [networking: MQTT wiring](networking.md#mqtt-wiring-plaintext-is-distinct-from-dashboard-tls).

### MeshCore declares container and pod hardening

[MeshCore values](../apps/meshcore-telemetry/values.yaml) disable privilege
escalation, set a read-only root filesystem, and drop all Linux capabilities at
container level. Pod settings require non-root execution with explicit user and
group IDs. Its Service is disabled. These reduce declared process privileges;
a disabled Service does not prevent outbound access or establish isolation.

The same file uses a mutable image tag and disables MQTT TLS. Hardening does not
establish image provenance, transport protection, successful non-root startup,
or namespace-wide policy enforcement. The
[chart dependency](../apps/meshcore-telemetry/Chart.yaml) is pinned, but rendered
security contexts and effective runtime restrictions were not inspected.

### Storage protections do not prove backup durability

[Longhorn values](../system/longhorn/values.yaml) declare retained storage and
an S3 backup target with Secret-backed credentials. Retained volumes and local
snapshots are not independent off-cluster recovery guarantees. The
[recurring-job template](../system/longhorn/templates/recurringjob-snapshot.yaml)
declares snapshot and backup tasks, but selection in values is commented out;
job declarations do not establish volume assignment, uploads, or restores.

The [S3 module](../external/modules/s3/v1/main.tf) and
[active callers](../external/s3.tf) declare default server-side encryption,
versioning, and public-access blocks. The module does not declare Object Lock,
replication, or lifecycle expiration. Logging is conditional and these callers
supply no logging target. The ACL input is not consumed by the module.

Encryption and public-access blocking do not protect against every authorized
write/delete operation or prove immutability. Versioning is not a tested restore
or an independent failure-domain guarantee; the declared shared IAM policy has
backup object-delete access. This does not establish deletion of retained
versions or any observed data loss. See [storage and backup declarations](storage.md)
for assignment, retention, recovery-input, and durability qualifications.

## Open questions and recommended operator verification

These are unresolved questions, not additional findings. In a separately
authorized review, operators can verify the following without recording secret
values or prescribing infrastructure changes here:

- GitOps: who can approve and merge source changes; what branch protections,
  artifact provenance checks, controller permissions, and deletion-review
  processes apply; whether rendered sync policies match intent.
- Ingress and DNS: effective client authentication, redirects, backend transport,
  network restrictions, certificate readiness, DNS credential scope and rotation;
  whether actual permissions are limited to intended zones and record types.
- Secret access: who can create ExternalSecrets in eligible namespaces; whether
  admission or provider controls restrict requested remote paths; effective
  Secret RBAC, encryption at rest, and credential ownership/delivery/rotation.
  Confirm provider/bootstrap separation without attributing policies to keys.
- IAM: effective policy attachments and additional grants, OIDC input constraints,
  and actual permissions associated with each credential flow. Declarations
  alone do not establish that bootstrap, DNS, backup, and registry credentials
  are distinct principals or share a principal.
- Backup jobs and logs: effective namespace Secret permissions, whether the helper
  ran successfully, and whether stdout is collected, retained, redacted, or
  accessible beyond intended readers. Review handling without copying tokens
  into documentation, terminals, issues, or audit reports.
- MQTT and Zigbee: effective listeners, network reachability, client credentials,
  topic ACLs, transport modes, and the active permit-join window. Do not infer
  anonymous access or ongoing pairing from these values alone.
- MeshCore: rendered and admitted security contexts, effective image identity,
  non-root startup, writable-path requirements, and surrounding isolation.
- Durability: actual volume job assignments, backup completion and integrity,
  object/version retention, credential access, failure-domain placement, and a
  separately authorized recovery test. Local documentation validation cannot
  establish backup health or recovery objectives.

## Sources

[2] [cert-manager Route53 DNS-01](https://cert-manager.io/docs/configuration/acme/dns01/route53)
[5] [External Secrets ClusterSecretStore v0.14.2](https://external-secrets.io/v0.14.2/api/clustersecretstore)
[6] [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac)
[8] [Kubernetes Secret Good Practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices)
