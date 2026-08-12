## ADDED Requirements

### Requirement: Deployment profile axis

`cluster.yaml` SHALL carry a required `deployment_profile` field with exactly one of three values: `appliance`, `prosumer`, `full`. The field MUST NOT have a schema default — every cluster declares its profile explicitly so that an unmigrated config fails validation rather than silently rendering under an assumed profile.

#### Scenario: Valid profile accepted
- **WHEN** `cluster.yaml` sets `deployment_profile: appliance` and `task configure` runs
- **THEN** `cue vet` passes and rendering proceeds

#### Scenario: Missing profile rejected
- **WHEN** `cluster.yaml` omits `deployment_profile` and `task configure` runs
- **THEN** `cue vet` fails with an error naming the missing field, and no files under `kubernetes/` are written

#### Scenario: Unknown profile rejected
- **WHEN** `cluster.yaml` sets `deployment_profile: homelab`
- **THEN** `cue vet` fails and lists the three permitted values

### Requirement: Profile determines the required field set

The CUE schema SHALL make field requirements conditional on `deployment_profile`. Under `appliance`, the set of fields a customer must supply SHALL be empty — every remaining required value is either derived at render time or supplied by the provisioning operator.

#### Scenario: Appliance needs no customer-supplied fields
- **WHEN** a `cluster.yaml` contains only `deployment_profile: appliance` plus operator-supplied values (`cluster_name`, `repository_name`, `cloudflare_domain`, `cloudflare_token`)
- **THEN** `cue vet` passes without any LAN address or NAS field present

#### Scenario: Full profile keeps existing requirements
- **WHEN** a `cluster.yaml` sets `deployment_profile: full` and omits `cluster_gateway_addr`
- **THEN** `cue vet` fails, preserving today's behaviour for expert-operated clusters

### Requirement: Storage backend axis

`cluster.yaml` SHALL carry a `storage_backend` field with values `local-path` or `nfs`. `nas_server`, `nas_path`, and `nas_coding_path` SHALL be required only when `storage_backend` is `nfs`; `nas_coding_path` SHALL remain optional even then.

#### Scenario: NFS backend requires NAS coordinates
- **WHEN** `storage_backend: nfs` is set and `nas_server` is absent
- **THEN** `cue vet` fails naming `nas_server`

#### Scenario: local-path backend forbids nothing but requires nothing
- **WHEN** `storage_backend: local-path` is set with no `nas_*` fields
- **THEN** `cue vet` passes

#### Scenario: Existing cluster migration fails fast
- **WHEN** an existing `cluster.yaml` written before this change (no `deployment_profile`, no `storage_backend`) is run through `task configure`
- **THEN** validation fails before rendering, and the error identifies both missing fields

### Requirement: Profile selects the rendered application set

`templates/config/kubernetes/flux/cluster/ks.yaml.j2` SHALL render only the Kustomizations appropriate to the active profile. Base apps that cannot function under a profile's constraints MUST NOT be rendered for that profile.

#### Scenario: Appliance omits unusable base apps
- **WHEN** rendering with `deployment_profile: appliance`
- **THEN** the generated `ks.yaml` contains no Kustomization for `storage/nfs-subdir`

#### Scenario: Profile does not change extras semantics
- **WHEN** an `extras:` entry is listed under any profile
- **THEN** its Kustomization is rendered exactly as today, unchanged by the profile axis

### Requirement: Appliance profile implies Omni provisioning

The `appliance` profile SHALL be valid only for Omni-provisioned clusters. Manual Talos provisioning requires per-node IP, NIC, and disk selectors that a zero-IT customer cannot supply, so the combination MUST be rejected at validation time rather than failing later during bootstrap.

#### Scenario: Appliance with manual Talos node config rejected
- **WHEN** `deployment_profile: appliance` is set and a `nodes.yaml` for manual Talos provisioning is present
- **THEN** `task configure` fails with an error stating that `appliance` requires Omni provisioning
