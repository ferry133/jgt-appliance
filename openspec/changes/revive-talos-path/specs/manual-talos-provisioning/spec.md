## ADDED Requirements

### Requirement: Nodes are declared in a dedicated configuration file

The manual path requires per-node facts that cannot be discovered remotely. These SHALL be declared in a node configuration file separate from the cluster configuration file, and that file SHALL be a declared input to template rendering.

#### Scenario: Node file is rendered as data
- **WHEN** templates are rendered
- **THEN** the node configuration file is among the declared data sources, and node values are available to templates

#### Scenario: Sample file guides the reader
- **WHEN** a user initialises a new repository
- **THEN** a commented sample node file exists showing every field, which are required, and how to obtain each value

#### Scenario: Node file is never committed
- **WHEN** the repository is inspected after configuration
- **THEN** the filled-in node file is ignored by version control

### Requirement: Node declarations are validated before rendering

Node values that are wrong produce a cluster that fails to boot, with slow and confusing symptoms. They SHALL be validated by schema before any file is rendered.

#### Scenario: Required node fields enforced
- **WHEN** a node entry omits its name, address, controller flag, disk, MAC address, or image schematic
- **THEN** validation fails naming the missing field, and nothing is rendered

#### Scenario: Field formats enforced
- **WHEN** a node's MAC address, image schematic, or name does not match its required format
- **THEN** validation fails identifying the malformed field

#### Scenario: Duplicate node identities rejected
- **WHEN** two nodes share a name, an address, or a MAC address
- **THEN** validation fails identifying the collision

#### Scenario: Reserved names rejected
- **WHEN** a node is named using a value reserved by the configuration format
- **THEN** validation fails

### Requirement: Rendered Talos configuration matches the cluster's expectations

The cluster installs its own CNI, DNS, and service proxy from the shared manifests. The rendered Talos configuration SHALL disable the built-in equivalents, so that a manually provisioned cluster is indistinguishable from an Omni-provisioned one once running.

#### Scenario: Built-in networking components disabled
- **WHEN** Talos configuration is generated
- **THEN** the built-in CNI, the built-in DNS, and the built-in service proxy are all disabled

#### Scenario: Both paths converge on the same cluster shape
- **WHEN** a manually provisioned cluster and an Omni-provisioned cluster are compared after bootstrap
- **THEN** both run the same networking components from the shared manifests

### Requirement: Cluster bootstrap is a single documented command

Bringing up a manually provisioned cluster SHALL be one command that generates secrets if absent, generates configuration, applies it to the nodes, bootstraps the control plane, and retrieves a kubeconfig.

#### Scenario: Bootstrap runs end to end
- **WHEN** the bootstrap command is run against nodes in maintenance mode
- **THEN** it completes with a working kubeconfig, without further manual steps

#### Scenario: Secrets generated once and encrypted
- **WHEN** bootstrap runs and no cluster secret file exists
- **THEN** one is generated and written encrypted, and a later run reuses it rather than regenerating

#### Scenario: Bootstrap is retryable
- **WHEN** bootstrap is interrupted and re-run
- **THEN** it converges without requiring the cluster to be reset first, for the steps that are inherently retryable

### Requirement: The manual path requires the API endpoint address

A manually provisioned cluster reaches its control plane through an address declared in configuration, not through a management proxy. That address SHALL be required whenever the manual path is used.

#### Scenario: Endpoint address required for manual path
- **WHEN** the manual path is used without a declared control plane API address
- **THEN** validation fails naming the missing address

#### Scenario: Omni path does not require it
- **WHEN** the Omni path is used
- **THEN** the manual path's endpoint requirement does not apply
