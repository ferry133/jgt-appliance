# jg-cluster-template

GitHub template for a Kubernetes cluster managed by ferry133. Click
**"Use this template"** to generate a per-user repo.

## Which document do you need?

| You are | Read |
|---------|------|
| A customer who received the hardware | **[`README-zero-IT.md`](README-zero-IT.md)**（繁體中文）— three physical actions, nothing else |
| Provisioning a cluster yourself, by hand | **[`docs/deploy/manual.md`](docs/deploy/manual.md)** — full step-by-step, both provisioning paths |
| Delivering an appliance to a customer | The operator runbook (see `openspec/changes/factory-agent`) |
| Changing how the template works | [`CLAUDE.md`](CLAUDE.md) — architecture, conventions, and the rules that are not obvious from the code |

This page routes; it deliberately contains no deployment steps, so there is only
one place each procedure is written down.

## Architecture

Three repositories, none of which is useful alone:

| Repo | Role |
|------|------|
| [`ferry133/jg-base`](https://github.com/ferry133/jg-base) | Golden Kubernetes manifests, watched by every cluster via Flux |
| `ferry133/jg-cluster-template` (this repo) | CUE schema, Jinja2 templates, Taskfile — the tooling that turns `cluster.yaml` into a cluster |
| per-user repo (generated from this template) | One `cluster.yaml`, its encrypted secrets, and the Flux entry point |

## Deployment profiles

`deployment_profile` in `cluster.yaml` decides how much the person setting up
the cluster has to know. It has no default — an unmigrated config fails
validation rather than being rendered under an assumption.

| Profile | For | Customer-supplied fields |
|---------|-----|--------------------------|
| `appliance` | Operator-delivered, single node | none |
| `prosumer` | Customer has a NAS or some infrastructure | a few |
| `full` | Expert operates it directly | all of them |

`storage_backend` (`local-path` / `nfs`) is the second axis: it selects what
bulk media and file shares use. Databases are block-backed either way.

## Provisioning paths

| Path | Machines are found by | Node facts come from |
|------|----------------------|----------------------|
| **Omni** | SideroLink — the machine registers itself | Omni |
| **Manual Talos** | You, with `nmap` | `nodes.yaml`, filled in by hand |

`appliance` implies Omni: the manual path needs per-node IP, NIC and disk
selectors that a non-technical customer cannot supply, so the combination is
rejected at validation time.

## Common commands

```sh
task init                      # generate cluster.yaml, nodes.yaml, age.key, deploy key
task configure                 # validate → render → validate manifests → encrypt
task bootstrap:talos           # manual path only: install Talos onto the nodes
task bootstrap:apps            # install Cilium, cert-manager, Flux; hand over to GitOps
task reconcile                 # force Flux to re-sync
task template:check            # rendering-pipeline integrity (runs inside configure)
task template:validate-manifests   # kubeconform over the rendered output
```

## Planned work

Design proposals live in `openspec/changes/`. They record what is being built,
why, and the measurements behind each decision — including the failures found
while verifying them.

| Change | About |
|--------|-------|
| `revive-talos-path` | Restore the manual Talos path this repo documented but did not ship |
| `deployment-profiles` | The profile and storage axes above |
| `factory-agent` | Operator-side agent that provisions a cluster end to end |
| `zero-it-onboarding` | This documentation split, and the customer-facing channel |
| `reconcile-jcom-lineage` | Bring a cluster that diverged back onto the template |
