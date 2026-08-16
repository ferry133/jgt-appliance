# Manual deployment — expert path

Full step-by-step provisioning, for someone comfortable with Kubernetes, Talos
and the shell. This is the `full` deployment profile: everything is declared by
hand in `cluster.yaml`.

- Delivering an appliance to a non-technical customer? That is the operator
  runbook, not this document.
- Are you the customer who received the hardware? See `README-zero-IT.md`
  (Traditional Chinese) — you are asked for three physical actions and nothing
  on this page applies to you.

Two provisioning paths are covered:

| Path | When | Node facts |
|------|------|-----------|
| **(B) Omni** | Default. Machines self-register over SideroLink | Supplied by Omni |
| **(A) Manual Talos** | No Omni, or you want direct control | You fill in `nodes.yaml` |

`deployment_profile: "appliance"` is rejected with the manual Talos path: it
needs per-node IP, NIC and disk selectors a zero-IT customer cannot supply.

---

## 🚀 Let's Go!

There are **7 stages** below. Follow them in order.

### Stage 1: Hardware Configuration

For a **stable** and **high-availability** production Kubernetes cluster, hardware selection is critical. NVMe/SSDs are strongly preferred over HDDs, and **Bare Metal is strongly recommended** over virtualized platforms like Proxmox.

Using **enterprise NVMe or SATA SSDs on Bare Metal** (even used drives) provides the most reliable performance and rock-solid stability. Consumer **NVMe or SATA SSDs**, on the other hand, carry risks such as latency spikes, corruption, and fsync delays, particularly in multi-node setups.

**Proxmox with enterprise drives can work** for testing or carefully tuned production clusters, but it introduces additional layers of potential I/O contention — especially if consumer drives are used. Any **replicated storage** (e.g., Rook-Ceph, Longhorn) should always use **dedicated disks separate from control plane and etcd nodes** to ensure reliability. Worker nodes are more flexible, but risky configurations should still be avoided for stateful workloads to maintain cluster stability.

These guidelines provide a strong baseline, but there are always exceptions and nuances. The best way to ensure your hardware configuration works is to **test it thoroughly and benchmark performance** under realistic workloads.

### Stage 2: Machine Preparation

> [!IMPORTANT]
> If you have **3 or more nodes** it is recommended to make 3 of them controller nodes for a highly available control plane. This project configures **all nodes** to be able to run workloads. **Worker nodes** are therefore **optional**.
>
> **Minimum system requirements**
> | Role    | Cores    | Memory        | System Disk               |
> |---------|----------|---------------|---------------------------|
> | Control/Worker | 4 | 16GB | 256GB SSD/NVMe |

##
## 2 types of Baby k8s Clusters sources ---(A) Talos ---(B) Omni
##
## ---(A) Talos Baby Cluster Setup
1. Head over to the [Talos Linux Image Factory](https://factory.talos.dev) and follow the instructions. Be sure to only choose the **bare-minimum system extensions** as some might require additional configuration and prevent Talos from booting without it. Depending on your CPU start with the Intel/AMD system extensions (`i915`, `intel-ucode` & `mei` **or** `amdgpu` & `amd-ucode`), you can always add system extensions after Talos is installed and working.

2. This will eventually lead you to download a Talos Linux ISO (or for SBCs a RAW) image. Make sure to note the **schematic ID** you will need this later on.

3. Flash the Talos ISO or RAW image to a USB drive and boot from it on your nodes.

4. Verify with `nmap` that your nodes are available on the network. (Replace `192.168.1.0/24` with the network your nodes are on.)

    ```sh
    nmap -Pn -n -p 50000 192.168.1.0/24 -vv | grep 'Discovered'
    ```


## ---(B) Omni Baby Cluster Setup

All clusters use **Cilium** as CNI (installed automatically by `task bootstrap:apps`). You must disable Omni's built-in flannel CNI before first boot.

### 1. Create Installatoin ISO in Omni UI

Omni UI → Download Installation Media → Create New.    (If havn't create yet.)

- **Cluster Name**: e.g. `jg-jiahd`
- **Talos Version**: latest
- **Kubernetes Version**: matching version

### 2. Add MachineConfigPatch (required — before first boot)

In the cluster creation screen, add a Patch:

```yaml
cluster:
  network:
    cni:
      name: none
  coreDNS:
    disabled: true
  proxy:
    disabled: true
```

This tells Talos to skip the built-in CNI flannel, coredns and kube-proxy. The replacements, Cilium + coredns, will be installed from `jg-base` in step 5.

⚠️ This patch **must** be applied before the cluster first boots. If flannel or Omni's coredns is already installed, you must recreate the cluster.




### Stage 3: Local Workstation

> [!TIP]
> It is recommended to set the visibility of your repository to `Public` so you can easily request help if you get stuck.

1. Create a new repository by clicking the green `Use this template` button at the top of this page, then clone the new repo you just created and `cd` into it. Alternatively you can use the [GitHub CLI](https://cli.github.com/) ...

    ```sh
    export REPONAME="home-ops"
    gh repo create $REPONAME --template ferry133/jg-cluster-template --private --clone
    cd $REPONAME
    ```

2. **Install** the [Mise CLI](https://mise.jdx.dev/getting-started.html#installing-mise-cli) on your local workstation.

3. **Activate** Mise in your shell by following the [activation guide](https://mise.jdx.dev/getting-started.html#activate-mise).

4. Use `mise` to install the **required** CLI tools:

    ```sh
    mise trust
    pip install pipx
    mise install
    ```

   📍 _**Having trouble installing the tools?** Try unsetting the `GITHUB_TOKEN` env var and then run these commands again_

   📍 _**Having trouble compiling Python?** Try running `mise settings python.compile=0` and then run these commands again_

5. Logout of the GitHub Container Registry as this may cause authorization problems in future steps when using the public registry:

    ```sh
    docker logout ghcr.io
    helm registry logout ghcr.io
    ```

### Stage 4: Cloudflare configuration

> [!WARNING]
> If any of the commands fail with `command not found` or `unknown command` it means `mise` is either not installed, activated or it could be configured incorrectly.

1. Create a Cloudflare API token for use with cloudflared and external-dns by reviewing the official [documentation](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/) and following the instructions below.

   - Click the blue `Use template` button for the `Edit zone DNS` template.
   - Name your token `kube`
   - Under `Permissions`, click `+ Add More` and add permissions `Zone - DNS - Edit` and `Account - Cloudflare Tunnel - Read`
   - Limit the permissions to a specific account and/or zone resources and then click `Continue to Summary` and then `Create Token`.
   - **Save this token somewhere safe**, you will need it later on.

2. Create the Cloudflare Tunnel:

    ```sh
    cloudflared tunnel login
    cloudflared tunnel create --credentials-file cloudflare-tunnel.json kube
    ```

> [!NOTE]
> The tunnel name is per-account, not per-cluster: `cloudflared tunnel create` fails
> if one of that name already exists. This repo uses `kube` because `kubernetes` is
> already taken in the `janncot.cc` account by another cluster. Nothing in the
> manifests reads the name — cloudflared authenticates with the tunnel ID and secret
> from `cloudflare-tunnel.json` — so it only has to be unique, and only matters when
> reading the Cloudflare dashboard.


The tunnel token is embedded into cluster secrets by `task configure`.


### Stage 5: Cluster configuration

1. Generate the config files from the sample files:

```sh
task init
```

Generates: `cluster.yaml` (from sample), `nodes.yaml` (from sample), `age.key` (SOPS key), `github-deploy.key`, `github-push-token.txt`.

2. Fill out the `cluster.yaml` configuration file using the comments in it as a guide. Select & un-comment for all available extras and optional fields.

    Start with the two fields at the top — they decide which of the rest you
    actually need, and neither has a default:

    | Field | Values | Effect |
    |-------|--------|--------|
    | `deployment_profile` | `appliance` / `prosumer` / `full` | This page is the `full` path. `appliance` rejects everything you would fill in by hand. |
    | `storage_backend` | `local-path` / `nfs` | Which class is the cluster default. `nfs` requires `nas_server` and `nas_path` and enables the NFS provisioner; `local-path` suspends it. `local-path` itself is installed either way. |

    `cue vet` runs before anything is rendered, so a missing or contradictory
    field fails immediately and leaves `kubernetes/` untouched.

    ---(A) Talos baby cluster: also fill out `nodes.yaml` — one entry per node,
    with `name`, `address`, `controller`, `disk`, `mac_addr` and `schematic_id`.
    Obtain the last three with `talosctl get disks -n <ip> --insecure`,
    `talosctl get links -n <ip> --insecure`, and the schematic ID you noted from
    the Image Factory. `nodes.sample.yaml` documents every field, and
    `task configure` validates them against `nodes.schema.cue` before rendering.

    ---(B) Omni baby cluster: leave `nodes.yaml` as `nodes: []`. Omni supplies
    the machine configuration; nothing under `talos/` is used.


3. Template out the kubernetes and talos configuration files, if any issues come up be sure to read the error and adjust your config files accordingly.

    ```sh
    task configure
    ```

    Validates schema → renders Jinja2 templates → encrypts secrets → validates outputs.

    Produces:
    ```
    kubernetes/
      components/sops/cluster-secrets.sops.yaml   ← commit this
      flux/cluster/ks.yaml                        ← commit this
    bootstrap/                                    ← gitignored; used by task bootstrap:apps
    ```

4. Push your changes to git:
   📍 _**Verify** all the `./kubernetes/**/*.sops.*` files are **encrypted** with SOPS_

    ```sh
    git add -A
    git commit -m "chore: add talhelper encrypted secret :lock:"
    git push
    ```
> [!TIP]
> Using a **private repository**? Make sure to paste the public key from `github-deploy.key.pub` into the deploy keys section of your GitHub repository settings. This will make sure Flux has read/write access to your repository.



### Stage 6: Bootstrap Talos, Omni smallest Kubernetes baby cluster

## ---(A) Talos baby cluster
> [!WARNING]
> It might take a while for the cluster to be setup (10+ minutes is normal). During which time you will see a variety of error messages like: "couldn't get current server API group list," "error: no matching resources found", etc. 'Ready' will remain "False" as no CNI is deployed yet. **This is normal.** If this step gets interrupted, e.g. by pressing <kbd>Ctrl</kbd> + <kbd>C</kbd>, you likely will need to [reset the cluster](#-reset) before trying again

1. Install Talos:

    ```sh
    task bootstrap:talos
    ```

    Generates the Talos secret (encrypted with SOPS on first run), renders the
    machine configs, applies them to every node in `nodes.yaml`, bootstraps
    etcd, and writes `kubeconfig` to the repo root.

    Per-node operations afterwards: `task talos:apply-node IP=<ip>`,
    `task talos:upgrade-node IP=<ip>`, `task talos:upgrade-k8s`,
    `task talos:reset`.

    > [!IMPORTANT]
    > `task talos:upgrade-k8s` waits for the node to become `Ready`, and a
    > cluster with no CNI never will. Run it **after** Stage 7
    > (`task bootstrap:apps`), not between here and there — otherwise it fails
    > with `node is not ready / timeout` and looks broken when it is only early.

    > [!TIP]
    > The boot ISO's Talos version does not have to match `talosVersion` in
    > `talos/talenv.yaml`. The installer image in the machine config decides what
    > lands on disk, so bumping the pinned version does not mean re-flashing USB
    > media.

2. Push your changes to git:

    ```sh
    git add -A
    git commit -m "chore: add talhelper encrypted secret :lock:"
    git push
    ```

## ---(B) Omni baby cluster

### 1. Assign Nodes and Create cluster

In Omni UI, Cluster --> Create cluster
    Add machines, assign control-plane / worker roles, then create. Nodes will be `NotReady` (no CNI yet) — this is expected.

### 2. (Option) Generate kubeconfig with ServiceAccount

ferry133's Omni instance is self-hosted inside the `jcom` cluster (not exposed publicly). To use `omnictl` you must port-forward to it first and have a valid Service Account token in `~/.config/omni/env`.

```sh
# 1. Port-forward to the Omni service (requires jcom kubeconfig)
KUBECONFIG=~/coding/jcom/kubeconfig kubectl port-forward -n omni svc/omni 18080:8080 &

# 2. Load OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY
source ~/.config/omni/env
omnictl get clusters   # verify access

# 3. Generate a SA-based kubeconfig for the new cluster (positional output path)
omnictl kubeconfig ~/coding/<repo>/kubeconfig-sa \
  --cluster <cluster-name> \
  --service-account \
  --user ferry133 \
  --ttl 8760h

# 4. Use it explicitly — do NOT copy it over ./kubeconfig
kubectl --kubeconfig ~/coding/<repo>/kubeconfig-sa get nodes
```

> [!IMPORTANT]
> Keep the two files separate. `kubeconfig` is the browser-login (OIDC) version
> and is your way back in when the service-account token expires; overwriting it
> with `kubeconfig-sa` throws away that escape hatch. Point automation at
> `kubeconfig-sa` explicitly with `--kubeconfig`, or
> `export KUBECONFIG=<repo>/kubeconfig-sa`.

If you don't yet have an Omni Service Account or its token has expired, see `CLAUDE.md` ("Omni Service Account 設定") for the full SA-rotation procedure.

> jcom is Talos-from-scratch (not Omni-provisioned) and uses a Talos client-cert kubeconfig — it does **not** need this step.


## Check: Baby k8s cluster is ready for base/extras applicatoin instatllation

- Kubernetes cluster provisioned via [Sidero Omni](https://omni.janncot.com) (see **Omni Setup** below)
- `kubectl` works with the correct kubeconfig (placed at `kubeconfig` in repo root)
- Cloudflare account with domain and API token
- NAS with NFS exports for `storage/nfs-subdir` (`nas_path`) and `claudecode/claude-code`
  (`nas_coding_path`) — both are base apps, so this is **not** optional


###
### Below now, both (A) Talos & (B) operation are the same.
###

### Stage 7: Bootstrap base and selective extra Kubernetes apps 

### 1 Install cilium, coredns, spegel, flux and sync the cluster to the repository state:

Installs Cilium → cert-manager → flux-operator → flux-instance in order:

```sh
task bootstrap:apps
```

After this, Flux takes over and syncs all base apps and selected extras from `jg-base`.
Nodes will become `Ready` once Cilium is deployed.

⚠️ Run this only once. After bootstrap, all changes go through Flux (see below).


## Post-Bootstrap Operations

### Force Flux Sync

```sh
task reconcile   # force Flux to re-sync from git
```

Or manually:

```sh
# Re-sync git source
flux reconcile source git flux-system -n flux-system

# Re-apply a specific Kustomization
flux reconcile ks <ks-name> -n flux-system
```

### After Changing cluster.yaml

```sh
task configure
# Re-apply the updated cluster-secrets:
sops -d kubernetes/components/sops/cluster-secrets.sops.yaml \
  | kubectl apply -n flux-system -f - --server-side
```

### Monitor Deployment

```sh
kubectl get pods --all-namespaces --watch
```

## GitHub Webhook (Optional)

For Flux to reconcile on `git push` instead of polling:

1. Get webhook path:
   ```sh
   kubectl -n flux-system get receiver github-webhook \
     --output=jsonpath='{.status.webhookPath}'
   ```

2. Full URL: `https://flux-webhook.${cloudflare_domain}/hook/<path>`

3. GitHub → Settings → Webhooks → Add webhook:
   - URL: above
   - Token: from `github-push-token.txt`
   - Content type: `application/json`
   - Events: push only

## Verification

```sh
flux check
flux get ks -A
flux get hr -A
```
