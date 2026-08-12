## ADDED Requirements

### Requirement: Storage tier is chosen by data type, not by size

Workloads SHALL be assigned a storage tier according to their access semantics. Anything relying on `fsync` durability and file locking — PostgreSQL, etcd, embedded databases, agent memory stores — MUST use block-backed storage. Bulk media, file shares, and backup targets MAY use NFS.

#### Scenario: Database uses block-backed storage
- **WHEN** a PostgreSQL PVC is provisioned under any profile
- **THEN** its storage class is block-backed (`local-path`, or a CSI block class where one is configured), never an NFS class

#### Scenario: Media uses NFS when available
- **WHEN** a bulk media or file-share PVC is provisioned on a cluster with `storage_backend: nfs`
- **THEN** it is provisioned from the NFS class

#### Scenario: Capacity pressure does not move a database to NFS
- **WHEN** a database outgrows local disk capacity
- **THEN** the remedy is larger local capacity or a block-mode CSI class backed by the NAS, and moving the database onto an NFS class is rejected

### Requirement: Node-local storage on a multi-node cluster is an explicit choice

Node-local volumes live on one node and their PersistentVolumes carry affinity to it. On a single node that is simply correct. On more than one node it pins every stateful workload to whichever node first scheduled it — the pod cannot be rescheduled elsewhere, and losing that node loses both the data and the ability to restart. The cluster looks replicated and is not. Validation SHALL refuse this combination unless it is explicitly acknowledged.

#### Scenario: Node count must be stated for node-local storage
- **WHEN** a cluster selects node-local storage without stating whether it has one node
- **THEN** validation fails, because the consequences differ entirely between the two cases

#### Scenario: A NAS does not exempt a cluster from the question
- **WHEN** a cluster with `storage_backend: nfs` enables an extra whose database lands on the block tier
- **THEN** it is subject to the same acknowledgement, because the database is pinned to one node regardless of what bulk storage the cluster has

#### Scenario: Single node needs no acknowledgement
- **WHEN** a single-node cluster selects node-local storage
- **THEN** validation passes with nothing further to declare

#### Scenario: Multi-node requires acknowledgement
- **WHEN** a multi-node cluster selects node-local storage without acknowledging the pinning
- **THEN** validation fails

#### Scenario: The acknowledgement cannot be supplied on the reader's behalf
- **WHEN** the acknowledgement is absent, or present and negative
- **THEN** validation fails rather than the requirement being satisfied by a default

#### Scenario: Replicated storage is the real answer
- **WHEN** a multi-node cluster has no NAS
- **THEN** the acknowledgement is recorded as a stopgap, and replicated block storage remains the correct solution

### Requirement: Default storage class follows the profile

Each profile SHALL supply a default storage class so that PVCs without an explicit class resolve correctly. Under `appliance` the default SHALL be `local-path`. Under `prosumer` and `full` the default SHALL follow `storage_backend`.

#### Scenario: Appliance defaults to local-path
- **WHEN** a PVC without an explicit storage class is created on an appliance cluster
- **THEN** it binds to a `local-path` volume

#### Scenario: NFS backend supplies the default
- **WHEN** a PVC without an explicit storage class is created on a cluster with `storage_backend: nfs`
- **THEN** it binds via the NFS provisioner, as today

### Requirement: No PVC names infrastructure that only one cluster has

> Revised 2026-08-11. This requirement previously read "No PVC depends on manual pre-provisioning", and asserted that every `storageClassName: ""` in `jg-base` left a claim Pending forever. Inspecting all thirteen occurrences disproved it: each is one half of a static PV/PVC pair declared in the same manifest and bound by `volumeName`, which is the correct idiom for a pre-existing NFS export and binds immediately. The real defect the scan found was a different one, stated below.

A manifest in `jg-base` is read by every cluster, so it SHALL NOT name infrastructure belonging to one of them. NFS coordinates SHALL be supplied by substitution rather than written literally.

#### Scenario: NAS address is not baked into the shared repository
- **WHEN** any PersistentVolume in `jg-base` declares an NFS server
- **THEN** it references `${NAS_SERVER}` rather than a literal address

#### Scenario: Static binding is permitted
- **WHEN** a PVC declares `storageClassName: ""` together with `volumeName` and a PersistentVolume declared alongside it
- **THEN** this is correct static provisioning and is left as is

#### Scenario: Export paths remain a known limitation
- **WHEN** an extra mounts a NAS export at a fixed path such as `/volume3/knowledge`
- **THEN** the path stays literal until that extra is needed off its originating cluster, and the limitation is recorded rather than silently carried

### Requirement: Agent workspace and agent memory have different durability

The claude-code workspace holds reconstructible working files and MAY live on node-local storage. Agent memory holds accumulated per-customer context that cannot be reconstructed and SHALL be stored in the database tier so that it is covered by database backups.

#### Scenario: Workspace on local storage
- **WHEN** a claude-code instance is deployed with no `nas_coding_path` configured
- **THEN** its workspace PVC is provisioned from the profile's default class and the deployment succeeds

#### Scenario: Agent memory survives workspace loss
- **WHEN** the workspace volume is destroyed and the instance is recreated
- **THEN** accumulated agent memory is still available, having been stored in the database tier

#### Scenario: NAS coding path remains available
- **WHEN** `nas_coding_path` is configured on a `prosumer` or `full` cluster
- **THEN** the workspace is mounted from NFS as today, unchanged by this requirement
