## ADDED Requirements

### Requirement: Local exceptions are declared, not hand-edited into generated files

A cluster's legitimate deviation from the shared configuration SHALL be expressed through a defined mechanism. Editing a rendered file's template by hand MUST NOT be the way this is done: the edit is indistinguishable from an un-synced older version, so it silently blocks every future template update.

#### Scenario: Exception expressed through the mechanism
- **WHEN** a cluster needs behaviour that differs from the shared default
- **THEN** it is expressed through the override mechanism, and the shared template file is unmodified

#### Scenario: Hand-edited generated template is reportable
- **WHEN** a cluster's copy of a shared template file differs from the template
- **THEN** that is reportable as drift rather than being indistinguishable from a declared exception

#### Scenario: Existing hand-written patches are migrated
- **WHEN** reconciliation completes
- **THEN** the exceptions currently hand-written into rendered-file templates have been migrated to the mechanism

### Requirement: An exception states why it exists

An override SHALL record the reason it exists. Without one it becomes permanent by default, because nobody can tell whether the condition that motivated it still holds.

#### Scenario: Reason is recorded
- **WHEN** an override is declared
- **THEN** it records what problem it addresses and what would have to change for it to be removed

#### Scenario: Overrides are reviewable
- **WHEN** a cluster's overrides are listed
- **THEN** each appears with its reason, so obsolete ones can be identified

### Requirement: An override does not silently widen

An override SHALL affect only what it declares. A mechanism that lets a narrow exception quietly replace a broader shared behaviour reintroduces the problem it was meant to solve.

#### Scenario: Scope is bounded
- **WHEN** an override is applied
- **THEN** shared behaviour outside its declared scope is unchanged

#### Scenario: Shared improvements still reach the cluster
- **WHEN** the shared configuration improves in an area a cluster has overridden nearby
- **THEN** the improvement reaches that cluster except where the override explicitly applies

### Requirement: A per-cluster workaround that generalises becomes a feature

An override declared by more than one cluster SHALL be raised as a candidate to become a supported configuration option. Repetition is evidence of a missing shared capability, not of coincidence.

#### Scenario: Repeated override promotes to configuration
- **WHEN** the same override is declared by more than one cluster
- **THEN** it is raised as a candidate to become a supported configuration option rather than remaining duplicated

#### Scenario: Promotion retires the overrides
- **WHEN** an override becomes a supported option
- **THEN** the clusters that carried it switch to the option and their overrides are removed
