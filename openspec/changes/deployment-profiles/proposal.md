## Why

目前 `cluster.yaml` 有 12 個必填欄位，其中 4 個 LB/VIP 位址要求填寫者知道自家 LAN 上哪些 IP 是空的、3 個 NAS 欄位要求已有 NFS 匯出的 NAS。這些都不是零 IT 客戶答得出來的資訊，也不是遠端 agent 在機器上線前推導得出來的——結果就是每一台交付都必須有人到現場或問一輪，無法自動化。

同時，現有預設把 PostgreSQL 的 PVC 放在 NFS（`sc-nas`）上，這在 fsync 與鎖語意上本來就不該做；而單節點 appliance 一旦改用節點本機碟，資料就完全沒有備援。

這個 change 是後續三個 change（`revive-talos-path`、`factory-agent`、`zero-it-onboarding`）的地基：沒有 profile 軸，就沒有「零 IT 客戶版 SOP」可寫，factory agent 也沒有可自動填入的欄位集合。

## What Changes

- 新增 `deployment_profile` 軸（`appliance` / `prosumer` / `full`），CUE schema 依 profile 決定哪些欄位必填。`appliance` 的客戶端輸入降到 0 個必填欄位（其餘由 factory agent 推導或供給）。
- 新增 `storage_backend` 軸（`local-path` / `nfs`）。**BREAKING**：`nas_server` / `nas_path` / `nas_coding_path` 由無條件必填改為 `storage_backend: nfs` 時才必填。既有 cluster.yaml 需補 `storage_backend: nfs` 才能通過 `cue vet`。
- LAN LoadBalancer 位址從 3 個壓成 1 個共用位址（`envoy-internal` + `mqtt` + fallback 的 `k8s-gateway`，port 不重疊）。不需要 LAN 可達的 `cluster_api_addr` 與 `cloudflare_gateway_addr` 改用固定的 `10.9.9.x`。
- LAN 位址取得方式從「人工挑選並填入」改為「自動探測後產出 `CiliumLoadBalancerIPPool`」。介面設計成之後可替換為 DHCP lease-holder 而不動上層。
- 內網服務 DNS：新增第二份 external-dns 實例，把掛在 `envoy-internal` 的 HTTPRoute 發佈為**不經 Cloudflare proxy 的 A 記錄**指向內網 LB IP。hostname 維持扁平（不引入 `.lan.` 前綴）。`k8s-gateway` 由預設元件降級為「偵測到 DNS rebinding protection 後才啟用」的 fallback。
- 儲存改依資料型態分層：DB（postgres、agent memory）走 block/local-path，媒體與備份走 NFS。修正 `jg-base` 中 postgres backup PVC 的 `storageClassName: ""`（在 appliance 上會永久 Pending）。
- `appliance` profile 強制離線備份：`pg_dump` + 工作區以叢集 age 公鑰加密後推送至 Cloudflare R2，由既有的 `monitoring/daily-check` CronJob 監看備份新鮮度；`age.key` 納入 escrow。

## Capabilities

### New Capabilities

- `deployment-profiles`: profile 與 storage backend 兩條軸的定義、各 profile 的必填欄位集合、各 profile 部署哪些 base app。
- `lan-address-allocation`: 叢集如何取得 LAN 上的 LoadBalancer 位址（共用、探測、pool 產出），以及不需 LAN 可達的位址如何配置。
- `internal-service-dns`: 掛在 `envoy-internal` 的服務如何被 LAN 用戶端解析，含公開 A 記錄模式、rebinding protection 偵測與 `k8s-gateway` fallback。
- `cluster-storage-tiers`: 依資料型態決定儲存層的規則，以及各 profile 的預設 storage class。
- `appliance-backup`: 單節點 appliance 的離線備份、還原與 `age.key` escrow。

### Modified Capabilities

（無。`openspec/specs/` 目前為空，本 change 建立的皆為新 capability。）

## Impact

**`jg-cluster-template`（本 repo）**
- `.taskfiles/template/resources/cluster.schema.cue` — 新增兩條軸與 conditional required
- `cluster.sample.yaml` — 依 profile 重組，appliance 區塊置頂
- `templates/config/kubernetes/components/sops/cluster-secrets.sops.yaml.j2` — 新增 R2 / 備份相關變數
- `templates/config/kubernetes/flux/cluster/ks.yaml.j2` — 依 profile 決定渲染哪些 Kustomization
- `templates/scripts/plugin.py` — profile 預設值與衍生欄位（含 `10.9.9.x` 固定值）

**`jg-base`**
- `apps/base/network/cloudflare-dns` — 新增 internal external-dns 實例（`txtPrefix` / `txtOwnerId` 必須與現有的 `k8s.` 分離，否則 `policy: sync` 會互刪記錄）
- `apps/base/network/k8s-gateway` — 改為條件啟用
- `apps/base/network/envoy-gateway`、`apps/extras/default/mqtt` — LB IP 共用註記（兩邊都需 `sharing-cross-namespace`）；appliance 下 `envoy-external` 改 ClusterIP
- `apps/base/kube-system/cilium/app/networks.yaml` — pool 從 `cidr: ${NODE_CIDR}` 收窄；apiVersion `v2alpha1` → `cilium.io/v2`
- `apps/extras/default/postgres/app/backup.yaml` — storageClassName 修正
- `apps/base/monitoring/daily-check` — 增加備份新鮮度檢查
- 新增備份 CronJob 與 LAN 位址探測元件

**既有叢集**
- jcom、jg-jiahd 等既有 cluster.yaml 需補 `deployment_profile: full` + `storage_backend: nfs`；不補會在 `task configure` 的 `cue vet` 階段失敗（fail fast，不會產出錯誤設定）。

**已驗證**
- Cilium LB-IPAM 的 `lbipam.cilium.io/sharing-key` + `sharing-cross-namespace` 跨 namespace 共用可行（2026-08-09 於 jg-jiahd, Cilium v1.19.1 實測）。內網位址數確定為 1。詳見 `design.md` D3。

**待驗證（spike，不得當成既定事實寫入 spec）**
- 服務同時匹配窄 pool 與寬 pool 時 Cilium 的選擇順序（須在 scratch 叢集測）。
- Envoy Gateway 的 `spec.infrastructure.annotations` 是否傳導 `sharing-key`（既有 `lbipam.cilium.io/ips` 已證實傳導，屬合理推論但未直接驗證）。
- DNS rebinding protection 的可靠偵測方式。
- Cloudflare DNS 接受 RFC1918 A 記錄的行為（僅 DNS-only，不可 proxied）。
