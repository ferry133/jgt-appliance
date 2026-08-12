## ADDED Requirements

### Requirement: Internal service hostnames stay flat

A service's internal-versus-external nature SHALL be expressed solely by its HTTPRoute `parentRefs` (`envoy-internal` or `envoy-external`). Hostnames MUST NOT encode that distinction — no `.lan.` or equivalent infix. Moving a service between gateways SHALL remain a one-line `parentRefs` edit that changes no hostname, certificate SAN, OAuth callback URL, or client configuration.

#### Scenario: Internal route keeps the flat hostname
- **WHEN** an HTTPRoute attaches to `envoy-internal` with hostname `pbx.${SECRET_DOMAIN}`
- **THEN** the published record is for `pbx.${SECRET_DOMAIN}` with no additional label

#### Scenario: Gateway move is non-breaking
- **WHEN** a route's `parentRefs` changes from `envoy-internal` to `envoy-external`
- **THEN** its hostname is unchanged, and no client, certificate, or Auth0 callback registration requires updating

### Requirement: Internal routes are published as unproxied A records

A second external-dns instance SHALL publish HTTPRoutes attached to `envoy-internal` as A records pointing at the shared LAN address. These records MUST be DNS-only; Cloudflare cannot proxy an RFC1918 destination, so a proxied record would blackhole the service.

#### Scenario: Internal route yields a DNS-only A record
- **WHEN** an HTTPRoute attaches to `envoy-internal` and reconciles
- **THEN** an A record for its hostname is created pointing at the shared LAN address with proxying disabled

#### Scenario: LAN client resolves without a local resolver
- **WHEN** a LAN client using its router-supplied DNS resolves an internal service hostname
- **THEN** it receives the shared LAN address and connects directly, with no `k8s-gateway` involved

#### Scenario: External routes unaffected
- **WHEN** an HTTPRoute attaches to `envoy-external`
- **THEN** it is published by the existing external-dns instance as a proxied record, exactly as today

### Requirement: The two external-dns instances own disjoint record sets

Both instances run `policy: sync` against the same Cloudflare zone. They SHALL use distinct `txtPrefix` and distinct `txtOwnerId` values so that neither treats the other's records as orphaned and deletes them.

#### Scenario: Ownership records are distinct
- **WHEN** both instances have reconciled
- **THEN** the zone contains two disjoint sets of TXT ownership records, each carrying its own owner ID and prefix

#### Scenario: Neither instance prunes the other's records
- **WHEN** the internal instance runs a full sync
- **THEN** records owned by the external instance remain present and unmodified, and vice versa

### Requirement: k8s-gateway is a conditional fallback

`k8s-gateway` SHALL NOT be deployed by default under the `appliance` profile. It SHALL be enabled only when the public-A-record path is proven not to work on the customer's network.

#### Scenario: Default appliance omits k8s-gateway
- **WHEN** an appliance cluster reconciles with public A records resolving correctly from the LAN
- **THEN** no `k8s-gateway` workload is deployed and no LAN address is consumed by it

#### Scenario: Rebinding protection triggers fallback
- **WHEN** a post-bootstrap check resolves an internal hostname from inside the LAN and the RFC1918 answer is filtered or rewritten
- **THEN** the result is recorded as DNS rebinding protection detected, and the operator is prompted to enable `k8s-gateway`

#### Scenario: Fallback changes no hostname
- **WHEN** `k8s-gateway` is enabled after a rebinding-protection detection
- **THEN** it answers for the same flat hostnames with the same LAN address, and no client configuration changes

### Requirement: Publishing internal hostnames introduces no new disclosure

Publishing an internal hostname to public DNS SHALL be treated as disclosing no information beyond what certificate issuance already discloses, because cert-manager records every issued hostname in Certificate Transparency logs. Records MUST resolve to RFC1918 addresses only, so the named services stay unreachable from outside the LAN.

#### Scenario: Internal record is unreachable externally
- **WHEN** a host outside the customer's LAN resolves an internal service hostname
- **THEN** it receives an RFC1918 address and cannot establish a connection

#### Scenario: No public routing path is created
- **WHEN** internal records are published
- **THEN** no Cloudflare Tunnel ingress rule or public route is created for those hostnames
