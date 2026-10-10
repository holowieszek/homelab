# Networking reference

Source snapshot: `d6ba04de243fdb722145dc556bfc28a32965ca61`.

## Scope and evidence

This guide describes checked-in network declarations, not a comprehensive
runtime assessment. A separate [read-only K3s inventory](kubernetes-audit.md)
recorded version `v1.31.6+k3s1` and zero standard NetworkPolicy objects on
2026-10-10; it did not identify the active CNI or inspect traffic, host
firewalls, listeners, routes, or AWS resources. The K3s installer remains
unpinned in source. Addresses, domains, hostnames, cloud resource names, and
credential identifiers are deliberately omitted. Links point only to safe
relative repository paths; upstream references use the assigned source ledger.

Start with the [repository overview](../README.md) and
[documentation index](index.md). Resolve runtime questions only through a
separately authorized operator review, not by running provisioning targets.

## K3s bundled networking: qualified defaults

The [K3s role](../bare/roles/k3s/tasks/main.yml) downloads the installer without a
version pin and invokes the server installation without explicit networking
flags. Workers use the configured control-plane endpoint on HTTPS port `6443`.
This role does not establish the effective server configuration or installed
component versions; settings outside the inspected source may change behavior.

- Upstream K3s documents bundled CoreDNS, Traefik, ServiceLB, and an embedded
  network-policy controller [1]. Flannel with a VXLAN backend is the upstream
  default described by its networking options [9], not a repository-pinned
  choice or evidence of encrypted pod traffic.
- Under the documented default, Traefik uses a LoadBalancer Service on ports
  `80` and `443`; ServiceLB can consume those host ports across eligible nodes
  [1]. Do not infer an external load-balancer appliance, actual listening nodes,
  firewall reachability, or Internet exposure from a Service type alone.
- A bundled network-policy controller is not itself an isolation policy. Verify
  effective policies and traffic restrictions independently; no enforcement
  behavior was tested here.

## Ingress and TLS declaration boundaries

[Argo CD ingress](../system/argocd/templates/ingress.yaml),
[Longhorn ingress](../system/longhorn/templates/ingress.yaml),
[Grafana ingress](../platform/grafana/templates/ingress.yaml), and application
values such as [ESPHome](../apps/esphome/values.yaml) and
[Memos](../apps/memos/values.yaml) select Traefik, annotate a cluster-wide
certificate issuer, and declare TLS hosts and namespace-local certificate
Secrets. These express intended HTTPS routing, not successful certificate
issuance, DNS resolution, authentication, or network access controls.

The explicit ingress templates route to backend service port `80`; the cited
application values declare HTTP backend ports. In addition,
[Argo CD values](../system/argocd/values.yaml) enable insecure server mode. This
is consistent with TLS termination at ingress, not proof of end-to-end TLS from
clients to pods. Redirect behavior and backend transport must be checked in the
rendered and running controller configuration.

[Home Assistant values](../apps/home-assistant/values.yaml) trust a configured
proxy CIDR. Verify that only intended proxies can reach that trust boundary;
the declaration does not establish the actual pod network or source addresses.

## ACME DNS-01 and Route 53 credential trust boundary

The [cert-manager chart](../system/cert-manager/Chart.yaml) pins its dependency;
[the issuer template](../system/cert-manager/templates/clusterissuer.yaml)
declares the production ACME endpoint, DNS-01 through Route 53, and DNS-zone
selectors. DNS-01 validates DNS control through challenge records [2]; it does
not require inbound HTTP access to the workload or establish that an ingress is
reachable. A selector chooses a solver, not an AWS authorization boundary.

The [ExternalSecret template](../system/cert-manager/templates/secret.yaml)
declares retrieval of both access-key components from AWS Secrets Manager into
a Kubernetes Secret in the certificate-controller namespace. The
[cluster secret store](../system/external-secrets/values.yaml) uses separate
Secret-backed AWS authentication seeded by
[bootstrap](../system/bootstrap.yml). The trust chain is operator-supplied
bootstrap credentials, External Secrets access to remote values, Kubernetes
Secret access, and cert-manager authority to change DNS. These are declarations,
not proof that values exist, synchronize, rotate, or belong to a particular IAM
principal.

[The IAM configuration](../external/iam.tf) declares a shared policy with
zone-scoped record changes plus zone discovery and change-status access; the
record-change statement has no TXT-only condition. The issuer does not specify
a hosted-zone ID. Review least privilege and credential rotation against [2],
but do not assume the supplied issuer credentials use that declared policy.
[Route 53 provisioning](../external/r53.tf) declares a hosted zone, not verified
zone delegation or workload address records.

## MQTT wiring: plaintext is distinct from dashboard TLS

- [EMQX values](../platform/emqx/values.yaml) declare three replicas, a
  LoadBalancer Service, and a Traefik dashboard ingress with certificate/TLS
  settings. Dashboard HTTPS does not configure MQTT transport encryption.
  [Its chart](../platform/emqx/Chart.yaml) pins the dependency, while listener
  ports, MQTT TLS, authentication, and authorization are not explicitly set in
  these local values; review chart defaults and effective broker configuration.
- [Zigbee2MQTT values](../apps/zigbee2mqtt/values.yaml) use an `mqtt://` broker
  URL, a plaintext transport declaration. Its serial coordinator uses a
  separate TCP connection on port `6638`, not the MQTT ingress.
- [Telemetry values](../apps/meshcore-telemetry/values.yaml) point to the same
  configured broker host on port `1883`, explicitly disable MQTT TLS, and
  subscribe to the configured telemetry topic. Its Kubernetes Service is
  disabled, consistent with an outbound subscriber. These settings do not
  establish successful connections, actual broker listeners, or topic ACLs.
  The chart dependency is pinned in [the EMQX chart](../platform/emqx/Chart.yaml);
  the official project source is [13]. Treat documentation for a different
  release as contextual, not proof of the behavior of this pin.

## CoreDNS customization and import uncertainty

The [forwarding manifest](../system/coredns/upstream-dns.yaml) declares the
`coredns-custom` ConfigMap explicitly in `kube-system`. Its `custom.server`
block forwards the configured internal zone to a private DNS upstream, using
DNS port `53`. The [public ApplicationSet](../system/argocd/values.yaml) discovers
this raw-manifest directory under `system/*`; its directory-derived destination
namespace does not override the explicit manifest namespace.

The manifest does not show the effective CoreDNS Corefile, a volume mount, or
an import of this custom block. Bundled CoreDNS defaults [1] do not prove this
customization is loaded. Verify imports, upstream reachability, and resolution
behavior separately; do not conflate this private forwarding path with Route 53
ACME validation.

## PXE DHCP and provisioning-network exposure

The [PXE Compose file](../bare/roles/pxe_server/files/docker-compose.yml) gives
dnsmasq host networking and `NET_ADMIN`; the
[dnsmasq template](../bare/roles/pxe_server/templates/dnsmasq.conf.j2) disables
DNS serving (`port=0`) but enables lease-serving DHCP, a router option, DHCP
logging, and TFTP/UEFI boot. This is not proxy-DHCP. The template does not bind a
specific interface; existing DHCP servers and unintended network interfaces
must be reviewed before starting it.

The HTTP container publishes host port `8080` for ISO and cloud-init downloads,
without an explicit host-address restriction in Compose. Neither HTTP nor TFTP
is a TLS-protected delivery declaration. Limit provisioning-network access and
check host firewall/bindings; no listening sockets or exposure were inspected.
See the [PXE provisioning reference](provisioning-reference.md#pxe-network-and-iso-behavior)
for lifecycle details, the disabled ISO checksum check, and boot-URL coupling.

## Open runtime questions

- Which CNI/backend and bundled controllers are active, and which nodes/ports
  does ServiceLB expose? The 2026-10-10 inventory reported `v1.31.6+k3s1` and
  no standard NetworkPolicy objects. Confirm whether that absence is intended
  and whether other network-isolation controls are active; the inventory does
  not answer either question.
- Do ingress classes, DNS records, redirects, certificate readiness, backend
  transport, and application/proxy access controls match the intended boundary?
- Are DNS-01 challenge records publicly resolvable, and do the actual issuer
  credentials have the intended zone-scoped permissions and rotation process?
- Which MQTT listeners, authentication rules, topic ACLs, and transport modes
  are effective? Can plaintext clients be restricted or migrated to TLS?
- Does CoreDNS import the custom block, and is the private upstream reachable?
  Is PXE isolated from normal DHCP and are provisioning downloads restricted?

## Sources

[1] [K3s Networking Services](https://docs.k3s.io/networking/networking-services)
[2] [cert-manager Route53 DNS-01](https://cert-manager.io/docs/configuration/acme/dns01/route53)
[9] [K3s Basic Network Options](https://docs.k3s.io/networking/basic-network-options)
[13] [EMQX source repository](https://github.com/emqx/emqx)
