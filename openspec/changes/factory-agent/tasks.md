## 1. Spikes（先做，結果會改變後面的設計）

- [ ] 1.1 確認 Omni 是否提供「新機器註冊」事件訂閱；若只能輪詢，測出可接受的間隔與 API 成本
- [ ] 1.2 確認 Google Workspace Admin SDK 建立使用者所需的最小權限範圍，以及是否非用 domain-wide delegation 不可
- [ ] 1.3 確認 Cloudflare Tenant API 的取得條件；若不可得，評估「單一母帳號 + 每叢集 scoped token」能否支撐交接
- [ ] 1.4 確認 Omni cluster 控制權可否轉移給客戶自有 Omni 實例；若不可，確定交接改發 Talos client cert 的做法
- [ ] 1.5 決定 factory 對客戶叢集憑證的存活期策略（長期持有 vs 每次向 Omni 重新取得），回寫 `design.md` Open Questions

## 2. Factory 執行環境（jg-base + jcom）

- [ ] 2.1 在 `jg-base` 新增 `kubernetes/apps/base/factory/`：namespace、獨立 ServiceAccount、最小權限 RBAC
- [ ] 2.2 驗證 factory 的 SA **不是** `claudecode/claude-code/app/rbac.yaml` 那個共用 cluster-admin SA
- [ ] 2.3 驗證同叢集的 `cc` instance 無法讀取 factory 的 secret（RBAC 拒絕）
- [ ] 2.4 建立 factory 的 HelmRelease 與 HTTPRoute（`factory.janncot.com`），登入白名單只含 operator
- [ ] 2.5 驗證客戶叢集的登入身分無法登入 factory
- [ ] 2.6 設定經 ClusterIP 直連 Omni，驗證不需 port-forward 且 gRPC streaming 呼叫不出現 trailers 錯誤
- [ ] 2.7 確認容器內具備完整工具鏈（`omnictl` `gh` `cloudflared` `age` `sops` `cue` `makejinja` `task` `kubectl` `helmfile`），版本與 repo pin 一致
- [ ] 2.8 驗證 image 內不含任何憑證材料，憑證全部 runtime 注入
- [ ] 2.9 建立憑證清單文件：每項憑證的用途、範圍、blast radius、輪替方式

## 3. 工單狀態機

- [ ] 3.1 定義工單 label 詞彙（有序階段），與既有 `docs/agents/triage-labels.md` 對齊
- [ ] 3.2 實作工單建立：交付啟動時開 Issue，記錄客戶、profile、預期機器
- [ ] 3.3 實作階段推進：完成一階段即換 label，任何時刻恰有一個階段 label
- [ ] 3.4 實作進度 comment：記錄動作、外部資源識別碼、驗證證據
- [ ] 3.5 加入防護：comment 寫入前檢查不含金鑰材料
- [ ] 3.6 實作 resume：從 label 與 comment 判定已完成階段並記錄跳過了哪些
- [ ] 3.7 實作矛盾處理：記錄狀態與觀察狀態不一致時停止並升級
- [ ] 3.8 在 `monitoring/daily-check` 加入停滯工單回報（階段 + 停留時間）

## 4. Provisioning 流程

- [ ] 4.1 實作機器註冊偵測，並與開放中的工單比對
- [ ] 4.2 未匹配任何工單的機器不得自動建叢集，改為回報 operator
- [ ] 4.3 實作 Omni cluster 建立（含 `cniConfig: none` 等首次開機前必須的 patch）
- [ ] 4.4 實作由 template 建立 user repo，名稱由 `cluster_name` 決定（決定性命名）
- [ ] 4.5 實作 Cloudflare tunnel 與 DNS 建立，名稱同樣決定性
- [ ] 4.6 實作 `cluster.yaml` 推導：網路值一律來自 Omni 回報的機器實際網路狀態，不接受人工輸入
- [ ] 4.7 串接 `task configure` → commit → push
- [ ] 4.8 實作 kubeconfig 取得與 `task bootstrap:apps`
- [ ] 4.9 實作完成判定：等到 Flux reconcile **且** 常駐 agent 可達，才算完成並記錄交棒
- [ ] 4.10 為每一步實作「先查後建」，驗證重跑不產生第二個 repo / tunnel / cluster
- [ ] 4.11 實作 QUIC 封鎖的自動修復（套用 http2 transport、驗證恢復、記錄動作）
- [ ] 4.12 實作未知失敗的停止與升級（不無限重試），附診斷證據
- [ ] 4.13 實作「機器未出現」的回報：列舉可能原因而不斷言，附非技術人員可執行的現場檢查清單

## 5. 身分與憑證

- [ ] 5.0 網域流程（D11）：客戶自有網域 → NS 委派到 operator 的 Cloudflare 帳號；zone 與 token 皆在 operator 側，客戶零輸入。含 operator 代購網域的選項
- [ ] 5.0a 驗證：零輸入 profile 的 provisioning 全程不向客戶索取任何 API token 或帳號憑證
- [ ] 5.0b 驗證：交接前後 hostname 完全不變，改變的只有「哪個帳號管這個網域的 DNS」

- [ ] 5.1 依 1.2 結論實作每叢集服務身分建立
- [ ] 5.2 明確禁止任何自動化消費者帳號註冊流程（程式與 runbook 皆須寫明）
- [ ] 5.3 實作登入身分設定：常駐 agent 白名單放客戶自己的信箱，服務身分不得為可登入身分
- [ ] 5.4 實作每叢集憑證清單的產生與更新（新增/輪替/移除時同步更新）
- [ ] 5.5 實作 `age.key` escrow，並讓 escrow 未確認時 provisioning 不得標記完成
- [ ] 5.6 為每項憑證撰寫就地輪替程序；`age.key` 輪替須以 `sops updatekeys` 就地重加密

## 6. 交接

- [ ] 6.0 交接封裝除列出「持有什麼」外，須逐項記載「要用它需要什麼能力」（D12 的不對稱）——操作 Cloudflare DNS、git 與 SOPS、Omni 或 Talos client cert

- [ ] 6.1 實作 `task handover`：SOPS 重新加密至客戶公鑰、repo transfer、Cloudflare 帳號信箱、Omni 控制權（依 1.4）、模型 API 憑證、k8s 存取
- [ ] 6.2 實作部分失敗的回報：列出成功與失敗項，不得回報成功
- [ ] 6.3 實作交接封裝產出：客戶持有什麼、各自用途、遺失的後果、需要的例行動作
- [ ] 6.4 實作交接後 operator 殘留存取的撤銷；保留支援關係時須在封裝明載保留了哪些
- [ ] 6.5 在 scratch 叢集執行交接演練：由無 operator 權限者只憑封裝完成 reconcile、解密 secret、登入常駐 agent
- [ ] 6.6 依演練結果修正，重跑至通過；未通過前不得對客戶宣稱可交接

## 7. Runbook / Skill

- [ ] 7.1 撰寫 `.claude/skills/provision-customer-cluster/SKILL.md`，每步含前置條件、指令、驗證斷言、失敗分支
- [ ] 7.2 由人工照 runbook 逐步執行一次完整 provisioning，修正指令與斷言的錯誤
- [ ] 7.3 交由 factory agent 自動執行同一份 runbook，比對結果一致
- [ ] 7.4 在 `CLAUDE.md` 新增 factory agent 與交接流程章節，並移除已被 factory 取代的手動 port-forward 說明

## 8. 驗收

- [ ] 8.1 以 scratch 工單完成一次全自動 provisioning，全程無人介入
- [ ] 8.2 在流程中途強制中斷 factory agent，驗證重啟後由工單續跑且無重複外部資源
- [ ] 8.3 模擬 QUIC 封鎖，驗證自動修復成功並留下記錄
- [ ] 8.4 模擬機器未上線，驗證回報列舉可能原因且不斷言
- [ ] 8.5 第一台真實客戶以「agent 執行、人在旁看」模式交付，事後檢討工單留痕
- [ ] 8.6 回寫所有 spike 結論到 `design.md` 與相關 spec，確認無「待驗證」項目遺留
