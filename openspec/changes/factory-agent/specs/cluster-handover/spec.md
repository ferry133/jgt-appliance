## ADDED Requirements

### Requirement: Handover is a single executable action

Transferring control SHALL be one command, not a checklist someone follows by hand. A manual checklist is how a cluster ends up half-transferred, with the operator still holding a key nobody remembers.

#### Scenario: One command performs the transfer
- **WHEN** an operator runs the handover action with the customer's new key material and account details
- **THEN** every transferable item is transferred in that single run

#### Scenario: Partial handover is not left silent
- **WHEN** any item fails to transfer
- **THEN** the run reports which items succeeded and which did not, and does not report success

### Requirement: Handover covers every item in the credential inventory

Handover SHALL transfer or reissue every credential enumerated for that cluster. Changing a single account password transfers only that account and MUST NOT be presented as handover.

#### Scenario: All inventory items addressed
- **WHEN** handover completes
- **THEN** every item in the cluster's credential inventory is either transferred, reissued to the customer, or explicitly recorded as not transferable with the reason

#### Scenario: Encrypted files are re-keyed
- **WHEN** handover runs
- **THEN** all SOPS-encrypted files in the cluster's repository are re-encrypted to the customer's key, and the operator's key no longer decrypts them

#### Scenario: Repository ownership moves
- **WHEN** handover runs
- **THEN** the cluster's repository is transferred to the customer's account and the cluster continues to reconcile from it

### Requirement: Handover produces a bundle the customer can act on

Handover SHALL produce a written bundle enumerating what the customer now holds, what each item is for, and what they must do to keep the cluster running.

#### Scenario: Bundle enumerates holdings
- **WHEN** handover completes
- **THEN** the bundle lists every credential and account the customer now holds, with its purpose

#### Scenario: Bundle states ongoing obligations
- **WHEN** the bundle is produced
- **THEN** it states what will break if each item is lost, and what routine actions the cluster needs

### Requirement: The bundle states what capability is needed to use it

Onboarding asks the customer for three physical actions; handover asks them to operate DNS, a Git repository, encrypted secrets and cluster administration. That asymmetry is legitimate — handover happens when the service relationship ends — but the customer MUST NOT discover it on the day. The bundle SHALL state, for each item, what someone must be able to do to use it.

#### Scenario: Required capability is stated per item
- **WHEN** the handover bundle is produced
- **THEN** each item records what a person must be able to do to operate it, not only what it is

#### Scenario: The customer can decide whether to outsource
- **WHEN** the customer reads the bundle
- **THEN** they can tell whether to operate the cluster themselves or engage someone, without first attempting it

#### Scenario: Handover is not offered as equivalent to onboarding
- **WHEN** handover is described to a customer
- **THEN** it is not presented as requiring no more of them than setup did

### Requirement: Handover is proven by drill, not by assertion

The acceptance criterion for this capability SHALL be a drill: a person holding none of the operator's access takes the bundle and operates the cluster successfully. Until that drill passes, handover is not considered to work.

#### Scenario: Drill performed on a scratch cluster
- **WHEN** the handover drill is run
- **THEN** a person with no operator access uses only the bundle to reconcile a change, decrypt a secret, and reach the resident agent

#### Scenario: Drill failure blocks the claim
- **WHEN** the drill reveals an item the customer cannot use unaided
- **THEN** the handover action is corrected and the drill is repeated before handover is offered to a customer

### Requirement: The operator retains no access after handover

After handover, the operator SHALL have no residual access to the cluster or its secrets, unless the customer explicitly retains them for continued support.

#### Scenario: Residual access removed
- **WHEN** handover completes without a continued-support arrangement
- **THEN** operator credentials for that cluster are revoked, and the operator's key no longer decrypts its secrets

#### Scenario: Continued support is explicit
- **WHEN** the customer retains the operator for support after handover
- **THEN** the access the operator keeps is recorded explicitly in the bundle rather than left implicit
