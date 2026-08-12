## Why

`README.md` 有完整的 (A) Talos 手動路徑章節，但這個 repo **沒有任何 talos 模板**——`templates/config/` 底下只有 `bootstrap/` 與 `kubernetes/`。README 要求讀者填 `nodes.yaml`（`:164`）並執行 `just bootstrap talos`（`:205`），但此 repo 既無 `nodes.sample.yaml`、無 `nodes.schema.cue`、無 justfile，也無 `.taskfiles/talos/`。整條路徑是死的。

這不只是文件問題，它已經在 repo 裡留下兩個實際缺陷：

- `.taskfiles/template/Taskfile.yaml:123` 引用 `{{.TEMPLATE_NODE_CONFIG_FILE}}`，此變數在本 repo **完全未定義**——`task template:tidy` 會失敗。
- `scripts/bootstrap-apps.sh:140-141` 硬性要求 `TALOSCONFIG` 環境變數與 `talhelper` CLI，但走 Omni 路徑的使用者兩者都用不到，卻被強制安裝與設定。

同時 `④ zero-it-onboarding` 的 task 2.2（修正 `just bootstrap talos`）被這裡擋住：在 Talos 路徑復活之前，那行指令沒有正確版本可以改成。

素材完整存在於 `~/coding/cluster-template`（本 repo 的上游來源），是一次定義清楚的 port，不是從零設計。

## What Changes

- 從上游移植 `templates/config/talos/`：`talconfig.yaml.j2`、`talenv.yaml.j2`、`patches/global/`（machine-network、machine-time、machine-files、machine-kubelet、machine-sysctls）、`patches/controller/cluster.yaml.j2`、`patches/README.md.j2`。
- 移植 `nodes.sample.yaml` 與 `.taskfiles/template/resources/nodes.schema.cue`（每節點必填 name / address / controller / disk / mac_addr / schematic_id，選填 mtu / secureboot / encrypt_disk / kernel_modules）。
- 移植 `.taskfiles/talos/Taskfile.yaml`（`generate-config`、`apply-node`、`upgrade-node`、`upgrade-k8s`、`reset`），並在 `.taskfiles/bootstrap/Taskfile.yaml` 補上 `talos` 任務。
- 在根 `Taskfile.yaml` 補上 `TALOS_DIR`、`TALOSCONFIG` 變數與 `includes: talos:`（本 repo 目前兩者皆無；`.mise.toml:5` 已指向 `talos/clusterconfig/talosconfig`）。
- `makejinja.toml` 的 `data` 加入 `./nodes.yaml`（目前只有 `cluster.yaml` 與 `trello-notifier.yaml`）。
- 修正 `.taskfiles/template/Taskfile.yaml:123` 的懸空變數 `TEMPLATE_NODE_CONFIG_FILE`。
- 讓 `scripts/bootstrap-apps.sh` 的 `TALOSCONFIG` 與 `talhelper` 前置條件**依路徑條件化**，Omni 使用者不再被強制安裝 talhelper。
- 修正 `cluster_svc_cidr` 的預設值矛盾：CUE（`cluster.schema.cue:14`）預設 `10.43.0.0/16`，`plugin.py:130` 卻 `setdefault` 為 `10.96.0.0/16`。兩條路徑的正確預設不同，必須明確表達而非互相覆蓋。
- 更新 `README.md:205` 的 `just bootstrap talos` 為實際存在的 `task bootstrap:talos`，解除 ④ task 2.2 的相依。

## Capabilities

### New Capabilities

- `manual-talos-provisioning`: 手動 Talos 路徑的節點宣告、設定產生與首次啟動流程。
- `talos-node-lifecycle`: 節點層級的日常操作——套用設定、升級 Talos、升級 Kubernetes、重置。
- `provisioning-path-selection`: 兩條供裝路徑（Omni / 手動 Talos）如何共存，以及一條路徑的前置條件不得阻擋另一條。
- `template-rendering-integrity`: 渲染管線自身的一致性——資料來源完整宣告、無懸空變數、預設值不互相矛盾。

### Modified Capabilities

（無。`deployment-profiles` 已規定 `appliance` 僅限 Omni，本 change 提供其對應的手動路徑，不改變該規定。）

## Impact

**`jg-cluster-template`（本 repo）**
- 新增 `templates/config/talos/`（7 個模板檔）
- 新增 `nodes.sample.yaml`、`.taskfiles/template/resources/nodes.schema.cue`
- 新增 `.taskfiles/talos/Taskfile.yaml`；`.taskfiles/bootstrap/Taskfile.yaml` 新增 `talos` 任務
- `Taskfile.yaml` — 新增 `TALOS_DIR` / `TALOSCONFIG` 變數與 talos include
- `makejinja.toml` — `data` 加入 `./nodes.yaml`
- `.taskfiles/template/Taskfile.yaml` — 修正 `:123` 懸空變數
- `.taskfiles/template/resources/cluster.schema.cue`、`templates/scripts/plugin.py` — 修正 `cluster_svc_cidr` 預設矛盾
- `scripts/bootstrap-apps.sh:140-141` — 前置條件條件化
- `README.md:205` — 修正指令
- `.gitignore` — `nodes.yaml` 與 `/talos/` 已列入，無需變更

**已查證的相容性（正面發現）**
- 上游 `templates/config/talos/talconfig.yaml.j2` 已設 `cniConfig: name: none`，`patches/controller/cluster.yaml.j2:12,19` 已設 `coreDNS.disabled: true` 與 `proxy.disabled: true`——與 `jg-base` 的預期（自行安裝 Cilium + CoreDNS、不用 kube-proxy）完全一致，也與 README 給 Omni 使用者的 MachineConfigPatch 相同。此處不需要改寫。
- 上游 `cluster.schema.cue` 的欄位是本 repo 的子集，本 repo 為超集，因此 cluster 層級 schema 不缺任何 Talos 路徑需要的欄位。

**與其他 change 的關係**
- 解除 `zero-it-onboarding` task 2.2 的阻塞。
- `deployment-profiles` 的 `appliance` 禁止手動 Talos；本 change 需與該規則對齊，`prosumer` / `full` 才可使用。
- 手動 Talos 路徑需要 `cluster_api_addr`（talconfig 的 endpoint 與 VIP），與 `deployment-profiles` 中「appliance 不需要該欄位」的決定並行不悖。

**Spike 結論（2026-08-09 實測，全數結案）**
- 上游模板與本 repo pin 的 Talos `1.12.4` / talhelper `3.1.5` **完全相同**，無相容性缺口。
- `talenv.yaml.j2` 的版本由該檔硬編並帶 renovate 註解，**刻意不與 `.mise.toml` 對齊**——後者 pin 的是 CLI（talosctl / kubectl），前者是叢集元件（installer image / kubelet）。本 repo 無 `.renovaterc.json5`，需手動 bump。
- `cluster_svc_cidr` 兩條路徑的正確值確實不同（手動 `10.43.0.0/16`、Omni `10.96.0.0/12`），因此改為**必填無預設**，並讓 `coredns_cluster_ip` 由它推導。
- 供裝路徑改以必填欄位 `provisioning_path: "omni" | "talos"` 表達；由 `nodes.yaml` 存在與否推導已證實不可行。

詳見 `design.md` D3 與 Open Questions。
