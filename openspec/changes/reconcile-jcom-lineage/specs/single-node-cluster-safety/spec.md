## ADDED Requirements

### Requirement: Components that cannot work on one node are gated by configuration

Some components are meaningless or actively harmful on a single-node cluster. These SHALL be enabled or disabled by configuration derived from the cluster's shape, not deployed unconditionally and patched away afterwards per cluster.

#### Scenario: Single-node cluster omits the component
- **WHEN** a cluster has one node
- **THEN** components that require more than one node are not deployed at all

#### Scenario: Multi-node cluster is unaffected
- **WHEN** a cluster has more than one node
- **THEN** those components are deployed as they are today

#### Scenario: No per-cluster patch is required
- **WHEN** a single-node cluster is provisioned
- **THEN** it needs no cluster-specific patch to avoid the component

### Requirement: A failing component must not degrade unrelated workloads

A component that fails on an unsupported topology SHALL fail in isolation. The known case is a peer-to-peer image mirror that, on a single node, never became ready and left behind host configuration redirecting every container registry to dead local ports — after which no uncached image could be pulled anywhere on the cluster.

#### Scenario: Failure stays contained
- **WHEN** a component fails to become ready
- **THEN** workloads that do not depend on it continue to function

#### Scenario: Host-level side effects are reverted
- **WHEN** a component that writes node-level configuration fails or is removed
- **THEN** the configuration it wrote is reverted, rather than left redirecting traffic to a dead endpoint

#### Scenario: Registry access survives the component
- **WHEN** an image-mirroring component is absent, failed, or disabled
- **THEN** images can still be pulled from their original registries

### Requirement: Node count is known to the configuration that gates components

Gating requires the rendered configuration to know how many nodes the cluster has. This SHALL come from declared configuration rather than being inferred at runtime, so the decision is visible before anything is deployed.

#### Scenario: Node count available at render time
- **WHEN** configuration is rendered
- **THEN** whether the cluster is single-node is determinable from declared configuration

#### Scenario: Gating decision is inspectable
- **WHEN** rendered output is reviewed
- **THEN** it is visible which components were gated out and why

### Requirement: The single-node case is exercised, not assumed

Single-node is the shape a zero-input appliance ships in, so it SHALL be a tested configuration rather than an edge case discovered in production.

#### Scenario: Single-node deployment verified
- **WHEN** a single-node cluster is provisioned from the shared configuration
- **THEN** it reaches a working state with no cluster-specific intervention

#### Scenario: Regression is detectable
- **WHEN** a change would deploy a multi-node-only component to a single-node cluster
- **THEN** that is caught before the cluster is affected
