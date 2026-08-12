## 1. Spikes（先做，結果會改變後面的設計）

- [x] 1.1 驗證 Cilium LB-IPAM `lbipam.cilium.io/sharing-key` 跨 namespace 支援 — 2026-08-09 於 jg-jiahd (v1.19.1) 實測，可行；結論見 `design.md` D3
- [x] 1.2 內網共用位址數量確定為 1，已回寫 `design.md` D3/D3a 與 `specs/lan-address-allocation/spec.md`
- [x] 1.3 已實測（2026-08-12），**結論與原本的假設相反**：
  - proxied + RFC1918 → 被拒，`code 9003`：`Target 10.9.1.241 is not allowed for a proxied record.`
  - DNS-only + RFC1918 → **API 接受，但權威 DNS 不回應**（NXDOMAIN）
  - 我第一次量成「可解析」並據此寫進設計，那是錯的且無法重現。第二次加上對照組才看清楚：同時建立的 `ctl-public → 203.0.113.9` 立即可解，`rfc1918-probe → 10.9.1.241` 回 NXDOMAIN。同一次查詢、同一個權威 NS，排除傳播與快取；zone 內無 wildcard
  - **這推翻 D6 的地基**，詳見 `design.md` D29
- [x] 1.4 決定由**節點自行查詢路由器**：客戶端回報需要客戶執行東西，而零 IT 客戶正是做不到的那一群；節點在同一個 LAN、同一個路由器後面，它看到的就是客戶端會看到的。已實作於 daily-check（先查公開 DNS 是否回 RFC1918，再問閘道是否回相同答案）
  - 但 1.3 之後這個偵測失去了原本的用途：擋住 RFC1918 的不是客戶路由器，是 Cloudflare 自己。偵測邏輯保留且會安靜跳過（公開查不到就不比對）
- [x] 1.0 appliance 是單節點，而 `jg-base/.../kube-system/kustomization.yaml:12` **無條件**部署 Spegel。**2026-08-10 已在測試機重現**：pod 永遠 `0/1`（`routing table is empty after bootstrapping`——單節點無 peer），且仍寫入 `_default/hosts.toml` 把所有 registry 導向本機死埠。惟 **image 拉取未受影響**（containerd 2.2.6 於 200ms 逾時後回退上游成功），故 jcom 記錄的「全叢集拉不動」應為舊 containerd 2.1.6 的行為。profile 仍須關掉 Spegel，但非緊急。**已由 2.8 的 suspend patch 處理**，並於 jgt-omni（單節點）確認 `suspend=true` 且 pod 已清除。詳見 `docs/template-lineage.md`
- [x] 1.5 **寬 pool 恆勝，規則是「建立時間最早者勝」**（2026-08-11，jgt-omni，Cilium v1.19.1）。窄 pool 只有在寬 pool `disabled: true` 時才被使用，證明它可用、只是不被選。三次實驗排除了另兩個假說：不是字典序（`aaa-spike-narrow` 輸給 `spike-wide`），也不是「最具體者勝」。
  - **直接後果**：不能在既有 `pool` 旁邊「加一個窄 pool」期待它被優先——jg-base 的 `pool` 在每個叢集上都是最早建立的，永遠贏。**4.6 必須收窄既有 pool，不能新增。**
  - **附帶確認 D3a（含一次自我更正）**：初測我的 spike pool 漏寫 `allowFirstLastIPs`（未指定＝可配發），拿到網路位址 `192.0.2.0`，我一度據此把風險上調；那是量到自己的設定。jg-base 明寫 `allowFirstLastIPs: "No"`，照抄補測後第一個配發是 `.1`。**D3a 原本的敘述就是對的**：第一個自動配發的 LB IP 就是預設閘道 `10.9.1.1`，且 `l2-policy` 的 `loadBalancerIPs: true` 無 serviceSelector，會直接 ARP 廣播出去。目前沒出事，只因三個現有服務都用 `lbipam.cilium.io/ips` 釘死位址，自動配發從未發生
- [x] 1.6 **確認**：單一位址 pool + 相同 `sharing-key`，port 不衝突者共用同一位址（`s1:80` 與 `s2:8080` 同得 `203.0.113.50`）；port 衝突者**拿不到位址**，並回報 `cilium.io/IPAMRequestSatisfied = False`。
  - **但 reason 是誤導的**：`reason=out_of_ips`，訊息為 *All enabled CiliumLoadBalancerIPPools that match this service ran out of allocatable IPs*——實際原因是共用位址上的 port 相撞，不是位址用盡。4.9 讓 daily-check 監看這個條件是對的（失敗可觀測），但**告警內容會把維運者指向錯誤的方向**，需要在告警文案裡點出「單一位址 profile 下，這通常代表 port 衝突」
- [x] 1.7 **確認，且比要求的更多**：`spec.infrastructure.annotations` 與 `spec.infrastructure.labels` **都**逐字傳到產生的 Service。labels 會傳這點是必要的——pool 的 `serviceSelector` 只能選 Service，而產生的 Service 預設只有 Envoy Gateway 自己的標籤，沒有 labels 傳導就無法讓它落進指定 pool。
  - 功能面也驗過（不只是「註解有出現」）：單一位址 pool 下，ns `spike` 的 Gateway（:80）與 ns `default` 的普通 Service（:9090）帶同一組 `sharing-key: gwshare` + `sharing-cross-namespace: "*"`，兩者同得 `203.0.113.90`，皆 `IPAMRequestSatisfied=True`。跨 namespace 共用經由 Gateway 傳導的 key 成立
  - 現網佐證：`envoy-internal` 的 `spec.infrastructure.annotations` 已帶 `lbipam.cilium.io/ips: 10.9.1.241`，產生的 Service 上原樣存在且生效

## 2. CUE schema 與範本（jg-cluster-template）

- [x] 2.1 `cluster.schema.cue` 加入 `deployment_profile`（三值、無預設）與 `storage_backend`（兩值）
- [x] 2.2 `nas_server` / `nas_path` 改為 `storage_backend: nfs` 時才必填；`nas_coding_path` 維持 optional
- [x] 2.3 appliance 下 `cluster_api_addr` / `cloudflare_gateway_addr` **不存在**（非「固定 10.9.9.x」——design D3 已改：cloudflared 走 ClusterIP DNS、API 走 Omni proxy，兩者都不需要位址）；`prosumer`/`full` 維持必填與互斥檢查
- [x] 2.4 appliance 下誤填 `cluster_gateway_addr` / `cluster_dns_gateway_addr` / `mqtt_lb_ip` 一律拒絕（看起來像設定了什麼、實際無人讀取）
- [x] 2.5 appliance ⇒ `provisioning_path: "omni"`（手動 Talos 需要零 IT 客戶給不出的節點資訊）
- [x] 2.6 新增 `backup_r2_*` 四欄位；appliance 下必填（單節點本機碟無備援，不該渲染出資料無保護的叢集）
- [x] 2.7 `plugin.py` 衍生 `default_storage_class`（nfs→sc-nas / 否則 local-path）與 `is_single_node`（appliance 恆真；talos 依節點數；其他 Omni 叢集無從判定故為 false）
- [x] 2.8 base app 依 profile gating（**非** extras 過濾——初版誤判 `storage/nfs-subdir` 為 extra，2026-08-11 實測發現）：`ks.yaml.j2` 由 `cluster.yaml` 生成 `suspend: true` patch，目前涵蓋 `nfs-client-provisioner`（非 nfs backend）與 `spegel`（單節點）。詳見 `design.md` D11
- [x] 2.9 `cluster-secrets.sops.yaml.j2` 加入 `BACKUP_R2_*`；並為改成 optional 的位址與 NAS 欄位補上顯式 `default()`（原本無防護，makejinja 的 chainable-undefined 會靜默渲染成空字串）
- [x] 2.10 `cluster.sample.yaml` 重組：新增 §0 Profile 置頂，標註 `(appliance: n/a)` 的欄位，NAS 改為條件必填，新增備份區塊
- [x] 2.11 三個 profile 各跑一次完整 `task configure` 皆通過，輸出符合預期（appliance 位址空/備份有值/extras 被過濾；full 位址與 NAS 齊全；prosumer+talos 的 coredns 推導為 10.43.0.10）

## 2c. 實測揭露的缺口（2026-08-11，jgt-omni 叢集）

- [x] 2c.1 已實作並在活叢集驗證：suspend patch 生成正確、Flux 已套用（`suspend=true`）、刪除後兩分鐘內未重建。`local-path` 叢集的失敗原因已精確佐證——`NAS_SERVER`/`NAS_PATH` 為空導致 Deployment `nfs.server: Required value`
- [x] 2c.4 新增可選欄位 `single_node`（Omni 路徑渲染期無法得知節點數，`nodes` 恆為 `[]`）；未宣告時假設有 peer——猜錯只是多跑一個能用的元件，反向猜錯會靜默停掉需要的
- [x] 2c.5 遷移步驟已在 jgt-omni 實測確立：**刪除被 suspend 的 Kustomization 無效**（prune finalizer 被 suspend 擋住，資源全留）；有效做法是直接 `kubectl delete hr`，helm uninstall 會連帶清掉它建立的 StorageClass / ServiceAccount。之後 `cluster-apps-base` 重建子 Kustomization 時 suspend 守住，資源維持消失。順序必須是「先刪資源、再靠 suspend 擋重建」。詳見 `design.md` D11
- [x] 2c.2 **原診斷是錯的，模板其實表達得出來**。實測 `claude_instances: []`：makejinja **並沒有略過**檔案，它產生了一個只含註解的 `helmrelease.yaml`，`kustomize build` 成功並輸出 0 個物件，`task configure` rc=0。會失敗的是「檔案不存在」那種情況（`evalsymlink failure`），而那不會發生
  - 原本記的失敗鏈是推論出來的，沒有跑過。實際跑一次就散了
- [x] 2c.3 已加強制檢查，而且**擔憂完全成立**——四個叢集的憑證逐一檢查後全部不合格：

  | 叢集 | 問題（未輸出憑證值） |
  |---|---|
  | jg-jiahd | 使用者名稱 `admin`、密碼 9 字元 |
  | jcom | 使用者名稱 `admin`、密碼 9 字元 |
  | jgt-omni-accept | 使用者名稱 `admin`（密碼長度足夠） |
  | jgt-talos-accept | 密碼 1 字元且為單一重複字元 |

  - 檢查**刻意不放在 CUE**：CUE 的約束失敗會把違規的值印進錯誤訊息，也就是把憑證洩漏到終端與 CI log——一個為了抱怨憑證太弱而洩漏憑證的檢查，比沒有檢查更糟。改為 `scripts/check-ttyd-credential.py`，只輸出「哪裡不對」與修復指令
  - 接在 `task configure` 的**渲染之前**：弱憑證應該擋住渲染，而不是部署之後才發現
  - 解析用 `yq` 而非自己切字串：憑證本身含冒號，行內又可能有註解，手工解析一度多讀了幾個字元，長度判斷因此不同——一個讀錯待檢物件的檢查器毫無用處
  - jgt-omni-accept 已換上強憑證並確認 `task configure` 通過。**jg-jiahd 與 jcom 未動**：換憑證會影響 ferry133 自己的存取，時機由他決定；叢集現在不受影響（Flux 不跑這個檢查），只有下次 `task configure` 會被擋

- [x] 2c.6 `local-path` 叢集原本**沒有 default StorageClass**：`sc-nas` 隨 nfs-subdir 一起移除後，叢集沒有任何 storage class（`storage/local-path-provisioner` 是 extra，未啟用）。已修：`ks.yaml.j2` 在 `storage_backend == 'local-path'` 時把它加進 Kustomization 清單，不論 `extras:` 有沒有列——profile 的預設 class 必須真的存在，而不只是「不是錯的那個」

- [x] 2c.7 `local-path` + 多節點改為明示選擇（方案 B）：CUE 要求 `single_node` 必須宣告；多節點時另需 `accept_node_pinning: true`，缺值或 `false` 皆拒絕。實作上繞過三次 CUE 自我滿足的陷阱，見 `design.md` D13
- [~] 2c.8 已實作 Longhorn（非 Rook-Ceph——3 節點家用叢集用 Ceph 過重）與第三個值 `storage_backend: "replicated"`：
  - jg-base `storage/longhorn`，預設 suspend；2 副本而非 3（一台可停機或 drain，仍有一份副本加一個重建目的地，只花三分之二空間；第三份副本擋不了真正威脅家用叢集的整站失效，那是異地備份的職責）
  - **不設為叢集預設 class**：bulk 資料不需要複製，設成預設會把既有 PVC 全部悄悄搬過去
  - namespace 標 `privileged`：Longhorn 掛 host path 且需要 mount propagation，Talos 預設 `baseline`——與 2c.11 的 storage namespace 同一道牆、同樣的安靜失敗方式
  - CUE：`single_node: true` 時**拒絕** `replicated`（單節點的「複製」是同一顆碟上的兩份副本，付了 Longhorn 的代價卻沒有保護）。六種組合已驗證
  - `db_storage_class` 刻意**不隨 backend 自動變成 `longhorn`**：裝了 Longhorn 不等於資料庫搬過去。忘記設不會靜默——資料庫仍在 node-local class，`accept_node_pinning` 閘門因此觸發，而它問的正好就是被忘記的那件事。（初版讓它自動推導，被 `check-template-integrity` 的「一個欄位兩個預設」規則擋下，那是對的：CUE 宣告 `local-path` 而 plugin 算出 `longhorn` 時，`_uses_node_local` 會依錯的值判斷）
  - **未在任何叢集實際部署**，因此標 partial。Longhorn 需要 `iscsi-tools` 與 `util-linux-tools` 兩個 Talos system extension 加上 `/var/lib/longhorn` 的 rshared 掛載——**manifest 裝不了這些**，而少了它們 pod 會起來、回報健康、然後掛載不了任何 volume。節點變更需要換 schematic 並逐台重開機
  - `docs/operations/replicated-storage.md` 寫明前置需求（Omni 與手動 Talos 兩條路徑）、驗證方式，以及**一張誠實的取捨表**：對 jg-jiahd（3 節點、8.7 MB 資料庫、已驗證的每日還原路徑）而言「釘住 + 備份」是站得住腳的，Longhorn 要在 RPO 真的重要、資料大到還原很慢、或節點重開頻繁到人工復原不再罕見時才值得。文件也記下第三條路：用 CSI 拿 NAS 的 iSCSI block（同樣需要那個 extension，但不多一層複製）

- [x] 2c.9 claude-code 的 `coding` volume 硬寫 `type: nfs`：無 NAS 時 `server`/`path` 渲染成空字串，chart schema 拒絕，**整個 release 裝不起來**。已改為由 `nas_coding_path` 條件渲染
- [x] 2c.10 claude-code 兩個 PVC 硬寫 `storageClass: sc-nas` → 改用 `default_storage_class`；同時 `replicas: 0` 配上 `WaitForFirstConsumer` 會讓 Helm 等一個依定義不會發生的綁定，已加 `install`/`upgrade` 的 `disableWait: true`。NFS 的 `Immediate` 綁定讓這個相撞在有 NAS 的叢集上不會出現
- [x] 2c.11 jg-base `storage` namespace 缺 PodSecurity 標籤，Talos 預設 `baseline` 擋掉 local-path provisioner 的 hostPath helper pod：provisioner 本身 Running、Kustomization Ready，但 PVC 永遠 Pending，錯誤只留在 PVC event。已於 jg-base `05b1501` 標為 `privileged`
- [x] 2c.12 上述五項合起來是同一個假設的五個位置（claude-code 長在有 NAS 的叢集上），且**全部只在 `local-path` 出現**——即 appliance 的標準組態。已在 jgt-omni 端到端驗證 `im.janncot.cc`：pod `1/1 Running`、兩個 PVC Bound 於 local-path、憑證 Ready、HTTP 401（ttyd basic auth，預期值）。詳見 `design.md` D14

- [x] 2c.13 `storage/local-path-provisioner` 由 extra 改為 base app 且永不 suspend（jg-base `3d87da3`）：它不是 NFS 的替代方案而是 node-local 層，有 NAS 的叢集同樣需要（否則 6.4 在 jg-jiahd 無處可放 DB）。`ks.yaml.j2` 的 auto-add 移除，改列入 `_now_base`。已在 jgt-omni 實測遷移完成：`local-path-provisioner` 現由 `cluster-apps-base` 擁有、路徑指向 `apps/base/`、StorageClass 回歸、PVC 全程 Bound。詳見 `design.md` D15
- [x] 2c.14 `accept_node_pinning` 的 predicate 已改為 `_uses_node_local`：`storage_backend == 'local-path'` **或** 啟用了 `#BlockTierExtras`（`claudecode/postgres`、`default/mariadb`、`default/postgres`、`freepbx/freepbx`）任一。有 NAS 的多節點叢集跑 DB 一樣被釘死，只是路徑不同，舊 predicate 會直接放行。`extras` 因此由 optional 改為 `*[] | [...string]`，讓判斷式能無條件讀取。七種組合皆已用 `cue vet` 驗證（含「nfs + 多節點 + 無 DB extra → 通過」與「nfs + 多節點 + postgres → 拒絕」）
- [x] 2c.15 jg-base README 的 extras→base 遷移 runbook 是錯的，且從未被執行過（jcom 事後補寫）。實跑後 release 照樣被 uninstall：`spec.prune` 不管刪除串聯——CRD 定義 `deletionPolicy` 才是，`MirrorPrune` 才會讀 `prune`，而本模板每個 Kustomization 都明寫 `deletionPolicy: WaitForTermination`；且線上 patch 會被母 Kustomization 的下次 apply 覆蓋，suspend 母體也不可靠（`Kustomization/flux-system` 由 flux-operator 管）。已改為「走 git 分兩次 push」（jg-base `db2568a`），詳見 `design.md` D16

- [x] 2c.16 `claude_code_always_on` 欄位（預設 off）：`replicas` 從模板寫死的 0 改為由 `cluster.yaml` 宣告。起因是 jgt-omni 的 `im` 今天在我反覆 reconcile 時被 Flux 校正回 0 → `im.janncot.cc` 503——先前那個一直活著的 pod 是**漂移**（更早驗證時手動 scale 上去、沒寫回宣告）
  - **刻意不照 jg-jiahd 的做法**：那邊是手改自己那份 `helmrelease.yaml.j2` 設 `replicas: 1`，而那份本地分歧正是 3.1 同步時要特別保護的東西之一。同一個需求出現第二次就該是欄位，不是第二份分歧；jg-jiahd 未來可改用它把那段收掉
  - 順帶把 claude-code 的兩個 PV 重建（我在清 Longhorn 時的 `kubectl delete pv --all` 波及了它們，卡在 `Terminating`）。新 PV 無 deletionTimestamp，`.claude` 需重新登入一次

## 3. 既有叢集遷移（不改變行為）

- [x] 3.1 **已對 jg-jiahd 實際套用**（2026-08-11）。先在完整副本驗過再上線，結果與副本逐字相同：`ks.yaml` **byte-identical**（唯一差異是把過期註解 `jgu5` 改成 `jg-jiahd`——repo 2026-05-30 已改名），`cluster-secrets` **+7 鍵、0 變更、0 移除**：4 個空的 `BACKUP_R2_*`、`DEFAULT_STORAGE_CLASS` 與 `DB_STORAGE_CLASS` 皆為 `sc-nas`、`LOCAL_PATH_IS_DEFAULT=false`。上線後全部 Kustomization Ready、`sc-nas (default)` 未變、`postgres-data` PVC 仍是 2026-06-19 那一個、`cc` pod 未重啟
  - 只同步了 ② 需要的 4 個檔案（schema / plugin / cluster-secrets / ks.yaml.j2），並把 jg-jiahd 的 QUIC workaround 重貼回去。**其餘仍分歧**：無 `templates/config/talos/`、無 `nodes.yaml` 與 `nodes.schema.cue`、無 `.taskfiles/talos/`、無 `check-template-integrity.py`、`bootstrap` 與 claude-code 模板仍是舊世代（`cc` 的 `replicas: 1` 與 image tag 是刻意的本地值）。完整世代同步屬 ① / ⑤，不在 3.1 範圍
- [x] 3.2 jcom 遷移**已完成**（2026-08-12，由 ⑤ 的 Group 6 執行）：模板全樹同步、兩個手寫例外變成宣告、六個 LB 位址不變。原文：阻塞於 `reconcile-jcom-lineage`：其 `templates/` 是更舊的世代（`SECRET_DOMAIN`、無儲存分層鍵），`task configure` 渲不出 `DB_STORAGE_CLASS`
  - [x] 3.2a **但 jcom 被 2c.13 弄壞了，已修**：`storage/local-path-provisioner` 移入 base 後，jcom 的 `extras:` 仍列著它，`extras-local-path-provisioner` 指向已不存在的路徑而 NotReady（約 72 分鐘）。資源全程安全——該 Kustomization 建不起來就不會 prune。修法是從 `extras:` 移除後 `task configure`，渲染差異恰好只有那一個 Kustomization 區塊，secret 值 0 變更
- [x] 3.3 未遷移時 `cue vet` 擋下且 `kubernetes/` 完全未被寫入（實測 0 個變更）

## 4. LAN 位址配置（jg-base）

- [x] 4.1 `network/lan-address` 元件已實作（jg-base）：hostNetwork + `NET_RAW`，由 `NODE_CIDR` 找出對應介面，**從子網高位往下掃**（`.254 → .200`）——路由器發 DHCP 租約絕大多數從低位開始，高位比較可能長期空著。跳過節點自身持有的每一個位址與慣例閘道 `.1`
  - 常駐 Deployment 而非 CronJob：appliance 首次開機不該等排程才有位址，而且這個迴圈同時就是 4.4 要的持續撞號監看
  - **自己的 namespace**：Talos 預設 `baseline` 同時禁止 hostNetwork 與 `NET_RAW`，元件根本起不來（與 2c.11 的 storage namespace 同一類缺陷，同樣是實跑才發現）。標 `network` 會把 cloudflared / envoy / k8s-gateway 一起升到 privileged，因此改為專屬 namespace
  - 非 appliance 一律 suspend（沿用 2.8 的機制）：那些 profile 在 cluster.yaml 宣告位址，探測寫出的第二個 pool 會與宣告的重疊，而 Cilium 拒絕重疊（D27）
- [x] 4.2 唯一輸出就是 `pool-discovered` 這個 `CiliumLoadBalancerIPPool`，RBAC 也只給這一個資源名稱——沒有任何 Service 標註、模板或 schema 指名這個元件，所以之後換成 DHCP lease-holder 只要換掉這支腳本
  - **已在 jgt-omni 實測**（用拋棄式 pool 名稱，不動該叢集的正式 pool）：正確找出 `enp2s0`、排除節點自身的四個位址、以 ARP 選出 `10.9.1.254` 並寫入 pool，`conflict=False`
  - **重啟穩定性已驗證**：全新 pod 的第一輪輸出是 `keeping 10.9.1.254`（而非 `selected`），證明它讀回已發布的位址、重新 ARP 確認後沿用。這正是「重開機不會把所有 LAN 服務搬到新位址」的機制
  - 選定的位址每一輪都重新探測，而不是選一次就固定——ARP 只能證明「此刻沒人回應」，當下關機的裝置回來仍會撞號（D4）
- [x] 4.3 三個 LAN 服務都加上 `sharing-key` 與 `sharing-cross-namespace`（jg-base）。由 `lan_shared_addr` 一個欄位驅動：設了就把 `cluster_gateway_addr` / `cluster_dns_gateway_addr` / `mqtt_lb_ip` 三者都渲染成它，同時打開共用；沒設就各服務落到**自己的**預設 key（互異＝不共用），今日行為不變
  - **已在 jgt-omni 端到端驗證**：`envoy-internal` 與 `k8s-gateway` 共用 `10.9.1.241`，兩者 `IPAMRequestSatisfied=True`，pool 從 3 個位址縮成 2 個（`.241` 共用 + `.243` external）。`envoy-external` 刻意不掛——沒有 LAN 客戶端連它
  - spec 的三個場景都用 scratch 服務單獨驗過：跨 namespace 共用成立、缺一邊 `sharing-cross-namespace` 的那個拿不到位址且 `already_allocated_incompatible_service`、其餘不受影響
  - 標註值踩了兩個 YAML 陷阱（空字串在 Gateway CRD 上是 `null`；`*` 被 kustomize 去引號後成為 YAML alias），兩次都被 dry-run 擋在套用之前。預設值改為服務自身名稱／namespace，收斂時用明確的 `network,mqtt`。詳見 `design.md` D28
- [x] 4.6 已實作（jg-base `9b1530e`）。`pool` 保留 `cidr: ${NODE_CIDR}` 但加上 `disabled: ${LB_POOL_WIDE_DISABLED:=false}`，新增 `pool-narrow` 由 `${LB_POOL_BLOCKS:=[]}` 提供逐一位址的 range。**靠停用寬 pool 來收窄，不是加一個更窄的**——1.5 已證明最舊者勝，加窄的沒用。
  - 兩個變數的預設值都等於今日行為：cluster-secrets 還沒有這兩個鍵的叢集維持寬 pool + 空的 `pool-narrow`（空 pool 就是沒東西可發，無害）。**這一點是必要的**：CRD 並未要求 `blocks`，空的 blocks 會被接受並靜默清空整個 pool，所以「沒有預設值」不是安全的失敗，是無聲的斷線
  - envsubst 無法表達「退回 `NODE_CIDR`」：巢狀預設值裡的 `}` 會提前終止運算式，連帶把 YAML 弄壞（已用 `flux envsubst` 實測，設值與不設值兩種情況都壞）
  - 一併移除 jg-base 內兩個寫死的位址：`10.9.1.2`（mariadb）與 `10.9.8.8`（omni），與 6.1 的 NAS IP 同一類缺陷。兩者都以原字面值作為 substitution 預設值，未遷移的叢集行為不變
  - 三個活叢集的推導結果已與實際配發位址逐一比對，完全吻合（jg-jiahd 4 個、jcom 6 個、jgt-omni 3 個）。`cluster_api_addr` 刻意不納入——它是 Talos VIP，不是 Service
  - **初版的兩個 pool 設計是錯的，已改為單一 pool**（jg-base `7e180df`）：narrow 依定義是 wide 的子集，必然重疊，Cilium 一律以 `PoolConflict=cidr_overlap` 拒絕，`disabled` 不影響判定。兩個叢集上 `pool-narrow` 的 `IPsUsed` 都是 0——**一個位址都沒配過**，而服務靠 D26 的「既有配發不收回」撐著，直到 jgt-omni 刪掉 `envoy-internal` 才逼出來。1.5 沒抓到是因為它的兩個 pool 不重疊。詳見 `design.md` D27
  - 修正後三個叢集皆 `conflict=False`：jgt-omni `used=2/total=2`、jg-jiahd `used=4/total=4`、jcom `used=8/total=256`（未收斂，明寫整個 node CIDR）。jcom 為此在自己的模板補了一行 `LB_POOL_BLOCKS`
  - **已上線 jgt-omni 與 jg-jiahd**。兩段都先驗證「未帶變數時是 no-op」（`pool-narrow` 存在但為空、寬 pool 仍啟用、服務不變），再推 per-user 變數翻轉。切換皆在 10 秒內完成，位址一個沒掉，全部 Kustomization Ready
  - **危害已實證關閉**：narrow 後在 jgt-omni 建一個未釘位址的 LoadBalancer Service，得到 `ip=<none>` 與 *There are no enabled CiliumLoadBalancerIPPools that match this service*——在此之前它會拿走 `10.9.1.1`（LAN 閘道）並 ARP 廣播
  - jcom 尚未套用（模板世代較舊，見 3.2），維持寬 pool——這正是預設值要保障的情況，其服務全程未受影響
  - 4.8 一併踩到一個坑：`CiliumL2AnnouncementPolicy` **只有 v2alpha1**，我把整份檔案改成 v2 導致整個 manifest dry-run 失敗、Kustomization NotReady。Flux 的 dry-run 擋在套用之前，pool 與服務都沒被動到；已修正（jg-base `2fa30b6`）
- [x] 4.7 `envoy-external` 改用**專屬的 EnvoyProxy**（GatewayClass 上那個對每個 Gateway 都生效，無法只改一個），Service type 由 `${ENVOY_EXTERNAL_SERVICE_TYPE}` 控制，appliance 為 ClusterIP
  - **已在 jgt-omni 實測 spec 場景**：暫時改為 ClusterIP 後，`envoy-external` 沒有 LB 位址、pool 用量由 2 降為 1，而 `https://im.janncot.cc` 三次都正常回應——證明 cloudflared 確實經叢集內 DNS 名稱連線，公開 ingress 不依賴那個 LAN 位址。之後已復原為 LoadBalancer（jgt-omni 是 full profile），`.243` 回歸
  - `lbipam.cilium.io/ips` 保留非空佔位值：ClusterIP 時 LB-IPAM 根本不讀它，而空字串在 Gateway CRD 上是 `null`（D28）
- [x] 4.8 `networks.yaml` 的 apiVersion 已改為 `cilium.io/v2`（叢集實際服務且儲存的版本），隨 4.6 一併變更
- [x] 4.9 daily-check 新增兩項：所有 LoadBalancer 的 `cilium.io/IPAMRequestSatisfied` 不為 True 時回報 fail；以及探測位址的穩定性（改選時 warn）
  - **告警文案自己給解釋，不轉貼 Cilium 的訊息**：依 1.6，共用位址上的 port 相撞會回報 `out_of_ips` 並說「pool 位址用盡」，把維運者指向「pool 太小」，而真正原因是那個 port 已被佔走；單一位址設計下這兩者從訊息完全分不出來。同理 `already_allocated_incompatible_service` 通常代表少掛了 `sharing-cross-namespace`
- [x] 4.4 **D32 後語意收窄**：位址一旦被寫進路由器就是外部契約，自動改選會讓路由器指向沒有東西在聽的位址、且全部內網名稱同時失效。因此 appliance 出廠前要把探測到的位址提升為宣告值（`lan_shared_addr`），之後撞號**回報而不自動改選**。程序見 `docs/operations/router-dns.md`。以下為原實作：探測迴圈每輪重新 ARP 確認選定位址；一旦該位址開始有回應就改選，並把新舊位址寫在 pool 的 annotation 上（`confirmed-at` / `previous` / `reselected-at`）——**記錄放在 pool 而不是只寫 log**，因為 pool 是這個元件唯一的輸出，而沒人看的 pod log 不算記錄。daily-check 讀這三個 annotation，改選時以 warn 呈報（改選代表所有 LAN 服務換位址，快取舊位址的客戶端需要重指）
- [x] 4.5 `kubernetes/apps/base/network/lan-address/README.md` 明訂替換契約：必須產出名為 `pool-discovered`、僅含一個單位址 block 的 pool，重啟後沿用同一位址，且不得碰其他 pool；**不得要求變更 Cilium 設定、Service 標註、模板或 CUE schema**——若需要，代表契約被打破，該重新檢視邊界而不是放寬它。同時寫明 ARP 為何只是第一版而非最終版（它只能證明「此刻沒人回應」）

## 5. 內網服務 DNS（jg-base）

- [~] 5.1 已實作並在 jgt-omni 實測，**隨後移除**：記錄確實被建立（A → `10.9.1.241`、`proxied=false`、TXT owner 分離），但**沒有任何 resolver 解得到**（見 1.3 / D29）。留著只會發佈解析不了的記錄，因此撤回而非保留
- [x] 5.2 分離機制本身已驗證有效（這部分結論不受 1.3 影響）：`txtPrefix: k8s-internal.` + `txtOwnerId: internal`，兩個實例同時 `policy: sync` 於同一 zone，external 側六筆記錄（3 CNAME + 3 TXT owner=default）在第二實例運行期間**逐字未變**。若共用 owner id，彼此會把對方的記錄當成孤兒刪除
- [x] 5.3 D32 定案後改為：`k8s_gateway` 開關（原名 `dns_fallback`，那個名字描述的是一個不存在的角色），**所有 profile 預設開**，包括 appliance——它是唯一能回答內網名稱的東西，沒有可以 fall back 的對象。因 4.3 的 sharing-key 與 `envoy-internal`／`mqtt` 共用位址，不額外佔用 LAN 位址
- [x] 5.4 D32 後重寫：**直接問路由器解不解得出內網名稱**（不再與公開 DNS 比對——D29 之後那邊根本沒有答案可比）。解不出判 FAIL 並指向 `docs/operations/router-dns.md`；FAIL 會扣住 dead-man ping
  - 這個檢查存在的理由：路由器設定是安裝時的一次性動作，叢集無法強制它維持。重設、換機、ISP 推設定都會讓 LAN 上所有內網名稱同時失效，而**叢集本身完全健康**——正是沒人會歸因正確的那種故障
- [ ] 5.5 D32 後改寫語意：不再有「fallback 前後」可比（k8s-gateway 一直都在）。要驗的是**路由器設定完成後，LAN 客戶端用扁平 hostname 可存取**——需要一台 appliance 與一個可設定的路由器，屬 8.2 的驗收
- [x] 5.6 已驗證：第二個 external-dns 實例運行期間，`external.janncot.cc` / `flux-webhook` / `im` 三筆 CNAME 與三筆 `k8s.cname-*` TXT **逐字未變**，proxied 狀態也未變。實例移除後叢集回到原狀（`target: internal.janncot.cc` 已還原、`im.janncot.cc` 仍回 401）

## 6. 儲存分層（jg-base）

- [x] 6.1 **原診斷是錯的**：`storageClassName: ""` 在這裡不是 bug。它與同一份 manifest 裡的 PV 以 `volumeName` 靜態綁定，這是既有 NFS export 的正確用法，會立刻 Bound，不會 Pending。掃描找到的真缺陷是另一個：`server: 10.9.2.13`（ferry133 自己的 NAS）被寫死在 ~20 個叢集共讀的 repo 裡。已改為 `${NAS_SERVER}`（jg-base `676f311`）；在唯一啟用這些 extras 的叢集上解析為同一位址，PV 未變動——PV 的 `nfs.server` 是 immutable，這點必須先確認才能推。spec 的該條需求已一併改寫
- [x] 6.2 掃描完成：13 處 `storageClassName: ""` 全為靜態 PV/PVC 配對；4 個檔案寫死 NAS IP（linebot ×2、synophoto、default/postgres backup），已修。export path（`/volume3/knowledge` 等）仍為字面值——只有原生叢集啟用這些 extras，列為已知限制而非默默帶著
- [x] 6.3 無 NAS 的叢集原本**完全沒有 default StorageClass**：nfs-subdir 宣告 `defaultClass: true` 但在該處被 suspend，local-path 則從未宣告。已改為 `defaultClass: ${LOCAL_PATH_IS_DEFAULT:=false}`，其值恰在 nfs-subdir 未運行時為 true，兩者永不相撞。已在 jgt-omni 實測：`local-path (default)`，且一個不指定 class 的 PVC 成功 Bound → 掛載 → 寫入
- [x] 6.4 DB 資料卷改用 `${DB_STORAGE_CLASS}`（`claudecode/postgres`、`default/mariadb`、`default/postgres`）。`default/postgres` 原本**完全沒寫 class**，於是在 NFS 叢集上資料目錄靜默落在 `sc-nas`。substitution 預設值取 `sc-nas` 而非正確的 block tier：PVC 的 `storageClassName` 是 immutable，預設值只會在尚未遷移到 profile schema 的叢集上生效，而那些全是 DB 已在 NFS 上的 NFS 叢集——預設值的意思是「維持現狀」，真正的搬遷仍須 dump/restore。freepbx 已在 block tier，不動
- [x] 6.5 claude-code 工作區改用 profile 預設 class（已於 2c.9/2c.10 完成）
- [x] 6.6 已驗證：設了 `nas_coding_path` 時 `coding` 掛載渲染結果與先前逐字相同（`type: nfs` + `${NAS_SERVER}`）；未設時整段不存在，兩個 PVC 落在 `local-path`
- [~] 6.7 **jcom 已完成搬遷（2026-08-13）**；jg-jiahd 仍依 2026-08-11 的決定延後
  - jcom 是四個叢集裡唯一無取捨的：單節點，`local-path` 沒有釘死任何原本不會被釘死的東西。前置的模板世代同步由 ⑤ 解決
  - 三張表（`episodes` / `knowledge` / `working_memory`）**全部 0 列**——MCP memory server 從未寫入，所以搬的是 schema。仍先 `pg_dump`（6261 bytes、3 個 CREATE TABLE）
  - 還原 0 錯誤，逐表列數相符，`postgres-data` 現為 `local-path/Bound`，pod `1/1`
  - **順序踩了一次坑**：第一次刪 PVC 後 Flux 立刻重建，但用的是**尚未更新的** cluster-secrets，於是又建成 `sc-nas`——而 `storageClassName` immutable，改不了。正解是先確認叢集上的 `DB_STORAGE_CLASS` 已是新值，再刪 PVC。第二次照此順序一次成功
  - jg-jiahd 維持 `db_storage_class: "sc-nas"`：3 節點，搬到 local-path 是拿「可跨節點重新排程」換「正確的 fsync 語意」，而 2c.8 的複製式儲存兩者都給
- [x] 6.8 `_uses_node_local` 再修一次：`db_storage_class` 明寫為非 node-local 的 class 時，DB 就不在 node-local 上，pinning 閘門不該再問。predicate 改為 `storage_backend == "local-path"` **或**（`db_storage_class == "local-path"` **且** 有 block-tier extra）。這個錯誤是由 6.7 的決定當場暴露的——選了「不搬」才發現 schema 會要求承認一件不會發生的事。六種組合已驗證
- [x] 6.9 **還原演練**（延後搬遷的直接後果：jg-jiahd 的 DB 繼續待在 NFS 上，失效模式是靜默損毀，而唯一的救援就是那份日備份——它的 restore 半邊從未被執行過）。已在 jg-jiahd 以唯讀掛載備份卷的拋棄式 postgres 實測 `linebot-20260810.sql.gz`：10 張表列數與生產**逐表相同**，restore 0 error。前置條件一併查出：**必須先建 `linebot` role**，否則 dump 裡的 `OWNER TO` 全數失敗（表仍會建，但擁有者變成 postgres）。演練 pod 已刪除

## 7. Appliance 備份（jg-base）

- [~] 7.1 `monitoring/backup` CronJob 已實作（每日 02:00 台北，早於 08:00 健檢，讓失敗當天就被回報）：`pg_dump` 各資料庫 → tar → age 加密 → `aws s3 cp` 上傳 R2 → 依 `BACKUP_RETAIN_DAYS`（預設 30）清理舊檔
  - **agent 工作區刻意不備**（依 D8）：工作區檔案可重建，不可重建的每客戶 context 在資料庫層、已被 dump 涵蓋；且該 PVC 在 `claudecode` namespace，跨 namespace 掛不上，硬要備就得把這個 job 放進 claudecode，位置是錯的
  - 資料庫走 `pg_dump` 而非檔案層複製——執行中的 data directory 檔案複製不是備份，是 torn page
  - `BACKUP_AGE_RECIPIENT` 為空時**硬失敗而非略過**：把可讀的客戶資料上傳到別人的物件儲存，比不上傳更糟
  - **尚未驗證實際上傳**：手上沒有 R2 憑證。已驗證的是「未設定 → 印訊息 → exit 0」（7.5）與加密（7.3）。上傳與還原屬 8.3 的驗收
- [x] 7.2 備份內容僅有 `pg_dump` 產出的 `.sql`，腳本不讀取任何 manifest 路徑。理由已寫進腳本註解：manifests 的權威副本在 git，從封存還原只會還原一份較舊的快照
- [x] 7.3 已實測：用叢集的 recipient 加密一段標記字串後，密文中**找不到明文標記**（grep 計數 0）；用另一把 age key 解密得到 `no identity matched any of the recipients`；用叢集自己的 `age.key` 才解得出。持有 R2 憑證者能取得的就是那段密文
- [x] 7.4 daily-check 讀最近一次成功的 backup Job 完成時間：>48h 判 FAIL（FAIL 會扣住 dead-man ping，因此即使信件本身沒寄達也會浮現）、>26h 判 warn、其餘 ok。已設定但從未成功過也判 FAIL
- [x] 7.5 已在 jgt-omni 實跑（該叢集無 `backup_r2_*`）：job `succeeded=1`，輸出 `off-site backup not configured — set backup_r2_* in cluster.yaml`。daily-check 對應記 ok 而非 fail——「沒設定」是這個叢集的陳述，不是故障；appliance 因 schema 必填而到不了這個分支
- [x] 7.6 `docs/operations/age-key-escrow.md` 寫明流程，並新增 `age_key_escrowed` 欄位：**appliance 未宣告或宣告 false 一律拒絕渲染**（沿用 D13 的模式，不給預設值，不能由 CUE 代簽）。四種組合已用 `cue vet` 驗證
  - 理由：備份加密到叢集自己的公鑰，`age.key` 是唯一能讀它的東西，而在單節點 appliance 上它就放在備份要對抗的那顆碟上。**未 escrow 的金鑰讓備份變成沒人打得開的密文**——那比沒有備份更糟，因為它看起來像保護
  - 文件也要求以 `age-keygen -y` 對**escrow 副本**驗出的公鑰比對 `.sops.yaml`：被截斷的金鑰副本，看起來和好的一模一樣

## 8. 驗收

- [x] 8.7 收窄 pool 的驗收**不能**問「narrow 之後有沒有壞」——漏列位址時那個問題也會答「沒有」。必須在套用前證明 pool 涵蓋當下每一個已配發位址（`kubectl get svc` 的實際集合 vs 渲染出的 `LB_POOL_BLOCKS`）。已配發的位址不會因來源 pool 消失而被收回，要到 Service 下次重建才失敗。詳見 `design.md` D26。已實作為 `scripts/check-lb-pool-covers-live.py`，套用前對 jgt-omni 與 jg-jiahd 各跑一次皆通過

- [ ] 8.1 在 scratch 叢集完成一次 appliance profile 全新部署，客戶端輸入為 0 項
- [ ] 8.2 從 LAN 用戶端驗證內網服務可用扁平 hostname 存取，且未變更路由器或裝置設定
- [ ] 8.3 完成還原演練：僅用備份封存 + escrow 的 `age.key`，在新叢集還原並比對資料一致
- [ ] 8.4 撰寫還原程序文件，內容須與演練實際步驟逐字一致
- [ ] 8.5 回寫所有 spike 結論到 `design.md` 與相關 spec，確認無「待驗證」項目遺留
- [ ] 8.6 每個 profile 的驗收都必須**在該 profile 上實跑到工作負載就緒**，不得只驗 `task configure` 的輸出。2c.9–2c.11 那四道渲染期缺陷全部無聲通過了 `task configure`（見 `design.md` D14）
