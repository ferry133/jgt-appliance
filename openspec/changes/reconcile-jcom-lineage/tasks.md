## 1. Spikes（先做，結果會改變範圍）

- [x] 1.1 jcom `ks.yaml.j2` 的 54 行**全數為新增**，兩個區塊、皆附事故說明，無舊版殘留：Cilium native-routing override（jcom 託管 Omni，MTU 1370 過小導致 SideroLink WireGuard `sendmmsg: message too long`）與 Spegel suspend。兩者根因相同——單節點
- [x] 1.2 `cilium_bgp_enabled` / `cilium_loadbalancer_mode` 在 jcom 與 jg-jiahd **皆為 0 消費端**（死碼），僅 genie1 仍在用；`spegel_enabled` 在 jcom 有 2 個消費端，仍活著
- [x] 1.3 **實測 jg-jiahd（3 節點）的命中率：4.4%**——`spegel_mirror_requests_total` 在約 3 小時、90 次請求的窗口內 `hit=4 / miss=86`。95.6% 的請求最後仍去外部 registry
  - 原因合理：家用叢集的 workload 多是 `replicas: 1`，只有 DaemonSet 會在多節點共用同一個 image，而那些在建叢集時就拉好了。P2P mirror 的前提很少成立
  - **但「移除比 gating 簡單」這個前提已經不成立**：gating 由 ② 的 2.8 免費提供了（`is_single_node` → suspend patch），所以保留的成本現在趨近於零，移除反而是額外變更
  - 爆炸半徑也比原本記的小：② 的 1.0 實測顯示 spegel 失敗時 containerd 2.2.6 會在 200ms 逾時後回退上游，image 仍拉得動；jcom 那次全叢集拉不動是舊的 2.1.6
  - **結論：不從 jg-base 移除。** 效益低但非零，gating 已解決唯一的硬傷（單節點），而移除是對所有叢集的變更。建議改為「多節點預設開、可關」——已由 2.8 的機制支援，不需新工作
- [x] 1.4 **決定：具名設定選項 + 全樹漂移偵測，不做通用的 patch 注入機制**
  - 需求規模在盤點後大幅縮小：真實例外只剩 jcom 的 Cilium native-routing 一個（jg-jiahd 的 QUIC 已因上游採納而消失，見 5.1）。為一個例外造一套通用 YAML 注入機制，複雜度遠超收益
  - 而 4.7 本來就寫著「同一例外出現於多個叢集 → 升格為設定選項」——若那是終點，就直接從那裡開始
  - **判準「能否偵測未宣告漂移」由 `scripts/check-template-drift.py` 滿足**：比對整個 `templates/`、`.taskfiles/`、`scripts/`，分三類報告 DRIFTED（內容不同）／BEHIND（本地缺少，代表收不到改進）／EXTRA（僅本地有）
  - 三個叢集實跑結果：jgt-omni 0 DRIFTED（僅缺今天新增的兩個腳本）、jg-jiahd 9 DRIFTED + 4 BEHIND、jcom 11 DRIFTED + 2 BEHIND（schema 255 行、plugin 164 行——印證它是更舊的世代）
  - 腳本的輸出刻意同時提醒**反方向**：一個因上游採納而變得多餘的例外，讀起來仍然像現行決策（5.1 的教訓）
- [x] 1.5 **已由 ② 解決**：新增 `single_node` 欄位（Omni 路徑渲染期確實無從得知，`nodes` 恆為 `[]`），並衍生 `is_single_node`——appliance 恆真、手動 Talos 依節點數、其他 Omni 叢集未宣告時假設有 peer。詳見 `deployment-profiles` 2c.4

## 2. 分岔清冊

- [x] 2.1 清冊格式定為：項目 / 位置 / 分類（收進模板・從叢集移除・宣告為例外）/ 現況。產出於 `docs/template-lineage.md`
- [x] 2.2 jcom 全部 7 個漂移檔逐項分類完成，共 17 項；其中 9 項已由 ① 收回模板
- [x] 2.3 jg-jiahd 僅 1 項（QUIC → http2），屬真正的 per-cluster 例外，待遷移到新機制
- [x] 2.4 無「不知道為什麼在這裡」的項目——每一項都有可追溯的理由，兩個 `ks.yaml.j2` 區塊皆附事故註解
- [x] 2.5 已收回模板的 9 項列於清冊並標記完成，避免重複處理

## 2b. 盤點時新發現

- [ ] 2b.1 模板 `cluster.schema.cue` 宣告 `cilium_bgp_router_addr` / `cilium_bgp_router_asn` / `cilium_bgp_node_asn` / `cilium_loadbalancer_mode` 四個欄位，**模板、cluster-secrets、jg-base 皆零消費端**（僅 genie1 在用）——接上或移除
- [ ] 2b.2 採納 jcom 的 `validate-talos-config` 任務
- [x] 2b.3 已採納 jcom 的 `cloudflare-tunnel.json` 前置檢查（由 `revive-talos-path` 5c.3 實作；2026-08-11 實測第二次踩到才修）
- [ ] 2b.4 單節點的 Cilium 設定（native routing + MTU 1500）與 Spegel 同屬「單節點安全性」，一併納入 3.x
- [ ] 2b.5 genie1 是第三支更舊的血脈（5 個 namespace 的 app 模板），本 change 不涵蓋，但需記錄以免「模板的後裔」被誤認為只有兩個 repo

## 3. 單節點安全性（jcom 遷移的前提）

- [x] 3.1 **已由 ② 的 2.8 解決**，但作法與原本設想的不同：jg-base 那份 `kustomization.yaml` 沒有改，因為 Flux 無法從那一端拒絕建立 Kustomization。改由 per-user repo 依 `cluster.yaml` **生成 suspend patch**——與 jcom 手寫的那段同型，只是來源從漂移變成宣告
- [x] 3.2 **已由 ② 解決**：`is_single_node` 於 `plugin.py` 衍生，`ks.yaml.j2` 據此生成 spegel 的 suspend patch
- [ ] 3.3 `01-apps.yaml.j2` 的 bootstrap 側 gating 與 jg-base 側一致（目前兩處控制互相打架：bootstrap 有 `spegel_enabled`、jg-base 無條件）
- [ ] 3.4 驗證單節點叢集完全不部署 Spegel，且不需任何 per-cluster patch
- [ ] 3.5 驗證多節點叢集行為不變
- [ ] 3.6 處理爆炸半徑：元件失敗或被移除時，它寫入的 `hosts.toml` 等節點層設定必須還原，不得留下指向死埠的 registry 轉址
- [ ] 3.7 驗證元件缺席 / 失敗 / 停用三種情況下，image 仍可從原 registry 拉取
- [x] 3.8 已回報：`deployment-profiles` 1.0 已標記完成，並註明 gating 由 2.8 的 suspend patch 承擔、已在 jgt-omni（單節點）確認 `suspend=true` 且 pod 已清除

## 4. Per-cluster 例外機制

- [ ] 4.1 依 1.4 實作機制
- [ ] 4.2 例外宣告須記錄「解決什麼問題」與「什麼條件成立時可移除」
- [ ] 4.3 實作例外清單的檢視方式
- [ ] 4.4 驗證例外範圍受限：宣告範圍外的共用行為不受影響
- [ ] 4.5 驗證共用改進仍能到達有例外的叢集
- [x] 4.6 `scripts/check-template-drift.py` 已實作並對三個叢集實跑（見 1.4）。DRIFTED 涵蓋任何手改共用檔案；BEHIND 額外回答一個原本沒被問的問題——**這個叢集正在錯過哪些改進**
- [ ] 4.7 定義「同一例外出現於多個叢集 → 升格為設定選項」的流程

## 5. 遷移既有例外

- [x] 5.1 **不需要新機制——這個例外已經不存在了**。jg-base commit `140d14c`（2026-07-23）把 `TUNNEL_TRANSPORT_PROTOCOL: http2` 與 `TUNNEL_POST_QUANTUM: false` 收為全域預設，而 jg-jiahd 的 patch 設的正是同樣兩個值，已經多餘了三個星期
  - 移除前三方逐字比對：patch 內容、jg-base 預設、活叢集上實際生效的環境變數，完全一致
  - **這也讓 CLAUDE.md 的 troubleshooting 段落過期**：它寫著「為什麼不改 jg-base？其他 cluster QUIC 正常，default 保留 QUIC 較好」——jg-base 早就改了。待更新
- [x] 5.2 已移除並推送。渲染後該區段與 jgt-omni **逐字相同**，分歧消除；活叢集上 cloudflared 的兩個環境變數不變、pod 未重啟（140 分鐘未動），是真正的 no-op
  - 過程中我第一次切割破壞了 YAML 結構（留下孤立的 `spec: values:` 與連續兩個 `target:`），而 `task configure` 仍 rc=0——**YAML 可解析不代表語意正確**。還原後改以完整區塊比對移除
- [ ] 5.3 jcom 的 Spegel suspend 改由 3.x 的 gating 取代（不是遷移到例外機制——單節點是通則不是例外）
- [ ] 5.4 驗證 jcom 在 gating 生效後不再需要該 patch

## 6. jcom 同步

- [x] 6.1 副本上已補齊，且不只那兩個欄位——完整清單：`deployment_profile: full`、`provisioning_path: talos`、`storage_backend: nfs`、`cluster_svc_cidr: "10.43.0.0/16"`、`single_node: true`、`db_storage_class: sc-nas`（DB 仍在 NFS）、`cilium_native_routing: true`、`omni_udp_lb_ip: "10.9.8.8"`、`claude_code_always_on: ["im"]`
- [x] 6.2 已隨全樹同步採用模板版
- [x] 6.3 同步 `makejinja.toml` 時一併帶入 `trello-notifier.sample.yaml`；模板版的 `render-configs` 會在渲染前 `cp -n` 建立它，所以 makejinja 的 data 宣告不會缺檔
- [x] 6.4 全樹同步（`templates/`、`.taskfiles/`、`scripts/`、`makejinja.toml`），漂移從 **13 個檔案降到 1 個**
  - **唯一刻意保留的是 `templates/config/talos/talenv.yaml.j2`**：jcom 是 Talos v1.12.4 / K8s v1.35.2，模板是 v1.13.8 / v1.35.1——盲目同步會升級 Talos 並**降級 K8s**。它承載的是 per-cluster 的版本狀態，不是模板內容，應排除在漂移比對之外
  - `01-apps.yaml.j2`：模板版的 bootstrap 完全不含 spegel（交給 Flux/jg-base），jcom 的 `spegel_enabled` 條件是舊世代做法。同步即解決 3.3 記錄的「兩處控制打架」
- [x] 6.5 副本驗證完成，`task configure` rc=0，渲染差異只有 3 個檔案。**而它抓到三個會壞的東西**：
  1. **`LB_POOL_BLOCKS` 漏了 `10.9.8.8`**（`omni/omni` 的 udp-gateway）：narrow pool 只含 5 個位址，活叢集有 6 個。依 D26 不會立刻壞，會等到那個 Service 下次重建才無聲失去位址。補 `omni_udp_lb_ip` 後，8.7 的檢查對活叢集 6/6 通過
  2. **claude-code `replicas: 1 → 0`**：jcom 的 `im` 會被關掉——與我今天在 jgt-omni 踩到的同一件事
  3. **我的 `claude_code_always_on` 設計不足**：jcom 舊模板寫的是 `1 if instance == "im" else 0`（im 常駐、cc 按需，活叢集確認 `im=1 / cc=0`），全域布林表達不出來。已改為 instance 名稱清單
  - **Cilium 例外由 `cilium_native_routing` 生成，內容指紋與手寫版完全相同**（`c73f48c3fe`）；`spegel` 的 suspend 同樣相符（`865a2051b0`）。新增的三個 suspend（longhorn / lan-address-probe / spegel）皆為預期
  - cluster-secrets 為純增鍵（`BACKUP_*`、儲存分層、`LAN_SHARING_*`、`NODE_DEFAULT_GATEWAY` 等），既有值除 `LB_POOL_BLOCKS`（narrow，已驗證）與測試用的 `TTYD_CREDENTIAL` 外未變
- [x] 6.6 **已對真 repo 執行並驗證**（2026-08-12）。渲染差異與副本完全一致（同樣 3 個檔案），套用後：
  - `routing-mode=native  mtu=1500  lb-mode=dsr` — Cilium 例外由 `cilium_native_routing` 生成後仍生效
  - `spegel` / `longhorn` / `lan-address-probe` 三個 suspend 皆 `true`，`cilium` 未 suspend 且 Ready
  - claude-code `cc desired=0` / `im desired=1 ready=1` — 與 `claude_code_always_on: ["im"]` 一致
  - 六個 LB 位址全部不變，spegel 零殘留
  - `ttyd_credential` 已輪替（原本是 `admin` + 9 字元密碼，守著一個 tunnel 對外曝光的 shell）
- [x] 6.7 同步時另外兩個**不可盲目同步**的檔案：
  - `.gitignore`：模板 repo 忽略 `/bootstrap/` 與 `/talos/`（本機產物），但 jcom 追蹤它們。兩者語意不同，同步會改變「什麼被提交」，超出模板同步的範圍。只補了缺的 `/trello-notifier.yaml` 一行
  - `.sops.yaml`：同步後出現 mode 644→755 的 diff。根因是模板 repo 的 `templates/config/.sops.yaml.j2` 權限是 `700`，而 makejinja 的 `copy_metadata = true` 會把權限帶到渲染產物——**一個模板檔的權限會傳染到每個 repo**。已在模板 repo 改回 644

## 7. 驗收

- [ ] 7.1 對已同步的 jcom 再套用一次後續模板變更，確認**不需手動合併**且其宣告的例外仍在
- [ ] 7.2 jg-jiahd 重跑 5.7 式比對，確認機制變更未影響它
- [ ] 7.3 人為在某叢集製造未宣告漂移，確認可被偵測並回報
- [ ] 7.4 單節點叢集端到端驗證：無 per-cluster patch 即可正常運作、image 拉取正常
- [ ] 7.5 回寫所有 spike 結論，確認無「待驗證」項目遺留
