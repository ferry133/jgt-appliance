# Template lineage and divergence inventory

Measured 2026-08-10. Working artifact for the `reconcile-jcom-lineage` change.

Cluster repositories are generated from this template once and then never
re-synced, so each one is frozen at the template's shape on its creation date.
Three generations exist. This is not "the template plus some tweaks" — the
generations differ in what the template was responsible for.

## The three generations

| Repo | Apps templated in-repo | Manual Talos toolchain | Notes |
|------|-----------------------|------------------------|-------|
| `genie1` | 5 namespaces (cilium, spegel, …) | yes | Predates `jg-base`; the repo rendered the apps itself |
| `jcom` | 2 namespaces | yes | Apps moved to `jg-base`; kept the Talos toolchain |
| `jg-jiahd` | 2 namespaces | no | Matches the template except one workaround |
| this template | 2 namespaces | yes (restored 2026-08-09) | — |

The template lost the Talos toolchain at some point and `revive-talos-path`
brought it back — which is why the ported files are byte-identical to
`genie1`'s copy. The template was behind its own descendants.

## Why divergence accumulates

`kubernetes/flux/cluster/ks.yaml` is a rendered artifact, but every per-cluster
exception is hand-written into its `.j2` template. A hand-edited template file
and an un-synced older one are **indistinguishable at the file level** — there
is no signal separating "this cluster deliberately differs" from "this cluster
is behind". So each workaround makes the next template update harder, and the
next workaround has nowhere to go but the same file.

Both known exceptions live there: `jcom`'s Cilium and Spegel patches, and
`jg-jiahd`'s QUIC patch.

## jcom — classification

Baseline: the template as of `849fde5`, before `revive-talos-path`.

| Item | Where | Classification | Status |
|------|-------|----------------|--------|
| `talos_patches()` plugin function | `plugin.py` | adopt into template | ✅ done (①) |
| `node_default_gateway` / `node_dns_servers` / `node_ntp_servers` defaults | `plugin.py` | adopt into template | ✅ done (①) |
| `cluster_svc_cidr: 10.43.0.0/16` | `plugin.py` | superseded — field is now required, no default | ✅ done (①) |
| `TEMPLATE_NODE_CONFIG_FILE` | `.taskfiles/template/` | adopt into template | ✅ done (①) |
| `encrypt-secrets` covering `TALOS_DIR` | `.taskfiles/template/` | adopt into template | ✅ done (①) |
| `kubeconform` wired to a task | `.taskfiles/template/` | adopt into template | ✅ done (①) |
| `bootstrap:talos` task | `.taskfiles/bootstrap/` | adopt into template | ✅ done (①) |
| `TALOS_DIR` / `TALOSCONFIG` / talos include | `Taskfile.yaml` | adopt into template | ✅ done (①) |
| `nodes.yaml` as makejinja data | `makejinja.toml` | adopt into template | ✅ done (①) |
| `validate-talos-config` task | `.taskfiles/template/` | **adopt** | ⬜ pending |
| `cloudflare-tunnel.json` precondition | `.taskfiles/template/` | **adopt** | ⬜ pending |
| `spegel_enabled` derivation + usage | `plugin.py`, `01-apps.yaml.j2` | **adopt, generalised** — single-node safety is a rule, not a jcom quirk | ⬜ pending |
| `cilium_bgp_enabled`, `cilium_loadbalancer_mode` | `plugin.py` | **drop from jcom** — zero consumers there | ⬜ pending |
| namespace discovery by scanning `kubernetes/apps/*/` | `bootstrap-apps.sh` | **drop from jcom** — the template's fixed list is a deliberate correction; the scan yields wrong namespaces under the current layout | ⬜ pending |
| no `trello-notifier` data file | `makejinja.toml` | **resolve** — the template declares it and makejinja aborts on a missing data file | ⬜ pending |
| Cilium native-routing override | `ks.yaml.j2` | **generalise** — see below | ⬜ pending |
| Spegel suspend | `ks.yaml.j2` | **generalise** — see below | ⬜ pending |

Nothing was classified "unexplained": every divergence carries a reason, and
both `ks.yaml.j2` blocks are commented with the incident that motivated them.

### The two ks.yaml.j2 blocks are the same problem

Both exist because **jcom is single-node while `jg-base` is written for
multi-node KubeSpan clusters**:

- **Spegel** is a peer-to-peer image mirror. `jg-base` deploys it
  unconditionally. On one node it never became ready and, while failing, wrote
  `/etc/cri/conf.d/hosts/_default/hosts.toml` mirroring every registry to dead
  `:29999`/`:30021` — after which no uncached image could be pulled anywhere on
  the cluster.
- **Cilium** runs vxlan with MTU 1370 so KubeSpan works across subnets. jcom
  hosts Omni, and 1370 is too small for Omni's SideroLink WireGuard →
  `sendmmsg: message too long` → slow Omni UI and kubectl. A single-node
  cluster needs no KubeSpan, so native routing at MTU 1500 is correct there.

Neither is a jcom quirk. `deployment_profile: appliance` is single-node by
definition, so **every appliance reproduces the Spegel failure** and gets the
needlessly small MTU. These belong in profile-driven configuration, not in a
per-cluster patch.

### Spegel reproduced on a disposable single-node cluster (2026-08-10)

Rather than trust the incident note, it was reproduced deliberately on the
acceptance-test machine while verifying `revive-talos-path` task 8.2.

**Confirmed — Spegel is structurally broken on one node.** The pod reaches
`Running` but never `Ready`, and restarts:

```
"failed to run bootstrap"  err="routing table is empty after bootstrapping"  attempts=16
```

Its peer-to-peer router has no peers to bootstrap a DHT with, so the readiness
probe can never pass. It also writes the registry mirror config regardless of
being unhealthy — `_default` means every registry, not a subset:

```toml
# /etc/cri/conf.d/hosts/_default/hosts.toml
[host.'http://10.9.1.238:29999']
capabilities = ['pull', 'resolve']
dial_timeout = '200ms'
[host.'http://10.9.1.238:30021']
capabilities = ['pull', 'resolve']
dial_timeout = '200ms'
```

**Not reproduced — the cluster-wide image-pull failure.** An uncached image
pulled successfully in 7.3s while Spegel sat unready: containerd dialed the
dead mirror, gave up after the 200 ms timeout, and fell back to the upstream
registry.

The difference appears to be containerd's version:

| Cluster | Nodes | containerd | Talos | Spegel |
|---------|-------|-----------|-------|--------|
| jcom (where the incident happened) | 1 | 2.1.6 | 1.12.4 | suspended by hand-written patch |
| jg-jiahd | 3 | 2.2.3 | 1.13.2 | 3/3 Ready |
| acceptance test | 1 | 2.2.6 | 1.13.8 | 0/1, restart loop, pulls still work |

So the hazard is **real but less severe than recorded, on current containerd**:
a permanently-unready pod, a restart loop, and a pointless 200 ms dial before
every registry hit — not a dead cluster. Gating Spegel off for single-node
clusters is still required; treating it as an emergency is not.

Two caveats against over-reading this: one image from one public registry was
tested, and a registry that is reachable-but-broken may behave differently from
one that refuses the connection. "Not reproduced" is not "cannot happen".

Both patches also document a mechanism worth keeping: the Cilium one uses a
JSON6902 append rather than a strategic merge, because a second strategic merge
**replaces** the child Kustomization's whole `spec.patches` list and silently
drops the generic HelmRelease-strategy patch above it.

## jg-jiahd — classification

| Item | Where | Classification | Status |
|------|-------|----------------|--------|
| QUIC → http2 tunnel transport | `ks.yaml.j2` | **keep as a declared per-cluster exception** — the node's ISP blocks UDP 7844; genuinely local | ⬜ migrate to the override mechanism |

Everything else matches the template. Its comment still says `jgu5:`, the repo's
name before it was renamed — harmless, but evidence that nothing re-reads these
blocks once written.

## genie1 — not inventoried

Oldest generation: renders 5 namespaces of app manifests itself and is the only
repo still consuming `cilium_bgp_enabled` and `cilium_loadbalancer_mode`.
Reconciling it is a larger job than jcom and is out of scope here. Recorded so
that "the template's descendants" is not assumed to mean two repos.

## Dead schema fields in the template

`cluster.schema.cue` declares four fields with **zero consumers** anywhere —
not in templates, not in `cluster-secrets`, not in `jg-base`:

```
cilium_bgp_router_addr    cilium_bgp_router_asn
cilium_bgp_node_asn       cilium_loadbalancer_mode
```

They are inherited from the generation where cilium was templated in-repo, and
only `genie1` still consumes them. A declared field nothing reads is the same
defect class as the divergent `cluster_svc_cidr` default that
`revive-talos-path` fixed: it looks like configuration and is not. Either wire
them through `cluster-secrets` to `jg-base` or remove them.
