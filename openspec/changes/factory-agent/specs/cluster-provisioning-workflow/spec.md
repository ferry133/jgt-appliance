## ADDED Requirements

### Requirement: Provisioning begins when a machine registers itself

The customer's only physical actions are unboxing, connecting ethernet, and powering on. The machine registers itself with Omni over SideroLink; the factory agent SHALL take that registration as the trigger to begin provisioning. No LAN scan, no IP entry, and no on-site network configuration is required.

#### Scenario: Registration starts a run
- **WHEN** a machine matching an open provisioning work order registers with Omni
- **THEN** the factory agent begins the provisioning workflow for that work order

#### Scenario: Unexpected machine does not auto-provision
- **WHEN** a machine registers with Omni and no open work order matches it
- **THEN** no cluster is created, and the machine is reported to the operator for triage

### Requirement: Provisioning runs end to end without human input

For a cluster whose profile requires no customer-supplied fields, the workflow SHALL complete every step without prompting: create the Omni cluster, create the user repository from the template, derive `cluster.yaml`, run `task configure`, commit and push, obtain a kubeconfig, run `task bootstrap:apps`, and wait for Flux and the resident agent to become ready.

#### Scenario: Unattended completion
- **WHEN** provisioning starts for an appliance work order
- **THEN** it reaches the ready state with no human input at any step

#### Scenario: Derived values come from observed state
- **WHEN** the workflow derives network values for `cluster.yaml`
- **THEN** they are derived from the machine's own observed network state as reported through Omni, not from operator input

### Requirement: Every step is idempotent

The workflow spans four external systems and takes tens of minutes; interruption is expected. Re-running any step SHALL converge rather than duplicate. A second run MUST NOT create a second tunnel, a second repository, or a second cluster.

#### Scenario: Re-run creates no duplicates
- **WHEN** the workflow is re-run after an interruption
- **THEN** external resources that already exist are detected and reused, and no duplicate is created

#### Scenario: Partial step is completed, not repeated blindly
- **WHEN** a step was interrupted after creating an external resource but before recording it
- **THEN** the re-run discovers the existing resource by a deterministic name or tag and adopts it

### Requirement: Provisioning resumes from recorded state

A resumed run SHALL determine where it stopped from durable recorded state, not from operator memory.

#### Scenario: Resume after agent restart
- **WHEN** the factory agent restarts mid-run
- **THEN** it reads the work order's recorded stage and continues from that stage

#### Scenario: Resume is explicit about what it skips
- **WHEN** a run resumes
- **THEN** it records which stages it skipped as already complete

### Requirement: Provisioning is complete only when the resident agent is reachable

The run SHALL NOT be marked complete until Flux has reconciled and the customer cluster's resident agent is reachable at its hostname. Reaching that point is the handoff from the factory agent to the resident agent.

#### Scenario: Completion requires resident agent
- **WHEN** Flux reconciliation succeeds but the resident agent is not yet reachable
- **THEN** the run remains in progress

#### Scenario: Handoff is recorded
- **WHEN** the resident agent becomes reachable
- **THEN** the work order records the handoff, and the factory agent stops acting on that cluster except when explicitly re-engaged

### Requirement: Known failure modes are remediated automatically

Failures with a documented remedy SHALL be detected and remediated by the agent rather than escalated. Where an ISP blocks the QUIC transport, the tunnel enters CrashLoopBackOff with handshake timeouts; the documented remedy is to force the HTTP/2 transport.

#### Scenario: QUIC blockage remediated
- **WHEN** the tunnel workload fails with repeated QUIC handshake timeouts
- **THEN** the agent applies the documented transport workaround, verifies the workload becomes healthy, and records what it did

#### Scenario: Unknown failure escalates instead of retrying
- **WHEN** a failure has no documented remedy
- **THEN** the agent stops, records the diagnostic evidence on the work order, and escalates rather than retrying indefinitely

### Requirement: Loss of machine visibility is reported as such

All remote visibility depends on the machine reaching Omni. When it does not, the agent cannot distinguish "not powered", "not cabled", "blocked egress", and "wrong boot device". It SHALL report the ambiguity honestly rather than asserting a cause.

#### Scenario: Absence reported without a guessed cause
- **WHEN** an expected machine has not registered within the expected window
- **THEN** the work order records that the machine is not visible and enumerates the possible causes, without asserting one

#### Scenario: Escalation carries the on-site checklist
- **WHEN** machine visibility is lost
- **THEN** the escalation includes the on-site checks a non-technical person can perform
