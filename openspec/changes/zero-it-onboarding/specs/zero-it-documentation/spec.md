## ADDED Requirements

### Requirement: Documentation is split by reader

Each document SHALL serve exactly one audience and SHALL NOT mix instructions meant for different readers. A single document serving an operator, an expert self-hoster, and a non-technical customer is unusable by all three.

#### Scenario: Entry document routes rather than instructs
- **WHEN** a reader opens the repository's main README
- **THEN** it states what the system is and routes each audience to their document, without containing deployment steps itself

#### Scenario: Zero-IT document contains no technical steps
- **WHEN** the zero-IT customer document is read end to end
- **THEN** it contains no command line, no configuration file, and no account setup

#### Scenario: Expert path remains fully documented
- **WHEN** an expert user wants to provision manually, including the manual Talos path
- **THEN** a document exists covering that path completely, without zero-IT material interleaved

#### Scenario: Operator runbook is referenced, not duplicated
- **WHEN** documentation refers to the operator provisioning procedure
- **THEN** it links to the single executable runbook rather than restating its steps

### Requirement: Documented commands match the repository

Every command, file path, and repository name appearing in documentation SHALL exist in this repository at the stated location. Documentation that references a tool the repository does not ship, or an upstream repository that is not this one, is a defect.

#### Scenario: No references to non-existent tooling
- **WHEN** documentation is checked against the repository
- **THEN** every documented command resolves to a task, script, or tool the repository actually provides

#### Scenario: Repository references are self-referential
- **WHEN** documentation instructs a reader to create a repository from this template
- **THEN** it names this repository, not the upstream project it was derived from

#### Scenario: Documentation does not contradict project rules
- **WHEN** documentation instructs an action on credentials or kubeconfig files
- **THEN** that instruction is consistent with the project's stated rules for those files

#### Scenario: Structural claims are accurate
- **WHEN** documentation states how many stages or steps a procedure has
- **THEN** the stated count matches the number actually present

### Requirement: The zero-IT document works with no connectivity

The customer reads this document before their network is working. It SHALL be delivered as a physical printed item in the box. A URL or QR code MAY supplement it but MUST NOT be the only way to reach it.

#### Scenario: Printed copy ships with hardware
- **WHEN** hardware is delivered
- **THEN** a printed copy of the customer instructions is inside the box

#### Scenario: Instructions readable before any setup
- **WHEN** the customer has done nothing yet and has no working connection to the operator
- **THEN** the printed instructions are sufficient to complete every action asked of them

#### Scenario: Printed and source content stay identical
- **WHEN** the customer instructions are changed
- **THEN** the printed artifact is regenerated from the same source, so the two cannot diverge

### Requirement: The zero-IT document is written in the customer's language

The document SHALL be written in the language the customer reads, at a reading level that assumes no technical background.

#### Scenario: No untranslated technical vocabulary
- **WHEN** the customer document is reviewed
- **THEN** it contains no term that requires technical background to understand, and no untranslated jargon

### Requirement: The zero-IT document is validated by an untrained reader

Readability SHALL be proven by test, not asserted. A person with no IT knowledge, who has not been briefed on the procedure, SHALL complete it unaided.

#### Scenario: Unaided completion
- **WHEN** an untrained reader is given only the box and the printed instructions
- **THEN** they complete every action asked of them without assistance, and reach the point where the system reports itself ready

#### Scenario: Failure revises the document
- **WHEN** the reader hesitates, asks a question, or performs an action incorrectly
- **THEN** that point is recorded as a documentation defect and the document is revised before the next test

#### Scenario: Test readers are uncontaminated
- **WHEN** a readability test is run
- **THEN** the reader has not previously seen the procedure or been told what to expect
