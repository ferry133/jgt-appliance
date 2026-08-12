## ADDED Requirements

### Requirement: Every divergence is inventoried and classified

Divergence between a cluster repository and the template SHALL be enumerated file by file and each item classified as one of: adopt into the template, remove from the cluster, or keep as a declared per-cluster exception. An item that nobody can explain is itself a finding and MUST be resolved rather than carried forward.

#### Scenario: Inventory is complete
- **WHEN** the reconciliation inventory is reviewed
- **THEN** every differing file is listed, and every difference within it is assigned exactly one classification

#### Scenario: Unexplained divergence is escalated
- **WHEN** a difference has no identifiable reason
- **THEN** it is recorded as unexplained and resolved before reconciliation completes, rather than being silently kept or silently dropped

#### Scenario: Direction of divergence is recorded
- **WHEN** an item is classified
- **THEN** the record states whether the cluster or the template held the better version, so the same judgement is not re-litigated later

### Requirement: Fixes found only in a cluster are returned to the template

A cluster repository that carries a correction the template lacks SHALL have that correction adopted into the template, so that every other cluster benefits and the cluster stops being the only place it exists.

#### Scenario: Cluster-only fix adopted
- **WHEN** the inventory identifies a correction present only in a cluster repository
- **THEN** it is adopted into the template, or explicitly rejected with a stated reason

#### Scenario: Adoption is verified against the origin cluster
- **WHEN** a cluster-only fix is adopted into the template
- **THEN** rendering that cluster from the updated template reproduces the behaviour the fix provided

### Requirement: Superseded cluster content is removed

Where the template holds a newer, correct version of something a cluster still carries in an older form, the cluster SHALL be updated rather than left on the old form.

#### Scenario: Superseded content updated
- **WHEN** a cluster carries an older form of something the template has since corrected
- **THEN** the cluster is updated to the template's version

#### Scenario: Update is justified, not assumed
- **WHEN** the template's version is adopted into a cluster
- **THEN** the reason the template's version is correct for that cluster is recorded, since "newer" alone is not a reason

### Requirement: The reconciled cluster can consume template updates

Reconciliation SHALL be treated as complete only when the cluster can take a template update as a routine operation. A cluster that still requires hand-merging MUST NOT be considered reconciled.

#### Scenario: Template update applies cleanly
- **WHEN** a subsequent template change is applied to the reconciled cluster
- **THEN** it applies without hand-merging, and the cluster's declared exceptions survive

#### Scenario: Reconciliation proven by a real sync
- **WHEN** reconciliation is declared complete
- **THEN** at least one actual template sync has been performed and its rendered output verified

#### Scenario: Rendered output is compared, not assumed
- **WHEN** a cluster is reconciled
- **THEN** its rendered manifests are compared before and after, with encrypted files compared in decrypted form, and every difference accounted for

### Requirement: Divergence is detectable going forward

The reconciliation SHALL leave behind a way to see that a cluster has drifted, so the next divergence is noticed while it is small.

#### Scenario: Drift is reportable
- **WHEN** a cluster's files are compared against the template
- **THEN** declared exceptions are distinguishable from undeclared drift

#### Scenario: Undeclared drift is visible
- **WHEN** a cluster acquires a change that is neither a template update nor a declared exception
- **THEN** that change is reportable as drift
