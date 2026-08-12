## ADDED Requirements

### Requirement: Only LAN-reachable services consume LAN addresses

Services that no LAN client ever connects to SHALL NOT consume an address from the customer's LAN subnet, and SHALL NOT be of type LoadBalancer at all where a ClusterIP suffices. `cloudflared` reaches the external gateway by in-cluster DNS name, not by its LoadBalancer address, so under the `appliance` profile `envoy-external` SHALL be a ClusterIP Service and `cloudflare_gateway_addr` SHALL NOT exist. `cluster_api_addr` is reached through the Omni proxy and SHALL NOT consume a LAN address under the `appliance` profile.

#### Scenario: External gateway consumes no address
- **WHEN** an appliance cluster is rendered and reconciled
- **THEN** `envoy-external` has no LoadBalancer address, `cloudflared` still reaches it by its in-cluster DNS name, and public ingress works

#### Scenario: Operator override retained
- **WHEN** a `full` profile cluster explicitly sets `cluster_api_addr` or `cloudflare_gateway_addr` in `cluster.yaml`
- **THEN** the explicit values are used and today's LoadBalancer behaviour is preserved unchanged

### Requirement: LAN-facing services share a single address

`envoy-internal`, `mqtt`, and (when enabled) `k8s-gateway` SHALL share one LAN address. Their listening ports do not overlap (80/443 TCP, 1883 TCP, 53 UDP+TCP), so a single address serves all three. The number of LAN addresses an appliance consumes SHALL be exactly one.

#### Scenario: One address serves all LAN-facing services
- **WHEN** an appliance cluster is reconciled with `envoy-internal` and `mqtt` deployed
- **THEN** both Services report the same `status.loadBalancer.ingress[0].ip`

#### Scenario: Sharing annotations are present on every participating service
- **WHEN** any one of the sharing services is missing `lbipam.cilium.io/sharing-cross-namespace`
- **THEN** that service receives no address and reports `cilium.io/IPAMRequestSatisfied=False` with reason `already_allocated_incompatible_service`, while the other services keep theirs

#### Scenario: Port collision surfaces as an unsatisfied condition
- **WHEN** a service requesting the shared address declares a port already claimed on that address
- **THEN** that service receives no address and reports `cilium.io/IPAMRequestSatisfied=False` with reason `already_allocated_incompatible_service`, rather than being assigned a second LAN address

### Requirement: The address pool contains only deliberately allocated addresses

The `CiliumLoadBalancerIPPool` SHALL contain only the addresses this cluster has deliberately claimed. A pool spanning the whole node CIDR lets any Service that omits an address annotation draw an arbitrary address from the customer's LAN, and it also lets a port collision silently consume a second address instead of reporting failure. Constraining the pool is what makes both failures observable.

#### Scenario: Pool is narrow
- **WHEN** an appliance cluster's LB-IPAM pool is inspected
- **THEN** its blocks contain only the discovered address(es), not the node CIDR

#### Scenario: Unannotated service cannot take a LAN address
- **WHEN** a Service of type LoadBalancer is created without an address annotation and no pool address is free
- **THEN** it receives no address and reports an unsatisfied IPAM condition, rather than being assigned an arbitrary address from the customer's LAN

### Requirement: LAN address is discovered, not configured

For the `appliance` profile the LAN address SHALL be obtained automatically and MUST NOT be a `cluster.yaml` field. The discovery component SHALL emit its result as a `CiliumLoadBalancerIPPool` resource.

#### Scenario: Address discovered on first reconcile
- **WHEN** an appliance cluster reconciles for the first time on an unknown LAN
- **THEN** a `CiliumLoadBalancerIPPool` containing exactly one address within the node's own subnet is created, and LAN-facing Services bind to it

#### Scenario: Discovery result is stable across restarts
- **WHEN** the discovery component restarts
- **THEN** it reproduces the same address rather than selecting a new one, and existing Service assignments are unchanged

### Requirement: Allocation mechanism is replaceable behind the pool interface

The initial implementation SHALL discover a free address by ARP probing the node's subnet. Its only contract with the rest of the system is the emitted `CiliumLoadBalancerIPPool`. A later DHCP lease-holder implementation MUST be substitutable without changes to Cilium configuration, Service annotations, templates, or CUE schema.

#### Scenario: Probe implementation emits the contract
- **WHEN** the ARP-probe implementation completes discovery
- **THEN** its sole cluster-visible output is a `CiliumLoadBalancerIPPool`, with no Service or HelmRelease field carrying the discovered address

#### Scenario: Swap does not ripple
- **WHEN** the probe implementation is replaced by a DHCP lease-holder that emits the same pool
- **THEN** no template, CUE field, or `jg-base` manifest outside the discovery component requires modification

### Requirement: Address conflicts are detected and reported

The discovery component SHALL continue to monitor the chosen address after assignment. An ARP-probed address can later collide with a device that was powered off at probe time; this MUST surface as an operator-visible signal rather than as unexplained LAN service failures.

#### Scenario: Post-assignment collision detected
- **WHEN** another host on the LAN begins answering ARP for the assigned address
- **THEN** the conflict is recorded in the daily health report and raised to the operator

#### Scenario: Conflict triggers re-selection
- **WHEN** a collision is confirmed
- **THEN** a new free address is selected, the pool is updated, and the change is logged with both the old and new address
