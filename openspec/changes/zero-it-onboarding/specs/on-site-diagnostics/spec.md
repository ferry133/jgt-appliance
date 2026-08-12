## ADDED Requirements

### Requirement: The diagnostic questions requiring an on-site vantage point are enumerated

When a machine does not reach the management plane, the operator cannot distinguish the possible causes remotely. The set of questions that can only be answered from inside the customer's network SHALL be enumerated explicitly, so that each one has an identified answering mechanism.

#### Scenario: Question set is documented
- **WHEN** the diagnostic design is reviewed
- **THEN** every question that cannot be answered from the operator side is listed, each with the mechanism that answers it

#### Scenario: Each question has an owner mechanism
- **WHEN** a new on-site question is identified
- **THEN** it is added to the set together with whether it is answered by observation, by photograph, or by an automated probe

### Requirement: Observable and photographic answers are available first

Questions answerable by what the customer can see SHALL be answered that way, without requiring any software beyond the messaging channel.

#### Scenario: Power and cabling established by observation
- **WHEN** it is unknown whether the machine is powered or cabled
- **THEN** the customer is asked to observe indicator lights and cable seating, and their answer resolves the question

#### Scenario: Boot state established by photograph
- **WHEN** it is unknown whether the machine booted correctly
- **THEN** the customer is asked to photograph the relevant indicator or display, and the image resolves the question

### Requirement: Questions requiring network probing are identified as deferred

Some questions cannot be answered by observation: whether an address is reachable on the local network, and whether the network permits the outbound traffic the machine needs. These SHALL be recorded as requiring an automated on-site probe, and SHALL be explicitly deferred rather than silently unanswered.

#### Scenario: Probe-only questions marked deferred
- **WHEN** a question requires probing the local network
- **THEN** it is recorded as deferred to the probe capability, and the operator knows it is currently unanswerable

#### Scenario: Deferred questions escalate to a human
- **WHEN** a deferred question blocks a provisioning run
- **THEN** the run escalates to a human rather than guessing

### Requirement: The rebinding-protection check is answered from the customer's vantage point

Whether the customer's network filters public DNS answers pointing at private addresses can only be determined from a client on that network. The answer SHALL be obtained from the customer side and recorded, because it decides whether the cluster needs a local DNS resolver.

#### Scenario: Check performed from the customer network
- **WHEN** the rebinding-protection status of a customer network must be determined
- **THEN** the check is performed from a device on that network, not from inside the cluster

#### Scenario: Result recorded and acted on
- **WHEN** the check completes
- **THEN** the result is recorded against the cluster, and the local resolver fallback is enabled if and only if filtering was detected

### Requirement: The probe capability has a defined interface before it is built

The automated probe is deferred, but the interface it will satisfy SHALL be defined now, so that adding it later does not require changing the channel, the work order model, or the provisioning workflow.

#### Scenario: Probe results enter through the existing evidence path
- **WHEN** the probe capability is added later
- **THEN** its results are recorded on the work order through the same evidence path used by customer observations, requiring no change to the work order model

#### Scenario: Adding the probe does not change the customer journey
- **WHEN** the probe capability is added later
- **THEN** the three physical actions asked of the customer are unchanged

### Requirement: Probe platform limitations are established before committing to it

The platforms available on a customer's phone restrict what a probe can do; raw-socket scanning is unavailable on at least one major mobile platform, and local-network discovery may require platform permission that is granted case by case. These limits SHALL be established before the probe is scoped, so that it is not designed around a capability that cannot ship.

#### Scenario: Limits established before scoping
- **WHEN** the probe capability is scoped
- **THEN** the platform restrictions have been established, and the probe's questions are answerable within them

#### Scenario: Unanswerable questions stay with human escalation
- **WHEN** a question cannot be answered within platform limits
- **THEN** it remains assigned to human escalation rather than being designed into the probe
