## Why

`jcom` 已經無法接收模板更新，而模板也無法從 jcom 取回它獨有的修正。這不是「模板 + 少量客製化」，是兩支互相分岔的血脈——2026-08-09 逐檔比對後量化如下（相對 `revive-talos-path` 動工前的模板 HEAD）：

```
templates/config/kubernetes/flux/cluster/ks.yaml.j2   54 行
.taskfiles/template/Taskfile.yaml                      31 行
templates/scripts/plugin.py                            22 行
.taskfiles/bootstrap/Taskfile.yaml                     14 行
scripts/bootstrap-apps.sh                              10 行
Taskfile.yaml                                           4 行
makejinja.toml                                          2 行
```

分岔是**雙向**的。`revive-talos-path` 已經把模板往 jcom 的方向拉回了一部分（talos 工具鏈、`TEMPLATE_NODE_CONFIG_FILE`、`encrypt-secrets` 含 `TALOS_DIR`、kubeconform 接線——後兩者正是比對 jcom 才發現模板漏掉的），但仍剩下三類無主的差異：

1. **jcom 有、模板沒有**：`spegel_enabled` / `cilium_bgp_enabled` / `cilium_loadbalancer_mode` 的 plugin 邏輯，以及 `01-apps.yaml.j2` 對 `spegel_enabled` 的使用。
2. **模板有、jcom 沒有**：`trello-notifier` 作為 makejinja data 檔（jcom 無此檔，套用模板的 `makejinja.toml` 會讓渲染直接中止）；`bootstrap-apps.sh` 改用固定 namespace 清單（jcom 仍是舊的「掃 `kubernetes/apps/*/`」版本，在現行目錄結構下會取到錯誤的 namespace）。
3. **jcom 專屬的求生 patch**：`ks.yaml.j2` 裡手寫的 Spegel `suspend: true`。

第 3 類指向真正的根因：**`kubernetes/flux/cluster/ks.yaml` 是渲染產物，但每個叢集的例外都被手寫進它的 `.j2` 模板裡**。jg-jiahd 的 QUIC workaround 也在同一個檔案。沒有任何機制把「這是本叢集的合法例外」和「這是還沒同步的舊版本」區分開，所以每加一個 workaround，該叢集就更難再吃模板更新——分岔是這個機制必然的產物，不是誰疏忽。

而 Spegel 那個 patch 記錄的是一次真實事故，且它預告了一個尚未發生的問題：`jg-base/kubernetes/apps/base/kube-system/kustomization.yaml:12` **無條件**部署 Spegel，jcom（單節點）上它起不來，臨死前寫入 `hosts.toml` 把所有 registry 導向死掉的埠，導致全叢集未快取的 image 都拉不動。`deployment-profiles` 的 `appliance` profile 正是單節點——每一台 appliance 都會重現這個故障。

## What Changes

- 建立**分岔清冊**：逐項把差異分類為「收進模板」「從叢集移除」「保留為合法的 per-cluster 例外」，每一項都要有理由，不留「不知道為什麼在這裡」的項目。
- 收進模板：單節點安全性的 gating（Spegel 是已知案例），以及比對後認定模板該有的 plugin 邏輯。
- 從 jcom 移除：已被模板較新做法取代者（例如 `bootstrap-apps.sh` 的 namespace 掃描）。
- 新增 **per-cluster 例外的正式表達方式**。目前唯一的做法是手改 `ks.yaml.j2`，這正是造成分岔的機制。**BREAKING**：既有的手寫 patch（jcom 的 Spegel suspend、jg-jiahd 的 QUIC workaround）需遷移到新機制。
- 讓 jcom 回到「能吃模板更新」的狀態，並以一次實際的模板同步驗證之。
- 單節點安全性納入 profile：`appliance` 不得部署在單節點上會自我破壞的元件，且不得靠 per-cluster patch 達成。

## Capabilities

### New Capabilities

- `template-lineage-reconciliation`: 分岔清冊、分類規則，以及「jcom 能重新消費模板更新」這個終局狀態的定義與驗證方式。
- `per-cluster-override-contract`: 叢集如何宣告合法的本地例外，使其可見、可稽核、且不阻擋模板更新。
- `single-node-cluster-safety`: 在單節點上會自我破壞的元件必須由設定 gating，而非事後 patch。

### Modified Capabilities

（無。本 change 建立的皆為新 capability；`deployment-profiles` 的 Spegel gating 需求以 task 形式回報給該 change，不在此處改寫其 spec。）

## Impact

**`jcom`（user repo）**
- `cluster.yaml` — 補 `provisioning_path: "talos"` 與 `cluster_svc_cidr: "10.43.0.0/16"`
- `templates/config/kubernetes/flux/cluster/ks.yaml.j2` — 手寫的 Spegel suspend 遷移到新機制
- `scripts/bootstrap-apps.sh`、`makejinja.toml`、`.taskfiles/` — 與模板對齊
- 首次同步後需完整驗證渲染結果

**`jg-jiahd`（user repo）**
- QUIC workaround 同樣遷移到新機制（目前是 `ks.yaml.j2` 的手寫 patch）

**`jg-cluster-template`**
- `templates/scripts/plugin.py` — 收回被判定該有的衍生旗標
- `templates/config/bootstrap/helmfile.d/01-apps.yaml.j2` — 單節點 gating
- 新增 per-cluster 例外的表達機制與其文件

**`jg-base`**
- `kubernetes/apps/base/kube-system/kustomization.yaml` — Spegel 改為可由設定停用

**與其他 change 的關係**
- `revive-talos-path`：其 task 5.8 即本 change 的起點；5c.1 / 5c.2 是比對 jcom 得到的成果。
- `deployment-profiles`：新增 task 1.0（appliance 單節點必須關閉 Spegel）。本 change 提供其所需的 gating 機制。

**待驗證（spike，不得當成既定事實寫入 spec）**
- jcom 的 `ks.yaml.j2` 那 54 行裡，有多少是真正的 per-cluster 例外、多少只是舊版本殘留。
- `cilium_bgp_enabled` / `cilium_loadbalancer_mode` 是否仍有消費端，或已是死碼。
- Spegel 在多節點叢集上的實際效益是否值得保留（若否，直接從 jg-base 移除比 gating 簡單）。
- per-cluster 例外的機制形式：Flux 的 post-build substitution、獨立的 overlay 目錄、或 cluster.yaml 驅動的條件渲染。
