## ADDED Requirements

### Requirement: Both provisioning paths are supported

The repository SHALL support provisioning through the managed control plane and provisioning Talos manually. Neither path is deprecated; they serve different users.

#### Scenario: Manual path is complete
- **WHEN** a user follows the manual path
- **THEN** every command, template, and schema it requires exists in this repository

#### Scenario: Managed path is unaffected
- **WHEN** the manual path is added
- **THEN** the managed path's behaviour is unchanged

### Requirement: One path's prerequisites do not block the other

Tooling and environment prerequisites SHALL apply only to the path that needs them. A user of the managed path MUST NOT be required to install or configure tooling that only the manual path uses.

#### Scenario: Managed path does not require manual-path tooling
- **WHEN** a user of the managed path runs the application bootstrap
- **THEN** it does not fail for a missing manual-path tool or a missing manual-path configuration path

#### Scenario: Manual path still checks its own prerequisites
- **WHEN** a user of the manual path runs the application bootstrap
- **THEN** its manual-path prerequisites are checked and a missing one fails the run

#### Scenario: Path is determined, not guessed per invocation
- **WHEN** the bootstrap runs
- **THEN** which path's prerequisites apply is determined from configuration, not inferred from whichever files happen to be present

### Requirement: Path selection is consistent with the deployment profile

The profile that requires zero customer-supplied input cannot use the manual path, because the manual path needs per-node facts a non-technical customer cannot supply. This SHALL be enforced at validation time.

#### Scenario: Zero-input profile rejects the manual path
- **WHEN** a configuration combines the zero-input profile with manual node declarations
- **THEN** validation fails stating that the profile requires the managed path

#### Scenario: Other profiles may use either path
- **WHEN** a configuration uses a profile that permits operator input
- **THEN** either path is accepted

### Requirement: Documentation routes each path to its own instructions

Each path SHALL be documented completely in one place, and documentation MUST NOT present a command from one path as though it applied to the other.

#### Scenario: Manual path instructions name real commands
- **WHEN** the manual path documentation is followed
- **THEN** every command it names exists in this repository

#### Scenario: Paths are not interleaved
- **WHEN** a reader follows one path's documentation
- **THEN** they are not required to skip over steps belonging to the other path
