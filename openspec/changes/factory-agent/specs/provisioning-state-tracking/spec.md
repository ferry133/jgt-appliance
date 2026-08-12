## ADDED Requirements

### Requirement: Each cluster delivery has one work order

Every cluster delivery SHALL be represented by exactly one GitHub Issue acting as its work order. The issue is the durable state store; no separate state file or database is introduced.

#### Scenario: Work order created before hardware ships
- **WHEN** a delivery is initiated
- **THEN** a work order issue exists identifying the customer, the profile, and the machine it expects

#### Scenario: One work order per delivery
- **WHEN** a provisioning run starts
- **THEN** it is associated with exactly one work order, and a second run for the same delivery reuses it

### Requirement: Stage is expressed as a label

The work order's current stage SHALL be carried by a label, drawn from a defined ordered vocabulary, so that stage is machine-readable and human-scannable without parsing prose.

#### Scenario: Stage advances by label
- **WHEN** the workflow completes a stage
- **THEN** the previous stage label is removed and the next is applied, leaving exactly one stage label

#### Scenario: Stage is readable without reading comments
- **WHEN** an operator lists open work orders
- **THEN** each one's stage is visible from its labels alone

### Requirement: Progress and evidence are recorded as comments

Each meaningful action SHALL append a comment recording what was done, to which external resource, and the evidence of success. This is the audit trail and the resume input.

#### Scenario: External resource identifiers recorded
- **WHEN** the workflow creates an external resource
- **THEN** a comment records its identifier, sufficient for a later run to find and adopt it

#### Scenario: Remediation recorded
- **WHEN** the agent applies an automatic remediation
- **THEN** a comment records the symptom, the remedy applied, and the verification result

#### Scenario: Secrets never appear in the work order
- **WHEN** any comment is written
- **THEN** it contains no key material, token, or password — only identifiers and non-sensitive evidence

### Requirement: Resume reads the work order

A resumed run SHALL determine completed stages from the work order's labels and comments.

#### Scenario: Resume from labels and comments
- **WHEN** a run resumes
- **THEN** it reads the work order to establish which stages are complete and which external resources already exist

#### Scenario: Contradiction halts rather than guesses
- **WHEN** the recorded state and the observed external state disagree
- **THEN** the run halts and escalates, rather than proceeding on either assumption

### Requirement: Stalled work orders are surfaced

A work order that has not advanced within its expected window SHALL be surfaced through the existing daily health reporting path, so a silently stuck delivery becomes visible without a separate monitoring system.

#### Scenario: Stalled order reported
- **WHEN** a work order has remained in the same stage beyond its expected window
- **THEN** it appears in the daily report as stalled, naming the stage and how long it has been there

#### Scenario: Completed orders stop being reported
- **WHEN** a work order reaches the completed stage
- **THEN** it is no longer reported as outstanding
