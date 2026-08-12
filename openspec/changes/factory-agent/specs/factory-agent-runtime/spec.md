## ADDED Requirements

### Requirement: Factory agent runs isolated from other agents

The factory agent SHALL run in its own namespace with its own ServiceAccount. It MUST NOT share the ServiceAccount that `claudecode/claude-code` binds to `cluster-admin` for all its instances, because that would expose the factory's cross-system credentials to every other agent instance on the same cluster.

#### Scenario: Separate namespace and service account
- **WHEN** the factory agent is deployed
- **THEN** it runs in a namespace of its own and uses a ServiceAccount distinct from the shared claude-code ServiceAccount

#### Scenario: Peer agent cannot read factory credentials
- **WHEN** a `claudecode/claude-code` instance on the same cluster attempts to read the factory agent's secrets
- **THEN** the request is denied by RBAC

#### Scenario: Factory holds no standing cluster-admin on its host cluster
- **WHEN** the factory agent's permissions on its host cluster are enumerated
- **THEN** they are limited to what provisioning requires, and do not include `cluster-admin` on the host cluster

### Requirement: Factory agent reaches Omni over in-cluster networking

Omni runs in the same cluster as the factory agent. The agent SHALL reach it by in-cluster Service address. It MUST NOT depend on a port-forward, and MUST NOT route Omni gRPC through a Cloudflare Tunnel, which breaks gRPC trailers that the Talos proxy's streaming calls depend on.

#### Scenario: Direct in-cluster access
- **WHEN** the factory agent issues an Omni API call
- **THEN** the call is made to the Omni Service's in-cluster address, with no port-forward and no tunnel hop

#### Scenario: Streaming calls succeed
- **WHEN** the factory agent performs an Omni operation that uses gRPC streaming
- **THEN** the call completes without a "server closed the stream without sending trailers" error

### Requirement: Factory credentials are enumerated and scoped

The factory agent holds the highest-privilege credential set in the system: Omni administrative access, a GitHub token able to create and transfer repositories, and a Cloudflare account token. Each credential SHALL be documented with its scope and its blast radius, and each SHALL be scoped to the minimum that provisioning requires.

#### Scenario: Credential inventory exists
- **WHEN** the factory agent's configuration is reviewed
- **THEN** every credential it holds is listed with its purpose, its scope, and what an attacker could do with it

#### Scenario: Credentials are not embedded in the image
- **WHEN** the factory agent's container image is inspected
- **THEN** it contains no credential material; all credentials are supplied at runtime

### Requirement: Factory agent has the provisioning toolchain available

The agent SHALL have available every CLI the provisioning workflow invokes, at the versions this repository pins.

#### Scenario: Toolchain present
- **WHEN** the factory agent starts
- **THEN** `omnictl`, `gh`, `cloudflared`, `age`, `sops`, `cue`, `makejinja`, `task`, `kubectl`, and `helmfile` are all present and runnable

#### Scenario: Version drift is visible
- **WHEN** a pinned tool version in the repository changes
- **THEN** the factory agent's toolchain is rebuilt to match, and a mismatch is detectable rather than silent

### Requirement: Factory agent is reachable by its operator

The agent SHALL be reachable at a stable hostname with authenticated access, so that an operator can inspect and intervene in a provisioning run.

#### Scenario: Operator access is authenticated
- **WHEN** an operator opens the factory agent's hostname
- **THEN** access requires authentication and only permitted identities may log in

#### Scenario: Customer identities cannot reach the factory
- **WHEN** a customer identity permitted on a customer cluster's resident agent attempts to log in to the factory agent
- **THEN** access is denied
