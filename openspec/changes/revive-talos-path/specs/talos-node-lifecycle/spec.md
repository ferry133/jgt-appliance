## ADDED Requirements

### Requirement: Configuration can be reapplied to a single node

Day-two changes must be applicable per node, not only by rebuilding the cluster. Applying configuration to one node SHALL be a supported operation that names the node explicitly.

#### Scenario: Apply targets one node
- **WHEN** an operator applies configuration naming a single node
- **THEN** only that node's configuration is applied

#### Scenario: Target must exist and be reachable
- **WHEN** the named node is unreachable or has no machine configuration
- **THEN** the operation fails before attempting to apply, with the reason stated

#### Scenario: Node identity is mandatory
- **WHEN** an apply operation is invoked without naming a node
- **THEN** it fails rather than defaulting to all nodes

### Requirement: Talos can be upgraded one node at a time

Upgrading a node SHALL use the image and version that node's own configuration declares, so that a node is never upgraded to a version its configuration does not describe.

#### Scenario: Upgrade uses the node's declared image
- **WHEN** a node is upgraded
- **THEN** the image and version come from that node's own declared configuration

#### Scenario: Upgrade targets one node
- **WHEN** an upgrade is invoked
- **THEN** it names exactly one node, and other nodes are untouched

### Requirement: Kubernetes can be upgraded independently of Talos

The Kubernetes version SHALL be upgradable as its own operation, using the version declared in configuration.

#### Scenario: Kubernetes upgrade uses declared version
- **WHEN** the Kubernetes upgrade operation runs
- **THEN** it upgrades to the version declared in configuration, not to a version supplied ad hoc

### Requirement: Reset is destructive and gated

Resetting returns nodes to maintenance mode and destroys the cluster. It SHALL require explicit confirmation before proceeding.

#### Scenario: Reset requires confirmation
- **WHEN** the reset operation is invoked
- **THEN** it states that the cluster will be destroyed and does not proceed without confirmation

#### Scenario: Reset returns nodes to maintenance mode
- **WHEN** reset completes
- **THEN** the nodes are in maintenance mode and can be provisioned again from scratch

### Requirement: Lifecycle operations verify their prerequisites

Each operation SHALL check that the tools, configuration, and credentials it needs are present before acting, so that a missing prerequisite fails immediately rather than midway through a cluster mutation.

#### Scenario: Missing prerequisite fails fast
- **WHEN** a lifecycle operation is invoked without a required tool, configuration file, or credential
- **THEN** it fails before making any change, naming what is missing
