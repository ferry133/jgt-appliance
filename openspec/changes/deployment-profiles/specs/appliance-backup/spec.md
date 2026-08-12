## ADDED Requirements

### Requirement: Appliance clusters back up off-site unconditionally

A single-node appliance using node-local storage has no redundancy: losing the disk loses the database and the agent's accumulated context. Under the `appliance` profile off-site backup SHALL be mandatory and MUST NOT be an opt-in extra.

#### Scenario: Backup ships with the profile
- **WHEN** an appliance cluster is rendered
- **THEN** the backup CronJob is present in the generated manifests without being listed in `extras:`

#### Scenario: Missing backup destination fails validation
- **WHEN** `deployment_profile: appliance` is set and the backup destination configuration is absent
- **THEN** `cue vet` fails, rather than rendering a cluster whose data is unprotected

### Requirement: Backups are encrypted with the cluster's own age key

Backup payloads SHALL be encrypted with the cluster's age public key before leaving the cluster. The destination operator MUST NOT be able to read them; decryption capability travels with `age.key` and therefore transfers with the handover bundle.

#### Scenario: Payload is encrypted before upload
- **WHEN** a backup run completes
- **THEN** the object written to the destination is age-encrypted, and no plaintext database dump is transmitted or stored

#### Scenario: Destination credentials cannot decrypt
- **WHEN** the backup destination's contents are read using the destination credentials alone
- **THEN** no cluster data is recoverable without `age.key`

### Requirement: Backup scope covers what cannot be reconstructed

Backups SHALL include the database tier and the agent workspace. Content already durable elsewhere — Kubernetes manifests in the Git repository, cluster state rebuildable from that repository — MUST NOT be included.

#### Scenario: Database and workspace captured
- **WHEN** a backup run completes
- **THEN** the archive contains a PostgreSQL dump and the agent workspace contents

#### Scenario: Reconstructible content excluded
- **WHEN** a backup run completes
- **THEN** the archive contains no copy of the Git-tracked Kubernetes manifests

### Requirement: Backup freshness is monitored by the existing daily check

The `monitoring/daily-check` CronJob SHALL report the age of the most recent successful backup. A backup pipeline that has silently stopped MUST become visible through the existing dead-man-switch path rather than requiring a separate alerting channel.

#### Scenario: Fresh backup reported
- **WHEN** the daily check runs and a backup completed within the last 24 hours
- **THEN** the report includes the backup age and the check passes

#### Scenario: Stale backup escalates
- **WHEN** the daily check runs and no backup has completed within the configured staleness threshold
- **THEN** the check reports failure and the dead-man-switch ping is withheld, raising the existing alert

#### Scenario: Unconfigured cluster stays quiet
- **WHEN** the daily check runs on a non-appliance cluster with no backup configured
- **THEN** it logs that backup checking is not configured and exits successfully, matching the CronJob's existing behaviour for unconfigured features

### Requirement: The cluster age key is escrowed

`age.key` is generated during provisioning and is the sole means of decrypting both SOPS secrets and backups. It SHALL be escrowed outside the customer site at provisioning time and SHALL be listed as an item of the handover bundle.

#### Scenario: Key escrowed at provisioning
- **WHEN** provisioning completes for a new cluster
- **THEN** `age.key` exists in the operator's escrow store, and the provisioning record notes that escrow succeeded

#### Scenario: Total site loss is recoverable
- **WHEN** the appliance hardware is destroyed and replaced
- **THEN** the escrowed `age.key` plus the Git repository plus the off-site backup are together sufficient to rebuild the cluster with its data

### Requirement: Restore is verified, not assumed

An untested backup is not a backup. A restore drill SHALL be performed on a scratch cluster and SHALL be the acceptance criterion for this capability.

#### Scenario: Restore drill succeeds
- **WHEN** a backup archive is restored onto a freshly provisioned scratch cluster using only the archive and the escrowed `age.key`
- **THEN** the database contents and agent workspace match the source cluster at backup time

#### Scenario: Restore procedure is documented
- **WHEN** an operator needs to restore an appliance
- **THEN** a written restore procedure exists that was followed verbatim during the drill
