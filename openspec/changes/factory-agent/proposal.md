## Why

目前交付一台客戶叢集需要一個人坐在筆電前，依 README 走完 7 個 stage：開 Omni UI 點選、建 Cloudflare token 與 tunnel、從 template 建 repo、手填 `cluster.yaml`、`task configure`、push、`task bootstrap:apps`。整段 10–40 分鐘、橫跨 Omni / GitHub / Cloudflare / Kubernetes 四個外部系統，而且沒有任何狀態記錄——中途斷掉就得靠人回想走到哪，重跑還會建出第二條 tunnel 或第二個 repo。

`deployment-profiles`（change ②）把 appliance 的客戶必填欄位降到 0，代表這些值**全部可以由程式推導或供給**。缺的是一個持有跨系統憑證、能把整段流程跑完、斷掉能續跑的執行者。

同時，「客戶隨時能拿回鑰匙」目前只是口頭承諾：`age.key`、GitHub repo、Omni 控制權、Cloudflare 帳號分散四處，沒有任何一個動作能把它們一起交出去。服務結束時無法乾淨退場。

> 依賴：本 change 建立在 `deployment-profiles` 之上。`appliance` profile 與 `storage_backend` 軸必須先存在，factory agent 才有可自動填入的欄位集合。

## What Changes

- 在 jcom 叢集新增常駐的 **factory agent**（`factory.janncot.com`），跑在**獨立 namespace 與獨立 ServiceAccount** 上。現行 `claudecode/claude-code/app/rbac.yaml` 是單一 ServiceAccount 綁 cluster-admin、所有 instance 共用——`factory` 若沿用，等於把 Omni Admin SA、GitHub PAT、Cloudflare 母帳號 token 暴露給同 namespace 的 `cc` instance。
- factory agent 經 **ClusterIP 直連 Omni**（Omni 以 `omni/omni` extra 跑在同一個 jcom 叢集內）。連帶消除 `CLAUDE.md` 記錄的兩個既有痛點：不再需要 `kubectl port-forward -n omni svc/omni 18080:8080`，也不會踩到 Cloudflare Tunnel 破壞 gRPC trailers 的問題。
- 新增**端到端 provisioning 流程**：偵測 Omni 上的新機器 → 建立 cluster → 由 template 建立 user repo → 推導 `cluster.yaml` → `task configure` → push → 取得 kubeconfig → `task bootstrap:apps` → 等待 Flux 與 `im` 就緒 → 交棒給常駐 agent。整段必須**冪等且可續跑**。
- 新增 **provisioning 狀態追蹤**：每台客戶叢集開一個 GitHub Issue 當部署工單，label 表示階段、comment 記錄進度。重用既有的 `docs/agents/issue-tracker.md` 與 `docs/agents/triage-labels.md`，不另造 state store。
- 新增**每叢集服務身分**：以 Google Workspace（`janncot.com` 網域下，經 Admin SDK 建立）或 Cloudflare Email Routing 別名作為該叢集持有服務（Cloudflare 帳號等）的信箱。**明確不採用「自動建立消費者 Google 帳號」**——Google ToS 禁止自動化註冊且強制 SMS 驗證，繞過會導致帳號連同其上的 Cloudflare 一起被停用。
- 新增 **`task handover`**：一次動作把六樣東西交出去（`age.key` 經 `sops updatekeys` 換成客戶公鑰、GitHub repo transfer、Cloudflare 帳號信箱、Omni 控制權、Anthropic 憑證、k8s 存取），並產出交接封裝清單。驗收標準是**交接演練**：由一個沒有 ferry133 任何權限的人接手操作成功。
- 新增**通知與升級路徑**，重用既有零件（`monitoring/daily-check` 的 Gmail SMTP、healthchecks.io dead-man switch、`default/linebot`），不引進新的通知基礎設施。
- 新增**已知失敗的自動修復**：cloudflared 因 ISP 封鎖 QUIC 而 CrashLoopBackOff 的 workaround（`TUNNEL_TRANSPORT_PROTOCOL: http2`）已記錄於 `CLAUDE.md`，factory agent 應能自行偵測並套用。

## Capabilities

### New Capabilities

- `factory-agent-runtime`: factory agent 跑在哪、如何與 Omni 通訊、持有哪些憑證、與其他 claude-code instance 的隔離邊界。
- `cluster-provisioning-workflow`: 從機器上線到交棒給常駐 agent 的完整流程，及其冪等與續跑語意。
- `provisioning-state-tracking`: 以 GitHub Issue 作為部署工單的狀態模型、階段轉換與稽核軌跡。
- `cluster-identity-and-credentials`: 每叢集服務身分的建立方式、憑證清單、`age.key` escrow，以及登入身分與服務身分的分離。
- `cluster-handover`: `task handover` 的範圍、產出與交接演練驗收。

### Modified Capabilities

（無。本 change 建立的皆為新 capability；`deployment-profiles` 的 spec 不因本 change 改變。）

## Impact

**`jg-base`**
- 新增 `kubernetes/apps/base/factory/`（僅部署於 jcom）：namespace、獨立 ServiceAccount 與最小權限 RBAC、HelmRelease、HTTPRoute
- `apps/base/claudecode/claude-code/app/rbac.yaml` — 釐清共用 SA 的邊界，factory **不**沿用
- `apps/base/monitoring/daily-check` — 增加 provisioning 工單的逾期檢查

**`jg-cluster-template`（本 repo）**
- 新增 `.taskfiles/handover/` 與 `task handover`
- 新增 `.claude/skills/provision-customer-cluster/SKILL.md`——人可照著做、agent 可照著跑的同一份 runbook
- `CLAUDE.md` — 新增 factory agent 與交接流程章節

**`jcom`（user repo）**
- `cluster.yaml` 的 `claude_instances` 不新增 `factory`（它不是 claude-code instance，而是獨立 app）
- 新增 factory 專用 secret 欄位（Omni Admin SA、GitHub PAT、Cloudflare 母帳號 token、Workspace Admin SDK 憑證）

**外部系統**
- Omni：新增 factory 專用 Admin service account
- GitHub：factory 專用 PAT（需 repo 建立、transfer、issue 權限）
- Cloudflare：母帳號 token；若採 Tenant API 開子帳號則需 partner 合約
- Google Workspace：Admin SDK Directory API 憑證

**已接受的風險**
- 所有客戶叢集的管理面集中於 jcom 上的 Omni。jcom 失效時客戶叢集本身照常運作，但遠端管理能力全失。依約定，量體成長後再處理 jcom 的高可用，本 change 不涵蓋。

**待驗證（spike，不得當成既定事實寫入 spec）**
- Omni 是否提供可靠的「新機器出現」事件或需輪詢；輪詢間隔與 API 成本。
- Google Workspace Admin SDK 建立使用者所需的最小權限範圍。
- Cloudflare Tenant API 的取得條件，以及不走 Tenant API 時「每客戶一個 Cloudflare 帳號」的可行替代。
- Omni cluster 控制權能否轉移給客戶自有的 Omni 實例，或交接時必須改採 Talos client cert。
