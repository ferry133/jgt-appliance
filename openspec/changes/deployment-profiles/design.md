## Context

這個 repo 交付的是**隱私驅動的地端叢集**：客戶之所以要這台機器，正是因為 homebridge、MQTT、IoT、存放公司知識的 PostgreSQL 這些東西不能放雲端。所以 LAN 可達性是產品需求，不是可以優化掉的實作細節——設計初期曾假設「ingress 全部走 Cloudflare Tunnel，LB IP 只是內部記帳」，這個假設在確認 `jg-base` 現況後作廢，本文件記錄修正後的方向。

現況（已查證）：

```
jg-base/kubernetes/apps/base/network/
  envoy-gateway/app/envoy.yaml:55   CLOUDFLARE_GATEWAY_ADDR   ← 只有叢集內 cloudflared 連
  envoy-gateway/app/envoy.yaml:85   CLUSTER_GATEWAY_ADDR      ← LAN 必須可達
  k8s-gateway/app/helmrelease.yaml:19  CLUSTER_DNS_GATEWAY_ADDR  ← LAN 必須可達
  cloudflare-dns  --gateway-name=envoy-external, policy: sync, txtPrefix: k8s.
jg-base/kubernetes/apps/extras/default/
  mqtt/app/tcp-gateway.yaml:10      MQTT_LB_IP                ← IoT 直連，LAN 必須可達
  homebridge/app/helmrelease.yaml:31  hostNetwork: true       ← 用節點 IP，不佔 LB IP
```

也就是：內網服務名稱目前**只存在於 `k8s-gateway` 的回答裡**，LAN 用戶端必須把 DNS 指向它才找得到。對零 IT 客戶而言這需要登入路由器改 DHCP option 6，是不可行的一步。

約束：
- 客戶端不可要求任何路由器設定、任何裝置設定。
- 既有叢集（jcom、jg-jiahd 等）必須能繼續運作，遷移成本要低且失敗要早。
- 不引入超出既有工具鏈（Cilium / external-dns / cert-manager / SOPS+age / Flux / daily-check）的新外部相依。

## Goals / Non-Goals

**Goals:**
- `appliance` profile 下，客戶必填欄位為 0；其餘由 factory agent 或渲染期推導。
- 消除「必須知道 LAN 上哪些 IP 空著」這個前置知識。
- 內網服務在**不改動客戶路由器與裝置**的前提下，於 LAN 上可用名稱存取。
- 把資料庫從 NFS 移到 block，並補上單節點必然缺少的備援。
- 既有 `full` 叢集行為不變，遷移只是補兩個宣告欄位。

**Non-Goals:**
- 不做 `factory-agent`（change ③）與 README 拆分（change ④），本 change 只鋪地基。
- 不實作 DHCP lease-holder，只保證介面可替換。
- 不處理 `revive-talos-path`（change ①）。
- 不為 appliance 提供高可用；appliance 明確是單節點，備份是它的容錯手段。
- 不改變 `extras:` 的語意與現有 extras 的行為。

## Decisions

### D1. 兩條正交軸，而非單一 profile 列舉

`deployment_profile`（客戶型態）與 `storage_backend`（儲存基礎設施）分開。理由：有 NAS 的客戶不見得要 `full` 的手動控制權，反之亦然。若壓成單一列舉，每新增一種組合就要多一個 profile 名稱。

*Alternative considered*：單一 `profile` 列舉含儲存語意。捨棄，因為組合會爆炸且語意混在一起。

### D2. `deployment_profile` 不給 schema 預設值

CUE 上不設 `*"full" | ...`。既有 `cluster.yaml` 會在 `cue vet` 階段直接失敗，而不是被預設值靜默套進某個 profile 後渲染出錯的東西。`task configure` 的流程是「validate → render → encrypt」，驗證失敗時 `kubernetes/` 不會被寫入，所以 fail fast 是安全的。

*Alternative considered*：預設 `full` 讓既有叢集零遷移。捨棄——靜默預設會讓「這台是哪種客戶」變成隱含知識，而這正是後續 factory agent 要據以決策的欄位。

### D3. LAN 位址不是「避開」，而是「壓到 1 個」

三個 LAN 可達服務的 port 完全不重疊（80/443、1883、53），可共用同一個位址。**已於 jg-jiahd（Cilium v1.19.1）實測確認**，見下方 spike 結論。

不需要 LAN 可達的兩個不是「搬到保留區段」，而是**直接不存在**：

- `cloudflare_gateway_addr`：cloudflared 的 config 指向 `https://envoy-external.network.svc.cluster.local:443`（`cloudflare-tunnel/app/helmrelease.yaml:80`），走 ClusterIP DNS。jg-jiahd 上 `envoy-external` 佔著 `10.9.9.5` 卻沒有任何東西連它。appliance 下 `envoy-external` 改 ClusterIP 即可。
- `cluster_api_addr`：Omni 自己 proxy，appliance 下不需要 LB 位址。

（初稿曾提議把這兩者放進固定的 `10.9.9.0/24` 保留區段。**已捨棄**——`10.9.9.0/24` 正是 jg-jiahd 自己的 node CIDR，拿一個自家在用的網段當「保證不撞」的保留區在語意上是錯的；而且既然兩者都不需要位址，保留區本身就是多餘的。）

「找 1 個空位址」與「找 4 個空位址」是不同難度的問題，這一步把後續探測的失敗率降一個數量級。

*Alternative considered*：全部走 Tunnel、不要 LAN 位址。**已作廢**——與地端隱私定位直接衝突，IoT 與 HomeKit 需要 L2 相鄰。
*Alternative considered*：把叢集放到獨立網段（雙網卡當路由器）。捨棄——appliance 會變成客戶網路的單點，重開機順序錯誤就整網斷線，對零 IT 是不可接受的失敗模式。
*Alternative considered*：改用 Envoy Gateway 的 `mergeGateways`，讓 internal gateway 與 tcp-gateway 共用一個 Envoy Service。捨棄——merge 的範圍是整個 GatewayClass，會把 `envoy-external` 一起併進來；要分開就得拆兩個 GatewayClass，比 sharing-key 重得多。

#### Spike 1.1 實測結論（jg-jiahd, Cilium v1.19.1, 2026-08-09）

測試以專用 pool（`192.0.2.0/29`, RFC 5737 TEST-NET-1）+ `serviceSelector` 隔離，兩個測試 Service 明確指定位址，全程未佔用任何真實 LAN 位址；production 的四個 LoadBalancer 位址在測試前後完全一致，測後資源已刪除無殘留。

| 驗證項 | 結果 |
|---|---|
| 跨 namespace 共用同一位址 | ✅ 兩個不同 namespace 的 Service 同時取得 `192.0.2.1` |
| `sharing-cross-namespace` 只掛單邊 | ✅ 失敗且**可觀測**：`cilium.io/IPAMRequestSatisfied=False`，reason `already_allocated_incompatible_service`，訊息 `different and not permitted namespace`；另一邊不受影響 |
| port 衝突（位址受約束時） | ✅ **不會**靜默多配位址：衝突方 unassigned，同樣回報 `IPAMRequestSatisfied=False`，訊息 `same port and protocol` |
| CRD 版本 | 叢集實際服務並儲存為 `cilium.io/v2`；`jg-base` 的 manifest 仍寫 `v2alpha1`（仍被接受，但應更新） |

關鍵推論：文件所述「port 衝突時多配一個 IP 進 sharing key 的集合」只適用於**自動配發且有多餘位址可拿**的情況。一旦位址被約束（明確指定，或 pool 只含單一位址），衝突就退化成 `IPAMRequestSatisfied=False` 這個乾淨的訊號——**收窄 pool 因此不只是精簡，它是把靜默失敗轉成可觀測失敗的執行機制**，而 `cilium.io/IPAMRequestSatisfied` 正好是 daily-check 可以監看的條件。

未於本次實測涵蓋（風險過高或超出範圍，移至 scratch 叢集驗證）：
- 服務同時匹配「窄 pool」與「涵蓋整個 node CIDR 的寬 pool」時的選擇順序。未測是因為若 Cilium 選了寬 pool，自動配發會取該區段第一個可用位址（`allowFirstLastIPs: "No"` 下即 `10.9.9.1`），那極可能是閘道器，會在真實 LAN 上造成 ARP 衝突。
- 單一位址 pool 下的自動配發是否落到 Pending（推論成立，但未實測）。
- Envoy Gateway 的 `spec.infrastructure.annotations` 是否會把 `sharing-key` 傳導到產生的 Service。本次測的是原生 Service。既有 production 已證實 `lbipam.cilium.io/ips` 經此路徑傳導成功，而傳導是通用的 annotation 複製，因此推論成立——但仍是推論。

### D3a. 現有 pool 涵蓋整個 node CIDR 是既有風險（2026-08-11 實測確認，見 D23）

`jg-base/kubernetes/apps/base/kube-system/cilium/app/networks.yaml` 的 pool 是 `cidr: ${NODE_CIDR}`，實測 jg-jiahd 即為 `10.9.9.0/24`。今天沒出事只因為每個 Service 都用 `lbipam.cilium.io/ips` 釘死位址；任何一個漏掉註記的 Service 都會從整個客戶 LAN 隨機取一個位址並經 L2 announcement 宣告，可能與真實裝置衝突。

本 change 收窄 pool 同時修掉這個既有風險。對 `full` profile 是行為改變（需明確列出該叢集實際使用的位址），必須逐叢集確認後再套用。

### D4. 先 ARP 探測，介面預留 DHCP lease-holder

ARP 探測只能證明「此刻沒人用」，證明不了「不在 DHCP pool 內」——當下關機的裝置回來就會撞號。根治做法是讓路由器自己配（合成 MAC 發 DHCPDISCOVER/REQUEST 並持續續租），但那是新元件。

折衷：先做探測，但把唯一對外契約定義為產出 `CiliumLoadBalancerIPPool`。之後替換實作不需動 Cilium 設定、Service 註記、模板或 CUE。撞號則靠持續監看 + 併入日常健檢回報，不假裝不會發生。

### D5. hostname 維持扁平，不引入 `.lan.`

內外之分已由 HTTPRoute 的 `parentRefs` 表達，那是 operator 看的地方。放進 URL 等於放進使用者看的地方，而使用者是搬遷成本的承受方：書籤、IoT/MQTT broker 位址、HomeKit 配對、Auth0 Allowed Callback URLs（`cluster.sample.yaml` 已逐 instance 記錄）、憑證 SAN 全都要改，而且服務在內外之間搬動會從「改一行 `parentRefs`」變成 breaking change。

關鍵觀察：**沒有名字衝突需要解**。每個 hostname 只會掛在一個 gateway 上，不會同時需要內外兩種答案，所以扁平名稱直接發公開 A 記錄即可。

*Alternative considered*：`app.lan.<domain>`。捨棄，理由如上。

### D6. 內網名稱走公開 DNS 的不 proxy A 記錄，`k8s-gateway` 降為 fallback

新增第二份 external-dns（`--gateway-name=envoy-internal`），把內網 route 發成指向 LAN 共用位址的 A 記錄，且必須關閉 proxy（Cloudflare 無法 proxy RFC1918）。LAN 用戶端用路由器給的任何 resolver 都能解出來，**不需要動路由器、不需要動裝置**。

兩份 external-dns 都是 `policy: sync` 且同一個 zone，因此 `txtPrefix` 與 `txtOwnerId` 必須分離，否則會互刪對方記錄——這是本設計最容易踩的實作陷阱。

`k8s-gateway` 不砍，改為偵測到 DNS rebinding protection 後才啟用。因為名稱扁平，啟用時回答的是同一組名稱、同一個位址，**切換不需要任何客戶端變更**，兩種模式可雙向移動。

揭露面：cert-manager 簽發的每個 hostname 本來就會進 Certificate Transparency log，所以發佈內網名稱不構成新的洩漏；回的是 RFC1918，外部解得到但連不到。

### D7. 資料庫走 block，拒絕 NAS-Docker 逃生梯作為預設

PostgreSQL 跑在 NFS 在 fsync 與鎖語意上本來就不該做，改 local-path 是修正而非妥協。容量真的不足時的正解是**更大的本機 NVMe**，或以 CSI 提供 NAS 的 block（iSCSI），而不是把 DB 搬到 NAS 上的 Docker。

搬到 NAS Docker 的代價不在效能，在於它**離開受管邊界**：不在 Flux、agent 管不動、daily-check 看不到、交接封裝涵蓋不到——而 DB 恰好是最不能出事的東西。它可以是明示的逃生梯，但必須標註「這一塊不在受管範圍」。

同時修正 `jg-base/kubernetes/apps/extras/default/postgres/app/backup.yaml:13,26` 的 `storageClassName: ""`（關閉動態供裝，在無預建 PV 的 appliance 上會永久 Pending）。

### D8. agent 工作區與 agent 記憶分層

工作區檔案可重建，放 local-path 即可。agent 累積的每客戶 context 不可重建，放進資料庫層，因而自動被備份涵蓋。`nas_coding_path` 保留為 optional（jcom / jg-jiahd 仍在用），不移除。

### D9. 備份重用既有零件

`pg_dump` + 工作區 → 以叢集 age 公鑰加密 → Cloudflare R2（每叢集本來就有 CF 帳號，S3 相容，免費額度足夠）。新鮮度由既有的 `monitoring/daily-check` 一併回報，斷了就經由既有的 healthchecks.io dead-man switch 浮上來。整條鏈沒有新的外部相依。

以叢集自己的公鑰加密，代表 R2 上的內容連 operator 也解不開，符合隱私定位；解密能力隨 `age.key` 移轉，天然接上 `task handover`。

### D10. `appliance` 僅限 Omni

手動 Talos 需要每節點的 IP、網卡與磁碟選擇器，零 IT 客戶給不出來。這個組合在驗證期就拒絕，而不是等到 bootstrap 才失敗。

### D11. Base app 的 gating 由 per-user repo 生成 suspend patch

`jg-base` 把每個 base app 無條件列在 `apps/base/*/kustomization.yaml` 裡，**Flux 無法從那一端拒絕建立 Kustomization**。所以「這個 profile 不要這個 base app」只能從 per-user repo 表達。

機制沿用 jcom 已驗證可行的作法：在 `cluster-apps-base` 的 patches 內對子 Kustomization 設 `suspend: true`。差別在**來源**——jcom 是手寫進 `ks.yaml.j2`，這裡是**由 `cluster.yaml` 推導生成**。同樣的 YAML，但一個是漂移、一個是宣告式設定，正好是 `reconcile-jcom-lineage` 的 `per-cluster-override-contract` 要求的分野。

patch 刻意只設 `suspend` 這一個純量欄位。jcom 的註解記錄過原因：**第二個 strategic merge 若設了 `spec.patches` 會整個取代該列表**，把上面通用的 HelmRelease 策略 patch 靜默吃掉。

目前 gating 兩項：

```
nfs-client-provisioner   storage_backend != 'nfs'
spegel                   is_single_node
```

#### 為什麼不是「從 extras 過濾」

初版實作誤以為 `storage/nfs-subdir` 是 extra，於是在 extras 迴圈裡把它濾掉——但它在 jg-base 是 **base app**（`apps/base/storage/nfs-subdir/ks.yaml`），從來不在 extras 裡。過濾器濾了一個不存在的東西，而當初的測試用一份「把它塞進 extras」的設定，於是測過了卻測錯對象。2026-08-11 在真實叢集上才發現：`local-path` 叢集照樣部署它並失敗，錯誤訊息精確指出原因——`NAS_SERVER` / `NAS_PATH` 被渲染為空字串，Deployment 因 `nfs.server: Required value` 建不起來。

#### suspend 不會清理既有資源

實測確認的語意：`suspend: true` 讓 Flux **停止 reconcile**，但**不會移除已部署的資源**。在測試叢集上 suspend 生效後 spegel pod 仍在跑；手動刪除 HelmRelease 之後，Flux 兩分鐘內沒有重建。

所以：
- **新叢集**：suspend 從第一次同步就在，該元件從未被部署。
- **既有叢集**：suspend 只防止重建，已部署的要手動刪除。

jcom 的註解其實早就寫了這件事（「stops reconciling/**recreating** it」），只是把它當成既定知識而非遷移步驟。

#### 既有叢集的遷移步驟（2026-08-11 於 jgt-omni 實測）

先看清楚 suspend 之後留下了什麼。以 `nfs-client-provisioner` 為例，它的 inventory 是 HelmRelease + HelmRepository，但 helm 另外建了 ServiceAccount 與 **StorageClass `sc-nas`，而且是叢集的 default** ——一台 `local-path` 叢集的預設儲存指向一個不能用的 NFS provisioner，這比「一個 pod 失敗」嚴重得多。

**刪除被 suspend 的 Kustomization 不會清理資源。** 實測：刪掉之後 HelmRelease 與 StorageClass 都還在，`prune: true` 沒有生效——suspend 擋掉了刪除時的 prune finalizer。所以這條路是無效的，而且它看起來像成功（Kustomization 確實消失了）。

有效的做法是**直接刪除 HelmRelease**，讓 helm-controller 執行 uninstall：

```
kubectl -n <ns> delete hr <release>     → helm uninstall 連帶清掉它建立的
                                          StorageClass / ServiceAccount 等
```

驗證結果：

```
刪 Kustomization        → hr 仍在、sc 仍在      ✗ 無效
刪 HelmRelease          → hr=0、sc=0            ✓ helm uninstall 清乾淨
強制 cluster-apps-base   → Kustomization 重建
reconcile                  但 suspend=true 守住，hr=0 sc=0 維持 ✓
```

最後一列是關鍵：`cluster-apps-base` 會把子 Kustomization 重新建出來（它自己沒有被 suspend），但重建出來的帶著 suspend patch，所以不會重新部署。順序因此是 **先刪資源、再讓 suspend 擋住重建**，而不是反過來。

（另注意 `cluster-apps-base` 的 interval 是 1h，所以刪掉子 Kustomization 之後不會立刻重建——實測 100 秒內都沒有動靜。除錯時容易誤判為「已經永久移除」。）

### D12. Omni 路徑無法在渲染期得知節點數

`is_single_node` 在 appliance（定義上單節點）與手動路徑（節點清單具權威性）可以推導，但 Omni 叢集的 `nodes` 恆為 `[]`。新增可選欄位 `single_node`，明寫者優先；未宣告時**假設有 peer**——猜錯只是多跑一個本來能用的元件，反向猜錯則會靜默停掉需要的元件。

### D13. `storage_backend` 的兩個值蓋不住三種情境

`local-path` 把兩個後果完全不同的情境混成同一個值：

| | local-path 是否適當 |
|---|---|
| 單節點無 NAS | ✓ 正確且完整 |
| **多節點無 NAS** | ⚠ 可用但降級——正解是複製式儲存 |

node-local 的 PV 帶著指向該節點的 affinity。多節點上這會**在第一次排程時**把每個有狀態工作負載悄悄釘死在一台機器：pod 排不到別台、那台碟壞了資料與服務一起沒。表面上有三個節點，實際上 postgres 只活在其中一台。

`cluster-storage-tiers` 原本只要求「DB 用 block-backed storage」，而 `local-path` 技術上就是 block-backed——多節點叢集選它會**通過所有檢查**，直到某次節點維護才發現起不來。spec 缺的是「block-backed 但不可跨節點漂移」這個維度。

正解是 Longhorn / Rook-Ceph 這類複製式 block storage。README Stage 1 提過它們，但 **jg-base 完全沒有實作**（只有 nfs-subdir 與 local-path-provisioner）。實作一整套複製式儲存範圍不小，因此分兩步：

- **現在**：CUE 拒絕「`local-path` + 多節點」除非明寫 `accept_node_pinning: true`。把沉默的降級變成明示的選擇。
- **之後**：在 jg-base 實作複製式儲存並加入第三個 `storage_backend` 值。jg-jiahd 是 3 節點，所以這不是假想需求。

#### 實作上的一個 CUE 陷阱

要求「使用者必須明寫某個值」比看起來難。三次嘗試都被 CUE 自己滿足了：

```
accept_node_pinning: true          → CUE 直接賦值，永遠通過
_hidden: accept_node_pinning & true → hidden field 不受 concreteness 檢查
accept_node_pinning?: "字面值"       → 引用時取到具體的字面值，仍然通過
```

有效的是**讓宣告的約束保持非具體**，再用矛盾拒絕不要的值：

```cue
accept_node_pinning?: bool          // 非具體
if single_node == false {
    accept_node_pinning: bool       // 缺值 → incomplete → 拒絕
    if accept_node_pinning == false {
        accept_node_pinning: _|_    // false → 矛盾 → 拒絕
    }
}
```

通則是：**`cue vet` 檢查的是「資料是否具體」，所以任何在 schema 裡寫死的值都會讓要求自我滿足**。

### D14. `local-path` 路徑上，claude-code 有一整條未被走過的 NFS 假設鏈

2026-08-11 在 jgt-omni（單節點、無 NAS）第一次真的把預設 instance `im` 跑起來，中間撞到五道牆。它們不是五個獨立 bug，是**同一個假設的五個位置**：claude-code 是在有 NAS 的叢集上長出來的，所以「有 NFS」被寫死在各處。

| # | 位置 | 症狀 | 修法 |
|---|---|---|---|
| 1 | `helmrelease.yaml.j2` 的 `coding` volume 硬寫 `type: nfs` | `server`/`path` 渲染成空字串 → chart schema 直接拒絕，**整個 release 裝不起來**（不只是少一個掛載） | 用 `nas_coding_path` 包起來 |
| 2 | 兩個 PVC 硬寫 `storageClass: sc-nas` | 該 class 在 local-path 叢集不存在 → PVC 永遠 Pending | 改用 `default_storage_class` |
| 3 | 沒有任何 default StorageClass | `storage/local-path-provisioner` 是 opt-in extra（見 2c.6） | `ks.yaml.j2` 依 `storage_backend` 自動加入 |
| 4 | `replicas: 0` × `WaitForFirstConsumer` | Helm 等 PVC 綁定，但沒有 pod 就不會綁 → 逾時後 release 永久失敗 | `install`/`upgrade` 加 `disableWait: true` |
| 5 | `storage` namespace 無 PodSecurity 標籤 | Talos 預設 `baseline` 擋掉 provisioner 的 hostPath helper pod | jg-base `05b1501`：標為 `privileged` |

兩個值得單獨記住的：

**#4 是兩個各自正確的決定相撞。** `replicas: 0` 是刻意的安全姿態（不常駐一個 root shell），`WaitForFirstConsumer` 是 node-local 儲存的正常行為——延後綁定才知道要綁哪台。湊在一起就是「Helm 等一個依定義不會發生的事件」。NFS 用 `Immediate` 綁定，所以**這個相撞在有 NAS 的叢集上完全不會出現**。

**#5 屬於「每個元件看起來都對」的那類故障。** provisioner pod `1/1 Running`、Kustomization `Ready=True`、StorageClass 存在——但 PVC 永遠 Pending，因為失敗發生在一個短命的 helper pod 上，錯誤只留在 PVC 的 event 裡：

```
failed to provision volume with StorageClass "local-path":
  pods "helper-pod-create-pvc-…" is forbidden:
  violates PodSecurity "baseline:latest": hostPath volumes (volume "data")
```

**通則**：這五道全部只在 `storage_backend: local-path` 上出現，也就是 **appliance profile 的標準組態**。有 NAS 的叢集一道都碰不到——所以這條路徑在此之前從未被端到端走過。②（以及後續每個 profile）的驗收必須包含**在目標 profile 上實跑**，不能只驗 `task configure` 的輸出：前四道在渲染階段全部無聲通過。

### D15. `storage_backend` 在回答兩個問題，只有一個是單值的

`local-path-provisioner` 原本是 extra，語意上被當成「NFS 的替代方案」——於是有 NAS 的叢集**不會裝它**。但它不是替代方案，是 node-local 那一層：D7 要求 PostgreSQL 離開 NFS（fsync 與鎖語意，與 NAS 多大無關），而在 `storage_backend: nfs` 的叢集上，DB 無處可去。Group 6.4 因此在 jg-jiahd 上根本無法實作。

```
「裝哪些 provisioner?」  → 常常兩個都要
「哪一張是預設 class?」  → 恰好一個
```

只有第二個是單值選擇。2026-08-11 起：`local-path-provisioner` 移入 jg-base base apps 且**永不 suspend**；`nfs-subdir` 維持 base 但無 NAS 時 suspend；`storage_backend` 只決定預設。`ks.yaml.j2` 那段 auto-add 隨之刪除——它存在的唯一理由就是「是 extra 但又非裝不可」，這個矛盾本身就是訊號。

**連帶要修的 predicate**：D13 的 `accept_node_pinning` 閘門掛在 `storage_backend == 'local-path'`。local-path 現在到處都在，6.4 又要把 DB 放上去，於是 jg-jiahd（3 節點、NFS）會把 postgres 釘死在一台**而閘門不觸發**。該問的是「有沒有工作負載落在 node-local class」，不是「local-path 是不是預設」。列為 Group 6 的前置。

### D16. 遷移 runbook 從未被執行過，而它是錯的

jg-base README 那份「suspend 母 Kustomization → `kubectl patch spec.prune=false`」的步驟，是 2026-08-08 jcom 掉 PVC 之後寫下的**補救建議**，沒有人跑過。2026-08-11 第一次照著跑（local-path 遷移），release 照樣被 uninstall。兩個各自獨立的原因：

**一、`prune` 不是管刪除串聯的欄位。** CRD 寫得很清楚：

> `deletionPolicy` … Valid values are (`MirrorPrune`, `Delete`, `WaitForTermination`, `Orphan`). **`MirrorPrune` mirrors the Prune field**. Defaults to `MirrorPrune`.

`prune` 只透過 `MirrorPrune` 才會被讀到。而本模板生成的每個 Kustomization 都**明寫** `deletionPolicy: WaitForTermination`，所以刪除時 `prune` 根本不在路徑上。patch 下去讀回來一模一樣，看起來完全成功。

**二、線上 patch 本來就留不住。** 兩個欄位都宣告在 git 裡，母 Kustomization 下次 server-side apply 就覆蓋回去。想靠 suspend 母體擋住也不行：suspend 當下看是生效的，但已在飛行中的 reconcile 照樣落地，而且這個 stack 的 `Kustomization/flux-system` 帶著 `app.kubernetes.io/managed-by: flux-operator`——另一個 controller 對它的 spec 有自己的主張。

有效做法是**走 git，分兩次 push**：先把退役的 Kustomization 設成 `deletionPolicy: Orphan`、確認真的 apply 了，再 push 移除。

這次選在 jgt-omni 上試是對的：local-path 的 PV 是節點上的 hostPath，helm uninstall 拿走 StorageClass 與 Deployment，但**不碰還有 PVC 綁著的 PV**。兩個 PVC 全程 Bound，復原只需要一次 `flux reconcile source git jg-base`。同一個錯誤發生在 claude-code 的 PVC 上就是 jcom 那次的資料損失。

**通則**：一份沒被執行過的 runbook 不是文件，是假設。而它會在最壞的時刻被照著執行——上一次就是。

### D17. 儲存分層有三層，不是兩層

Group 6 實作後定形為三個名稱，各自回答不同問題：

| 變數 | 值 | 誰用 |
|---|---|---|
| `DEFAULT_STORAGE_CLASS` | `storage_backend` 決定 | 沒指定 class 的 PVC、bulk 資料 |
| `DB_STORAGE_CLASS` | **恆為 block tier**，與 `storage_backend` 無關 | 需要 fsync 與檔案鎖的（D7） |
| `LOCAL_PATH_IS_DEFAULT` | `storage_backend != nfs` | local-path 是否宣告自己是叢集預設 |

第三個是補一個真正的洞：`nfs-subdir` 寫死 `defaultClass: true`，但它在無 NAS 的叢集上被 suspend，而 local-path 從來沒宣告過——於是那種叢集**一張 default class 都沒有**，任何省略 `storageClassName` 的 PVC 都會 Pending 指著空氣。兩者永不相撞，因為 `LOCAL_PATH_IS_DEFAULT` 為真的條件恰好就是 nfs-subdir 沒在跑。

`default/postgres` 的 PVC 原本**完全沒寫 class**——於是在 NFS 叢集上，資料目錄靜默落在 `sc-nas`。D7 早就寫著不該這樣，但沒有任何東西在檢查，因為「沒寫」看起來不像一個選擇。

#### 預設值刻意選了「錯的那個」

`${DB_STORAGE_CLASS:=sc-nas}` 的預設不是正確答案，是**現狀**。理由是 PVC 的 `storageClassName` immutable：預設值只在 cluster-secrets 沒有該鍵時生效，也就是還沒遷移到 profile schema 的叢集，而那些全是 DB 已經在 NFS 上的 NFS 叢集。若預設成正確的 block tier，下一次 reconcile 會拿一個改不動的欄位去 patch 活的 PVC，把 jg-jiahd 與 jcom 的 Flux 打成永久紅燈——而資料一步也沒搬。

真正的搬遷是 dump → 刪 PVC → 用 block class 重建 → restore，那是 6.7，per-cluster 的動作。`db_storage_class` 欄位的作用是讓「還沒搬」變成 `cluster.yaml` 裡看得見的一行。

同樣的 immutable 顧慮讓 `server: 10.9.2.13` → `${NAS_SERVER}` 這個改動必須先查證：PV 的 `nfs.server` 也是 immutable，只有在唯一啟用那些 extras 的叢集上兩者解析為同一位址，才推得下去。查證過了，是同一個。

### D18. 「掃出一個缺陷」與「掃出的是那個缺陷」是兩回事

6.1/6.2 原本寫的是「修掉 `storageClassName: \"\"`，它會讓 PVC 永遠 Pending」，spec 甚至有一條需求叫「No PVC depends on manual pre-provisioning」。實際打開 13 處來看，**每一處都是同一份 manifest 裡的 PV/PVC 靜態配對，用 `volumeName` 綁定**——既有 NFS export 的正確用法，會立刻 Bound。

原始診斷是在沒讀檔案的情況下下的：看到 `storageClassName: ""` 就套用了那個 pattern 最常見的解釋。掃描本身是對的，它確實掃出了缺陷——只是缺陷是**寫死的 NAS 位址**，不是空字串。

若照原需求執行，會把四組正常運作的靜態綁定改成動態供裝，在 jg-jiahd 上把 linebot 的知識庫與 synophoto 的 vault 從既有 NFS export 換成新配的空目錄。**照著錯的規格做，比不做更糟**——spec 已改寫，並保留原文與被推翻的過程。

### D19. 延後搬遷是有代價的選擇，代價要當場付掉

6.7 的決定是**不搬**：jg-jiahd 的 postgres 留在 `sc-nas`，等 2c.8 的複製式儲存。理由站得住腳——搬到 local-path 是拿「可跨節點重新排程」換「正確的 fsync/鎖語意」，而 2c.8 兩者都給，何必先付一次遷移成本再付第二次。

但這個選擇有個立即的後果：**jg-jiahd 的資料庫繼續待在 NFS 上，而 postgres on NFS 的失效模式是靜默損毀**——不是崩潰，是某天發現資料不對。那條路徑的唯一救援是每天那份 dump。

而那份 dump 的 **restore 半邊從未被執行過**。備份 CronJob 每天寫出 48 KB 的檔案、留 14 份、job 全部 Completed——證明的是「dump 會產生檔案」，不是「檔案能還原成資料庫」。這正是 D16 那個錯誤的形狀：一份沒被執行過的程序不是保障，是假設。

所以延後搬遷的同時就把演練做掉了。在 jg-jiahd 起一個拋棄式 postgres、唯讀掛上備份卷、還原 `linebot-20260810.sql.gz`：

```
prod                    restored
episodes=148            episodes=148
knowledge=34            knowledge=34
line_user_projects=29   line_user_projects=29
line_users=29           line_users=29
projects=7              projects=7
schema_migrations=13    schema_migrations=13
sites=3                 sites=3
task_confirmations=11   task_confirmations=11
trello_boards=20        trello_boards=20
working_memory=11       working_memory=11
```

逐表相同，0 error。同時查出一個**前置條件**：必須先 `create role linebot`，否則 dump 裡每一句 `OWNER TO linebot` 都失敗——表還是會建起來，資料也在，但擁有者變成 `postgres`。這種「看起來成功了」的還原，正是會在真正需要的那天才發現不對的東西。

**通則**：接受一個風險的時候，同時驗證對應的補償措施還活著。否則「我們有備份」和「我們有 runbook」是同一種話。

### D20. 決定會反過來證偽 schema

`accept_node_pinning` 的 predicate 在一天之內錯了兩次，兩次都是同一種錯——問的是代理指標，不是實際狀態：

```
v1  storage_backend == "local-path"              漏掉：有 NAS 但 DB 在 block tier 的叢集
v2  ... 或 有 block-tier extra                    誤抓：明寫 db_storage_class 把 DB 移開的叢集
v3  ... 或 (db_storage_class 是 node-local 且 有 block-tier extra)
```

v2 是為了修 v1 而寫的，寫的時候看起來完備。**是 6.7 的決定把它證偽的**：使用者選「不搬、明寫 `sc-nas`」，我去套用時才發現 schema 會要求 jg-jiahd 承認一件在它身上不會發生的事——DB 明明在 NFS 上，卻被要求簽署 node-pinning 同意書。

一個要求使用者承認風險的閘門，如果會對沒有該風險的人發問，它教出來的行為就是「照簽」。那比不問更糟——D13 花了三次嘗試才讓 CUE 無法代簽，結果 predicate 本身讓簽名失去意義。

**通則**：實際去用一次 schema，比再讀一遍 schema 有效。這兩次修正都不是想出來的，是套用到真實叢集時撞出來的。

### D21. 把 app 移進 base，會立刻打到所有還列著它的叢集

2c.13 把 `storage/local-path-provisioner` 移進 jg-base 的 base apps，push 之後約 72 分鐘 jcom 的 Flux 是紅的：它的 `extras:` 還列著那個名字，於是 `extras-local-path-provisioner` 指著一條已經不存在的路徑。

jg-base 是**推出去就生效**的——~20 個叢集共讀 main，沒有 per-cluster 的節流。移動一個 app 的目錄等於同時對所有列著它的 `cluster.yaml` 做了破壞性變更，而那些 repo 各自獨立、不會一起更新。ks.yaml.j2 的 `_now_base` 過濾器正是為此存在，但它只保護**已經同步到新模板世代的 repo**；jcom 沒有，所以它就是接不住。

資源全程安全，原因值得記下來：**建不起來的 Kustomization 不會 prune**——它連 inventory 都算不出來，談不上垃圾回收。紅燈是可見的失敗，不是靜默損毀。

#### 但真正的保護不是那個，是 adoption

修的時候本來準備照 D16 的兩次 push 走（先 `deletionPolicy: Orphan`）。查了一下發現不必：

```
Kustomization/local-path-provisioner
  labels: kustomize.toolkit.fluxcd.io/name: cluster-apps-base   ← 新主人已接手
extras-local-path-provisioner.status.inventory
  entries: [flux-system_local-path-provisioner_...Kustomization]  ← 舊主人還記著
```

Flux 的 GC 在刪除前會比對物件的 ownership label 是不是自己。label 已經指向 `cluster-apps-base`，所以舊 wrapper 被 prune 時會**跳過**它。實測證實：移除 extras 條目、reconcile，`extras-local-path-provisioner` 消失，而 `local-path` StorageClass 的 age 仍是 88 天——沒有被重建，也就沒有被刪過。

所以 D16 的 runbook 可以收窄：**`deletionPolicy: Orphan` 只在「移除」與「接手」落在同一次 reconcile 時才需要**。一旦新主人已經 apply 過、label 已經改寫，競態就結束了，舊 wrapper 直接刪除是安全的。判斷依據是物件的 label，不是時間。

### D22. 用副本先跑一次，是這次唯一能證明「什麼都沒變」的方法

3.1 對 jg-jiahd（正式叢集）的作法是：整個 repo 複製一份 → 套用變更 → `task configure` → 和變更前的 `kubernetes/` 逐檔比對，然後才在本尊上重跑同一套。

結果讓這件事值得：`ks.yaml` **byte-identical**，`cluster-secrets` **+7 鍵、0 變更**。這種「什麼都沒動」的結論，只有先產出兩份可比對的輸出才拿得到——直接在本尊上跑，看到的是既成事實，沒有對照組。

secret 的比對不能直接 diff 明文（裡面是 token）。作法是解密後把每個值換成 sha 前十碼再比：鍵名照常可見，值只看得出「一樣/不一樣」。空字串是 `da39a3ee5e`，一眼認得出四個 `BACKUP_R2_*` 是空的。

同步時**保留本地分歧**是這次的關鍵細節。jg-jiahd 的 `ks.yaml.j2` 有一段 QUIC → http2 的 per-cluster workaround（該站點的上游防火牆擋 UDP 7844），直接覆蓋上游版本會把 cloudflared 打掛。清單化本地分歧、覆蓋後逐一重貼，是這種「部分同步」唯一安全的作法——也是為什麼只同步了 ② 真正需要的 4 個檔案，而不是整棵 `templates/`。

### D23. LB-IPAM 的 pool 選擇是「先來先贏」，所以窄 pool 不能用加的

1.5 在 jgt-omni（Cilium v1.19.1）實測，服務同時匹配多個 pool 時：

| 假說 | 結果 |
|---|---|
| 最具體者勝（/32 勝 /24） | ✗ 寬 pool 拿走 |
| 字典序 | ✗ `aaa-spike-narrow` 仍輸給 `spike-wide` |
| **建立時間最早者勝** | ✓ 兩次實驗一致 |

窄 pool 在寬 pool `disabled: true` 時立刻被使用，證明它可用、只是不被選。

**這直接決定 4.6 的作法**：jg-base 的 `pool` 在每個叢集上都是最早建立的那一個，任何後加的窄 pool 永遠拿不到分配。**必須收窄既有 pool，不能在旁邊新增。**

#### 順帶確認 D3a 的風險（含一次自我更正）

第一次量測時我的 spike pool 沒有寫 `allowFirstLastIPs`，而該欄位**未指定即等於可配發**，於是拿到 `192.0.2.0`（網路位址），我據此把 D3a 的風險上調成「比原本假設更糟」。**那是錯的——量到的是我自己的設定，不是生產設定。** jg-base 的 pool 明寫 `allowFirstLastIPs: "No"`。

補測（同樣 `/24`，這次照抄生產設定）：

```
allowFirstLastIPs: "No"
第 1 個自動配發   192.0.2.1
第 2 個           192.0.2.2
```

所以網路位址確實被保留，**D3a 原本寫的就是對的**：第一個自動配發的位址就是 `.1`，換算到 `10.9.1.0/24` 正是預設閘道。風險等級不變，不需要上調。

**教訓**：spike 的環境要照抄被測對象的設定，否則量到的是自己。

而 `l2-policy` 是 `loadBalancerIPs: true` 且**沒有 serviceSelector**——配到什麼就 ARP 廣播什麼。所以在任何一台這種叢集上，只要有人建立一個沒指定 IP 的 LoadBalancer Service，第二個就會把預設閘道的位址搶去廣播。

目前沒炸的唯一原因是 `envoy-external` / `envoy-internal` / `k8s-gateway` 三者都用 `lbipam.cilium.io/ips` 明確指定位址，自動配發從未發生過。這是巧合構成的安全，不是設計。

### D24. `IPAMRequestSatisfied=False` 說得出有問題，說不對是什麼問題

1.6 確認了單一位址 profile 的失敗是可觀測的：同一個 `sharing-key` 下，port 不衝突的服務共用位址，port 衝突的拿不到位址並回報 `cilium.io/IPAMRequestSatisfied = False`。

但 reason 與訊息是誤導的：

```
reason  = out_of_ips
message = All enabled CiliumLoadBalancerIPPools that match this service
          ran out of allocatable IPs
```

實際原因是**共用位址上的 port 相撞**，不是位址用盡。在 appliance 的單一位址設計下這兩者永遠長得一樣，維運者看到訊息會去找「pool 是不是太小」，而正解是「這個 port 已經被另一個服務佔走」。

4.9 讓 daily-check 監看這個條件仍然正確——失敗確實浮得出來。但**告警文案必須自己補上正確的解釋**，不能直接轉貼 Cilium 的 message。

### D25. Gateway 的 `infrastructure.labels` 是這條路能走通的前提

1.7 原本只要驗 `annotations` 傳導。實測發現 `labels` 也逐字傳導，而**那才是關鍵的一半**：pool 的 `serviceSelector` 只能選 Service，而 Envoy Gateway 產生的 Service 預設只帶它自己的標籤（`gateway.envoyproxy.io/owning-gateway-name` 等）。沒有 labels 傳導，就沒有辦法讓某個 Gateway 的 Service 落進指定的窄 pool——annotations 傳導得再好也沒用，因為它根本不會被那個 pool 選中。

功能面也一併驗了，不只是「註解有出現」：單一位址 pool 下，ns `spike` 的 Gateway（:80）與 ns `default` 的普通 Service（:9090）帶同一組 `sharing-key` + `sharing-cross-namespace: "*"`，兩者同得 `203.0.113.90`。跨 namespace 共用經由 Gateway 傳導的 key 成立，D3 的單一內網位址設計在 Gateway 這一側站得住。

### D26. 收窄 pool 的失敗是延遲性的，不是即時可見的

4.6 實作前先在 jg-jiahd 演練了整個切換（用 TEST-NET 位址明確釘死，任何 LAN pool 都服務不了它，因此對真實網路零暴露）。兩個結果，第二個推翻了我先前的判斷。

**切換本身無縫**。`drill-wide` 設 `disabled: true` 的瞬間起連續取樣 12 秒，位址一次都沒掉，`IPAMRequestSatisfied` 全程 `True`——Cilium 直接改由 `drill-narrow` 供應同一個位址，不會先收回再配發。

**但漏列一個位址不會當場報錯**。刪掉提供該位址的 pool 之後：

```
t+3s … t+18s   ip=192.0.2.50   satisfied=True   reason=satisfied
```

**已經配出去的位址不會因為來源 pool 消失而被收回。** 直到 Service 被重建才浮出來：

```
after recreate:  ip=<none>  satisfied=False
  message: No pool exists with a CIDR containing '192.0.2.50'
```

我先前說「漏掉的位址會依 1.6 可見地失敗」——**那是錯的**。1.6 量的是「新配發時 pool 空間不足」，不是「既有配發的來源消失」。後者是潛伏的：narrow 之後一切看起來正常，直到某次 Helm upgrade、Flux 重佈或節點事件重建了那個 Service，它才安靜地失去位址。而那時距離改動已經過了幾天或幾週，沒有人會把兩件事連起來。

**因此 4.6 的驗收標準不能是「narrow 完之後有沒有壞」**——那個問題在漏列的情況下也會回答「沒有」。必須是**套用前先證明 pool 涵蓋當下每一個已配發位址**，也就是把 `kubectl get svc` 實際列出的位址集合，和渲染出來的 `LB_POOL_BLOCKS` 逐一比對。三個活叢集都已這樣比對過，完全吻合。

### D27. 兩個巢狀 pool 不可能共存，而我照著自己的警告踩了下去

4.6 的初版是兩個 pool：`pool` 保留整個 node CIDR 且預設啟用，`pool-narrow` 列出實際位址，靠 `disabled: true` 讓前者退場。設計理由是保護「看不見的叢集」——沒有變數就維持今日行為。

**它從來沒有運作過。**

```
pool-narrow: PoolConflict=True  cidr_overlap
  range '10.9.9.4 - 10.9.9.4' overlaps range '10.9.9.0 - 10.9.9.255' from IP Pool 'pool'
  IPsUsed = 0
```

narrow 依定義就是 wide 的子集，必然重疊，而 Cilium 對重疊一律以 `cidr_overlap` 拒絕——**`disabled` 不影響這個判定**。兩個叢集上 `pool-narrow` 的 `IPsUsed` 都是 0，一個位址都沒配過。

而它看起來是好的，因為 **D26**：既有配發不會被收回。四個服務各自抱著改動前就拿到的位址，什麼都沒壞。真正的失敗在等下一次 Service 重建——**正是 D26 描述的那一類潛伏失敗，被引用 D26 的那個改動親手裝上去**。在 jgt-omni 刪掉 `envoy-internal` 之後它再也拿不回位址（`no_pool`），才把它逼出來。

#### 為什麼 1.5 沒抓到

1.5 測「服務同時匹配窄 pool 與寬 pool 時誰勝」，用的兩個 pool 是 `192.0.2.0/24` 與 `198.51.100.5`——**互不重疊**。互不重疊的 pool 確實會比較新舊；巢狀的 pool 根本走不到那一步，先被 conflict 擋掉。

我把「最舊者勝」直接套用到巢狀情境，而那個結論的成立條件（不重疊）在 spike 裡是隱含的、沒有被寫下來。**spike 結論要連同它的前提一起記，否則它會被搬到不成立的地方。**

#### 修正後的形狀

只有一個 pool，每個叢集都必須提供自己的 blocks。沒有 narrow 的叢集就把整個 node CIDR 寫出來——那本來就是它隱含在拿的東西，只是現在是明寫的。空的預設值不是安全網（空 pool 什麼都不發），它只是讓 manifest 保持合法；會落到它的叢集就是沒被現行模板渲染過。

代價是失去「未知叢集自動安全」這個保護，換取的是這個設計真的能動。jcom 因此先補了一行 `LB_POOL_BLOCKS`（值就是它的 node CIDR），三個活叢集全部覆蓋。

### D28. 標註值的兩個陷阱：空字串與 `*`

4.3 要把 sharing 標註放進 jg-base，用 `${LAN_SHARING_KEY:=}` 控制開關。連續兩次被 YAML 擋下：

| 寫法 | 結果 |
|---|---|
| `"${LAN_SHARING_KEY:=}"` | Gateway CRD 收到 `null` 而非 `""`，型別驗證失敗，整份 manifest dry-run 被拒 |
| `"${LAN_SHARING_CROSS_NAMESPACE:=*}"` | kustomize **移除引號**，替換後成為裸 `*`，YAML 當成 alias，解析失敗 |

共同的根因是**替換後的值要能獨立作為合法 YAML 純量**——kustomize 不會替你保留引號，而 Flux 是在 kustomize 之後才做替換的。

修法是給每個服務**非空且互異**的預設值（自己的名字、自己的 namespace），等同「不共用」。實測確認：非空但互異的 key 各自獨立配發，兩個服務都 satisfied。而 `envsubst` 的 `:=` 對「已設定但為空」也套用預設值，所以未遷移叢集與已遷移但不收斂的叢集會落到同一條路徑。

`sharing-cross-namespace` 收斂時用明確的 `network,mqtt` 而非 `*`——實測逗號清單與 `*` 效果相同，順帶把跨 namespace 權限收成最小集合。

### D29. D6 的地基不存在：Cloudflare 不解析指向 RFC1918 的 A 記錄

D6 整套設計建立在一個假設上：把內網名稱發成指向 LAN 位址的公開 A 記錄，LAN 客戶端用路由器給的任何 resolver 都解得到，因此**不需要動路由器、不需要動裝置**——而那正是零 IT 客戶唯一能配合的形式。

2026-08-12 實測推翻了它。

#### 我第一次量錯了，而且錯得看起來像成功

第一次測試（1.3）記錄下來的結論是「DNS-only 可行、proxied 被拒、1.1.1.1 與 8.8.8.8 都回傳 10.9.1.241」。前兩項是對的。**第三項不成立，而且無法重現。**

第二次測試補上了第一次缺的東西——**對照組**：

```
同一個 zone、同時建立、同樣 proxied=false、同樣 TTL
  ctl-public     → 203.0.113.9    立即解得到
  rfc1918-probe  → 10.9.1.241     權威 NS 回 NXDOMAIN
```

同一次查詢、同一個權威 NS，所以不是傳播、不是快取。zone 內沒有 wildcard 可以解釋先前那個答案，而把當初那筆記錄原樣重建，現在回傳空。

**API 收下記錄，DNS 拒絕發布它。** Cloudflare 這是在做 DNS rebinding 防護——諷刺的是，D6 原本擔心的是**客戶路由器**會做這件事，並為此準備了 `k8s-gateway` fallback。真正擋下來的是上游的權威 DNS，而 fallback 對它無效。

#### 而且 appliance 是**兩條路都不通**，不是「改用 k8s-gateway 就好」

這一點上一版寫得不夠清楚。`k8s-gateway` 是**被動的**——它是一台 DNS server，不攔截流量，只在客戶端主動查詢它時才回答。要讓 LAN 上的手機、電視、HomeKit 用得到，必須：

- 路由器的 DHCP 發 option 6 指向它，或
- 每台裝置手動設定 DNS

**而那正是 D6 當初發明公開 A 記錄要繞開的那一步。** 所以 appliance 現在的處境是：

```
公開 A 記錄     → Cloudflare 不解析              ✗
k8s-gateway     → 部署得起來，但沒有人會去指向它   ✗
```

`full` / `prosumer` 不受影響：那些叢集的 operator 有能力也有權限把路由器的 DNS 指到 `k8s-gateway`，jg-jiahd 與 jcom 今天就是這樣運作的。**問題完全集中在 appliance**，而它恰好是唯一不能要求任何設定動作的那一個。

#### 連帶失效的東西

- **5.1 / 5.2**（第二份 external-dns）：發出去的記錄沒有人解得到。已移除，而不是留著發佈解析不了的記錄
- **5.3**（k8s-gateway 降為條件啟用）：它不是 fallback，是**唯一**能回答內網名稱的東西。appliance 若不部署它，內網名稱完全無法解析
- **5.4**（rebinding 偵測）：邏輯本身沒錯且會安靜跳過（公開查不到 RFC1918 就不比對），但它偵測的是客戶路由器，而問題不在那裡

#### 這是 Cloudflare 的政策，不是 DNS 的限制

補測（2026-08-12）：已知會把位址編進主機名的公開服務，從公開 resolver 查都正常回傳私有位址。

```
10.9.1.241.nip.io      @1.1.1.1 → 10.9.1.241     @8.8.8.8 → 10.9.1.241
192.168.1.1.sslip.io   @1.1.1.1 → 192.168.1.1    @8.8.8.8 → 192.168.1.1
localtest.me           @1.1.1.1 → 127.0.0.1      @8.8.8.8 → 127.0.0.1
```

所以 **DNS 協定沒問題、1.1.1.1 與 8.8.8.8 沒有過濾**，擋住的是 Cloudflare 對自己託管 zone 的發布政策。D6 的想法本身成立，只是不能託在 Cloudflare 上。

**但 zone 不能整個搬走**：Cloudflare Tunnel 的公開入口必須是同 zone 內的 proxied 記錄（`<id>.cfargotunnel.com` 只在 Cloudflare zone 內有意義）。所以能動的是「內網名稱那一部分」，不是整個網域。

#### mDNS 為什麼不是解（2026-08-12 評估）

`.local` 幾乎零設定——各大 OS 原生支援，正好符合「不能碰路由器與裝置」。但有兩個硬限制：

1. **只能服務 `.local`。** resolver 依後綴決定走不走 multicast，`homebridge.janncot.cc` 永遠不會被送去問 mDNS。要用就得改名，而那正是 D5 拒絕過的那類變更。
2. **`.local` 拿不到公開 TLS 憑證。** Let's Encrypt 不簽保留網域，所以 HTTPS 一定是憑證錯誤，除非在每台裝置安裝私有 CA——那就回到「要碰每一台裝置」。

值得記的是：**真正需要「LAN 主機名 + 有效 TLS」的集合比想像小**。homebridge / HomeKit 本來就用 Bonjour（即 mDNS）做裝置探索，不經 DNS；MQTT 的 IoT 裝置通常直接設 IP。需要憑證的其實是那些有登入的網頁介面。mDNS 可以覆蓋前者，覆蓋不了後者。

#### 剩下的選項，沒有一個是免費的

| 方案 | 代價 |
|---|---|
| **把內網名稱委派給另一家權威 DNS**（`lan.<domain>` NS 委派，Cloudflare 留給 tunnel） | 多一層後綴（D5 拒絕過類似的）、多一個 provider 與其 API 憑證；但扁平度以外的一切都保留：cert-manager 照樣 DNS-01 簽發、tunnel 不動、客戶端零設定 |
| mDNS `.local` | 名稱全改且**拿不到公開憑證**；只適合 HomeKit/MQTT 這類本來就不靠 DNS 或不需 TLS 的 |
| 換掉整個 zone 的 DNS 供應商 | **不可行**：Cloudflare Tunnel 需要同 zone 的 proxied 記錄 |
| 客戶把路由器 DNS 指向 k8s-gateway | 正是零 IT 客戶做不到的那一步 |
| appliance 接管 DHCP 並發 option 6 | 讓 appliance 成為客戶網路的單點，D3 已因此否決過類似方案 |
| 接受出廠時由 operator 設定一次路由器 | 誠實，但「三個物理動作」變成四個，且需要路由器管理權 |

這是 ② 目前最大的未解問題，且**不是實作細節**——它決定 appliance 能不能達成「LAN 名稱可用且零設定」這個 goal。在選定方向之前，Group 5 其餘項目不應繼續。

**通則**：這次的錯誤不在於量測，而在於**沒有對照組**。一個沒有 negative control 的正面結果，證明的可能只是「我當時看到了什麼」。第二次測試之所以可信，正是因為公開位址的記錄在同一時刻是通的。

### D30. 未 escrow 的 `age.key` 讓備份變成「看起來像保護」的東西

備份加密到叢集自己的 age 公鑰（D9），好處是 R2 上的密文連持有該 R2 帳號的 operator 都讀不了——已實測：密文中找不到明文標記，換一把 key 解密得到 `no identity matched any of the recipients`。

代價是 `age.key` 成為唯一能讀取備份的東西。而在單節點 appliance 上，它就放在**備份要對抗的那顆碟**上。

```
碟壞掉 → 叢集沒了 → R2 上有備份 → 但解密金鑰跟著碟一起沒了
```

結果是一堆沒人打得開的密文。這比沒有備份更糟，因為它在事發之前一直看起來像保護。

因此 `age_key_escrowed` 沿用 D13 的模式：**appliance 未宣告或宣告 `false` 一律拒絕渲染**，且不給預設值——預設值等於替 operator 簽名。這讓「escrow 完成」成為 provisioning 的前置條件，而不是一條寫在文件裡、沒人檢查的步驟。

文件另外要求用 `age-keygen -y` 對 **escrow 副本**驗出的公鑰去比對 `.sops.yaml`：一份被截斷的金鑰副本，和一份好的看起來完全一樣，而差別只會在需要它的那天顯現。

### D31. ConfigMap 裡的 shell 腳本會先經過 envsubst

備份腳本用 `BASH_REMATCH` 的數字索引取回正則捕獲，整個 Kustomization 因此建置失敗：

```
post build failed for 'ConfigMap.v1/offsite-backup':
  envsubst error: variable substitution failed: missing closing brace
```

Flux 在套用 ConfigMap 之前會對它跑 envsubst，於是帶數字索引的展開被讀成一個「名字裡有中括號」的變數。**腳本放在 ConfigMap 裡就不再只是 shell，它同時是 Flux 的替換輸入。**

有意思的是 `@` 形式的陣列展開沒事——daily-check 用了好幾個月。所以不是所有中括號都不行，是數字索引特別會踩到。

而第一次修正之後它**還是失敗**：我把程式碼改成 `sed`，卻在註解裡寫下 `${BASH_REMATCH[1]}` 解釋為什麼要改。envsubst 不區分程式碼與註解。

### D32. 決定：出廠時由 operator 設定一次路由器（2026-08-12）

D29 的四個選項中選定「出廠時 operator 設定一次路由器的 DNS」。取捨很清楚：**用一個安裝時的動作，換掉其他三個方案各自的長期代價。**

| 保住了 | 放棄了 |
|---|---|
| 扁平命名（D5 不必推翻） | 「客戶端與路由器零設定」這個目標 |
| cert-manager 對真實網域簽發的有效 TLS | 出貨流程多一個需要路由器管理權的步驟 |
| 不引入第二個 DNS provider 與其憑證 | |
| Cloudflare Tunnel 不動 | |

零 IT 客戶仍然不必做任何事——動作落在 operator 身上，而 operator 本來就要到現場。這與 `README-zero-IT.md` 的「三個物理動作」不衝突：那三個是**客戶**的動作。

#### 連帶後果一：`k8s-gateway` 不再是 fallback，是主要路徑

5.3 原本要讓 appliance 預設不部署它，那個預設現在是反的。命名也錯了——`dns_fallback` 描述的是一個不存在的角色。改名為 `deploy_k8s_gateway`，appliance 預設**開**。

它仍然只吃一個 LAN 位址：4.3 的 sharing-key 讓它與 `envoy-internal`、`mqtt` 共用同一個位址，所以「appliance 只佔 1 個位址」的目標不受影響。

#### 連帶後果二：位址被寫進路由器之後就不能再自動改選

這一點比第一點重要，而且與 4.1/4.2/4.4 直接衝突。

探測元件的設計是「每輪重新確認，撞號就改選」（D4）。但一旦 operator 把路由器的 DNS 指向 `10.9.x.y`，那個位址就成了**外部契約**：改選會讓路由器指向一個沒有東西在聽的位址，而 LAN 上所有內網名稱同時失效——沒有人會把這兩件事連起來。

所以 appliance 的位址生命週期變成兩段：

```
出廠前   探測選址 → operator 確認 → 寫回 cluster.yaml 固定下來 → 設定路由器
出廠後   位址是宣告值，不再改選；撞號變成需要人介入的事件
```

探測從「持續的分配機制」降級為「首次選址的輔助」。這其實讓 4.1/4.2 更誠實：ARP 本來就只能證明「此刻沒人回應」（D4），把它當成長期分配機制一直是勉強的。

4.4 的撞號監看仍然有價值，但它的動作從「自動改選」改成「**回報並要求人介入**」——因為改選的代價現在包含「要再去改一次路由器」。

#### 連帶後果三：偵測的對象變了

5.4 實作的是「公開 DNS 回 RFC1918 → 問路由器是否同意」。D29 之後公開 DNS 根本不會有那筆記錄，那個檢查會安靜跳過，等於死碼。

正確的檢查是直接的：**問路由器解不解得出內網名稱**。解不出就代表路由器被重設、被換掉，或設定從未生效——而那正是「內網全壞掉但沒有任何元件顯示異常」的情形。

### D33. 檢查憑證的機制不該自己洩漏憑證

2c.3 的第一版實作把強度規則寫進 CUE：

```cue
ttyd_credential?: string & =~"^[^:]+:.{20,}$" & !~"(?i)(admin|test|password|...)"
```

規則本身是對的，八個測試案例全部如預期。但 `cue vet` 失敗時會這樣說：

```
ttyd_credential: invalid value "admin:hunter2" (out of bound =~"...")
```

**它把憑證印進終端和 CI log。** 一個為了抱怨憑證太弱而把憑證洩漏出去的檢查，比沒有檢查更糟——弱憑證至少還需要有人去猜。

所以檢查移到 `scripts/check-ttyd-credential.py`，那裡可以控制輸出：只講哪裡不對、怎麼修，永遠不印值。

順帶踩到第二個坑：第一版腳本用 `line.partition(":")` 讀值。憑證本身**依定義含冒號**，而該行還可能有行內註解與引號，於是它讀到的字串比真值長了幾個字元——長度判斷因此得出不同答案（先說 9 字元，後說含弱字）。改用 `yq`。**一個讀錯待檢物件的檢查器，比沒有檢查更危險，因為它會給出看似權威的錯誤結論。**

#### 檢查結果證明這個任務不是假想的

| 叢集 | 問題 |
|---|---|
| jg-jiahd | 使用者名稱 `admin`、密碼 9 字元 |
| jcom | 使用者名稱 `admin`、密碼 9 字元 |
| jgt-omni-accept | 使用者名稱 `admin` |
| jgt-talos-accept | 密碼 1 字元、單一重複字元 |

四個全部不合格，其中兩個是生產叢集，守著一個 tunnel 一連上就對外可達的 shell。`replicas: 0` 擋住了實際登入，但那是姿態不是控制——任何把它 scale up 的動作都會拿掉它。

### D34. 「模板無法表達 X」要先跑一次再說

2c.2 記錄的是：`claude_instances: []` 會讓 makejinja 略過 helmrelease，而 `kustomization.yaml` 硬寫的 `resources` 會讓 kustomize build 失敗。

實測結果：**makejinja 沒有略過**，它產生了一個只含註解的檔案；`kustomize build` 成功並輸出 0 個物件；`task configure` rc=0。模板一直都表達得出來。

會失敗的是「檔案根本不存在」（`evalsymlink failure`），但那個情況不會發生。原本的失敗鏈是從兩個各自合理的前提推論出來的，中間那一步沒有人驗過。

與 D18（`storageClassName: ""` 那次）同一個形狀：**掃描或推論指出一個缺陷，不代表指出的是那個缺陷。** 差別在於這次的成本只是一次實驗，而 D18 若照著做會拆掉四個正常運作的 NFS 掛載。

### D35. 複製式儲存解除了 D13 的承認要求，但它的前提裝不進 manifest

D13 把「多節點 + node-local」變成必須明寫的承認（`accept_node_pinning`），並說真正的解是複製式 block storage。2c.8 把那條路做出來了：`storage_backend: "replicated"` → Longhorn，而 `longhorn` 是唯一同時是 block-backed **且**不釘節點的 class。所以部署它會讓那個閘門自動不再觸發——這是正確的誘因方向：想擺脫承認書，就去解決它描述的問題。

選 Longhorn 而非 Rook-Ceph：3 節點的家用叢集跑 Ceph 過重。

#### 它與其他 provisioner 有一個結構性差異

`local-path` 與 `nfs-subdir` 是純 manifest：套用就會動。Longhorn 不是——它需要每個節點有 `iscsi-tools` 與 `util-linux-tools` 兩個 Talos system extension，加上 `/var/lib/longhorn` 的 rshared 掛載。**這些沒有任何 Kubernetes manifest 裝得起來**，而少了它們的失敗形狀特別壞：pod 起得來、回報健康、然後掛載不了任何 volume。

因此它預設 suspend 的理由和 `nfs-subdir` 不同：後者是「這個叢集沒有 NAS」，前者是「這個叢集的節點還沒被改造過」。文件把節點準備寫成 enable 之前的必要步驟，而不是 troubleshooting。

#### 誠實的取捨表比實作更有價值

| | 釘住的 local-path + 備份 | Longhorn |
|---|---|---|
| 節點死掉 | 從昨晚的 dump 還原到另一台 | 從存活副本重建 |
| RPO | 最多 24h | 0 |
| RTO | 約 15 分鐘、人工 | 秒級、自動 |
| 代價 | 無（備份本來就在跑） | 每節點約 1 GB RAM，多一個要升級與監看的系統 |

對 jg-jiahd——3 節點、8.7 MB 的資料庫、**今天剛驗證過的每日還原路徑**——「釘住 + 備份」是站得住腳的。Longhorn 要在 RPO 真的重要、資料大到還原很慢、或節點重開頻繁到人工復原不再罕見時才值得。

文件因此以「先問值不值得」開頭，並記下第三條這個 stack 沒實作的路：用 CSI 從 NAS 取 iSCSI block volume。資料留在已有 RAID 的硬體上、fsync 語意正確、pod 可以漂移，而且不多一層複製——代價是同樣需要那個 iSCSI extension。

#### 一個被自己的檢查擋下的設計錯誤

初版讓 `db_storage_class` 隨 backend 自動推導成 `longhorn`。`check-template-integrity` 的「一個欄位只能有一個有效預設」規則擋下它，而那是對的：CUE 宣告預設 `local-path`、plugin 算出 `longhorn`，`_uses_node_local` 就會依 CUE 那個錯的值判斷，於是對一個已經不釘節點的叢集索取承認書。

改成單一預設，並讓「忘記把資料庫搬到 longhorn」以正確的方式現形——資料庫仍在 node-local class，閘門觸發，而它問的正好就是被忘記的那件事。**比自動推導更好：自動推導會讓人以為裝了 Longhorn 資料就搬好了。**

### D36. 手動 scale 的漂移，呈現出來是「無法解釋的中斷」

claude-code 的模板寫死 `replicas: 0`，那是刻意的安全姿態——一個帶 cluster-admin RBAC、被 tunnel 對外曝光的 root shell，不該常駐。

但 jgt-omni 的 `im` 先前一直是 `1/1 Running`：那是更早驗證 `im.janncot.cc` 時手動 `kubectl scale` 上去的，從沒寫回宣告。今天為了測 Longhorn 反覆 reconcile，Flux 把它校正回 0，`im.janncot.cc` 從 401 變成 503。

**宣告式系統修正漂移是它的職責，但當事人看到的是服務無故消失。** 而且我當時正在回報「pod 1/1 Running 53 分鐘」當作資料完好的證據——那個 pod 在我報告的前幾分鐘就已經被縮掉了，我讀到的是舊狀態。

修法是把「要不要常駐」變成 `cluster.yaml` 的欄位（`claude_code_always_on`，預設 off），而不是再 scale 一次。

#### 為什麼不照 jg-jiahd 的做法

jg-jiahd 有同樣的需求，處理方式是**手改自己那份 `helmrelease.yaml.j2`** 設 `replicas: 1`。CLAUDE.md 記載那是 2026-08-08 user-confirmed 的，並註明它取代了先前 `kubectl scale` 的漂移——**同一個問題在那邊已經發生過一次**。

但那份本地修改後來成為 3.1 同步時必須逐一保護的分歧之一（與 QUIC workaround 並列）。一個需求出現第二次，就該是欄位而不是第二份分歧。jg-jiahd 未來可以改用這個欄位，把那段本地修改收掉。

**通則**：per-cluster 的差異若反覆出現，它就不是例外，是缺少的設定項。

### D37. `storage_backend: replicated` 幾乎是單向的

2c.8 只驗證了安裝。移除 Longhorn 在 jgt-omni 上撞到三道彼此獨立的牆：

1. **拒絕移除**：`longhorn-uninstall` hook 要求 `deleting-confirmation-flag`。patch Setting CRD 不夠——CRD 顯示 `value: "true"` 且 `status.applied: true`，job 仍讀到 `false`，因為它讀的是 chart 裝下去的 ConfigMap。必須從 Helm values 設。
2. **webhook 死鎖**：webhook Service 被刪但設定還在，於是 namespace 裡任何刪除都失敗，卡在 `Terminating` 不會自己好。
3. **三個 CR 的 finalizer**：`backuptargets`、`engineimages`、`nodes.longhorn.io` 撐住 namespace。

之後 CRD 與孤兒 StorageClass（`longhorn`、`longhorn-static`）還要手動清——Helm 兩樣都留著。

**進場前先想好退場。** 這件事的教訓不只是「移除很麻煩」，而是：一個元件的**安裝**驗證通過，不代表它可以被安全地移除，而 profile 這種可切換的軸隱含了雙向承諾。已寫進 `docs/operations/replicated-storage.md`。

### D38. 換 storage class 的順序：先確認 secret，再刪 PVC

jcom 的 DB 搬遷（6.7）第一次沒成功，而失敗的方式很有教育意義。

流程是：改 `db_storage_class` → `task configure` → push → 刪 PVC → 讓 Flux 用新 class 重建。刪掉之後 Flux **立刻**重建了 PVC，但它讀到的 `cluster-secrets` 還是舊的，於是又建成 `sc-nas`。而 `storageClassName` immutable，所以那個新 PVC 也改不了——只能再刪一次。

根因是把「push 了」當成「叢集已經知道了」。`cluster-secrets` 是另一個 Kustomization，它有自己的 reconcile 節奏；而 PVC 的重建幾乎是瞬時的。兩者之間有一個窗口，而破壞性操作正好落在窗口裡。

正確的順序是**先驗證叢集上的值**，再動 PVC：

```sh
kubectl -n flux-system get secret cluster-secrets \
  -o jsonpath='{.data.DB_STORAGE_CLASS}' | base64 -d   # 必須已是新值
```

第二次照此執行，一次成功。

**通則**：GitOps 裡「我推了」和「叢集套用了」之間永遠有延遲，而任何不可逆的手動步驟都必須以後者為前提，不是前者。

### D39. 路由器設定的三種做法，以及一次過度悲觀的評估

D32 決定由 operator 設定一次路由器，但沒說**怎麼設**。實測（jgt-omni，2026-08-13）釐清了兩件事：

```
im.janncot.cc  → 10.9.1.243    k8s-gateway 負責的名稱
github.com     → 20.27.177.113  不負責的網域，確實轉發上游
```

**`k8s-gateway` 會轉發。** 我先前假設它不轉發、因而斷言「把 DHCP DNS 指向它 = 全網斷」，那個推論的前提是錯的。正常運作時它對整個 LAN 是透明的。

真正的風險縮小成兩個，且性質不同：

| 失效模式 | secondary DNS 能否接手 |
|---|---|
| 叢集完全當掉（無回應） | ✅ 客戶端 timeout 後轉 secondary——**可用但慢**（通常 5 秒） |
| k8s-gateway 活著但回錯（NXDOMAIN / SERVFAIL） | ❌ 客戶端**接受**那個答案，永遠不會問 secondary |

所以 secondary DNS 是部分保險：擋得住停電，擋不住壞答案。

#### 通用性才是決定因素

| 做法 | 內網名稱 | 叢集掛掉 | 路由器支援度 |
|---|---|---|---|
| DHCP DNS → 叢集（+ secondary） | 自動涵蓋 | 慢但可用 | **所有路由器** |
| 條件轉發（只有 `<domain>` 給叢集） | 自動涵蓋 | 只影響內網名稱 | dnsmasq 系（UniFi / OpenWrt / pfSense） |
| 逐筆 Local DNS Record | 手動同步 | 只影響那幾筆 | 部分機種 |

appliance 是要出貨給零 IT 客戶的，**部署程序必須在最低共同標準上可行**。條件轉發最乾淨，但消費級路由器多半沒有；逐筆記錄也不普遍。**唯一每台路由器都有的是 DHCP 的 DNS server 欄位。**

所以預設程序是：primary 指向叢集、secondary 指向路由器自己或公開 DNS。有條件轉發的（像 ferry133 的 UniFi）就用它，那是嚴格更好的選項，但不能寫成前提。

**通則**：一個要出貨的程序，它的可行性下限由客戶端的設備決定，不由我們手上這台決定。

## Risks / Trade-offs

- ~~**Cilium `sharing-key` 跨 namespace 未經驗證**~~ → **已於 2026-08-09 在 jg-jiahd 實測確認可行**（見 D3 的 spike 結論）。內網位址數確定為 1。
- **收窄 pool 對既有叢集是行為改變** → `full` profile 需逐叢集列出實際使用位址後再套用；未列全會讓某個 Service 失去位址，但因為會回報 `IPAMRequestSatisfied=False`，屬可觀測失敗而非靜默中斷。
- **`envoy-external` 改 ClusterIP 對既有叢集是行為改變** → 若有人習慣從 LAN 直接打該位址（而非經 Cloudflare），會斷。僅在 `appliance` 下預設改變，`full` 維持現狀。
- **ARP 探測撞號無法根治** → 持續監看 + 併入日常健檢 + 撞號時自動改選並記錄新舊位址；長期以 DHCP lease-holder 取代，介面已預留。
- **DNS rebinding protection 會擋掉公開 A 記錄回私有 IP**（Fritz!Box、部分 ASUS、pfSense 預設） → 開機自檢偵測後啟用 `k8s-gateway` fallback；因名稱扁平，切換零遷移。
- **local-path 讓 pod 綁死單一節點** → appliance 本就是單節點，語意一致；`prosumer`/`full` 多節點叢集若把 DB 放 local-path，需明確接受該 pod 不可跨節點漂移。
- **BREAKING：既有 cluster.yaml 需補兩個欄位** → 失敗發生在 `cue vet`、渲染之前，不會產出半套設定；遷移是每個 repo 加兩行。
- **單碟切兩個分割不防磁碟故障** → 因此 appliance 的離線備份是強制而非選配；分割只解決系統與資料互相踩踏。
- **備份鏈依賴 Cloudflare R2** → 若 R2 不可用，備份中斷會經由 daily-check 的 dead-man switch 曝光，不會靜默失敗。
- **`age.key` 是單點** → escrow 為強制項，且列為交接封裝第一項；未 escrow 即視為 provisioning 未完成。

## Migration Plan

1. **先讓既有叢集無痛**：schema 加入兩條軸後，jcom / jg-jiahd 等各補 `deployment_profile: full` + `storage_backend: nfs`，行為與今日完全相同，先確認 `task configure` 綠燈。
2. **jg-base 側加法優先**：第二份 external-dns、備份 CronJob、LAN 位址探測元件都是新增資源，不影響既有叢集（它們仍走 `k8s-gateway`）。
3. **postgres 儲存層與 backup PVC 修正**：對既有叢集是資料搬遷，需個別排程，不隨 profile 上線一起做。
4. **appliance 首台以 scratch 叢集驗證**，還原演練通過後才用於真實客戶。
5. **Rollback**：本 change 的每一項在 `full` profile 下皆為 no-op 或加法，回退方式是把 profile 維持 `full` 並停用新增的 external-dns 實例與備份 CronJob。

## Open Questions

- ~~Cilium LB-IPAM 的 `sharing-key` 是否支援跨 namespace 共用？~~ **已解決**：支援，內網位址數為 1（Cilium v1.19.1 實測）。
- 服務同時匹配窄 pool 與寬 pool 時，Cilium 依什麼順序選擇？影響遷移期間兩種 pool 並存的安全性。須在 scratch 叢集驗證，不可在有真實裝置的 LAN 上測。
- DNS rebinding protection 的可靠偵測方式為何？從叢集內解析拿不到答案，必須從 LAN 上的用戶端視角測——是靠客戶手機（change ④ 的 LINE bot）回報，還是節點自己以 hostNetwork 查詢路由器指定的 resolver？
- Cloudflare DNS 對 RFC1918 A 記錄的實際行為（僅確認可 DNS-only，需實測是否有額外限制）。
- R2 的 bucket 與憑證由誰建立、放在哪一層設定？取決於 change ③ 對「每叢集 Cloudflare 帳號」的最終結論。
- `prosumer` 的預設 storage class 若為 NFS，DB 的 block 要求如何表達——是強制每個 DB PVC 明寫 class，還是另設一個永遠 block 的次要 class？
