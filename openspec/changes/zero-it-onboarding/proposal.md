## Why

`deployment-profiles`（②）讓 appliance 的客戶必填欄位降到 0，`factory-agent`（③）讓部署流程無人介入。但客戶那一端仍然沒有東西：他收到一個紙箱，不知道要做什麼、做完了不知道成功沒有、出錯了不知道找誰。

現行 `README.md` 也無法擔任這個角色——它同時服務三種讀者（operator、進階使用者、上游殘留），而且已經與 repo 脫節：`:102` 的 `gh repo create --template onedr0p/cluster-template` 指向上游而非本 repo，`:205` 的 `just bootstrap talos` 沒有對應的 justfile，`:20` 說「6 stages」但實際寫到 Stage 7，`:243` 的 `cp kubeconfig-sa kubeconfig` 與 `CLAUDE.md` 明文禁止的事情直接衝突。一份自己都不正確的文件，不可能拿去給不懂 IT 的人照著做。

此外，②的 DNS rebinding protection 偵測（task 1.4）卡在同一個地方：偵測必須從 LAN 上的用戶端視角執行，而叢集內看不到那個視角。客戶手上的手機是唯一在正確位置的裝置。

> 依賴：`deployment-profiles`（②）與 `factory-agent`（③）。本 change 是客戶接觸面，站在兩者之上。`revive-talos-path`（①）不被本 change 取代——手動 Talos 路徑保留在給進階使用者的文件裡。

## What Changes

- **文件依讀者拆分**。`README.md` 收斂為簡短入口；新增 `README-zero-IT.md` 給零 IT 客戶；進階使用者與手動路徑保留獨立文件；operator 的可執行 runbook 由 ③ 的 skill 承擔，本文件只連結不重複。
- **修正 `README.md` 的既有錯誤**：上游 repo 名稱、不存在的 `just bootstrap talos`、stage 數量不符、與 `CLAUDE.md` 衝突的 kubeconfig 覆蓋指示。
- **零 IT SOP 以「三個物理動作」為全部內容**：開箱、插網路線、插電開機。其餘一律不出現在客戶文件裡。
- **文件必須在零連線狀態下可用**：客戶收到箱子時網路還沒通，SOP 必須是紙本隨箱出貨，QR code 只是輔助入口而非唯一入口。
- **新增 onboarding 溝通管道（LINE bot）**，跑在 **factory 側（jcom）而非客戶叢集**——客戶叢集在 onboarding 當下還不存在。重用 `default/linebot` 既有的 webhook gateway 形態與 LINE 憑證欄位，不新建通知基礎設施。
- **LINE bot 承擔四件事**：三題 intake、部署進度推播、請客戶拍照回傳（燈號/螢幕）、出錯時的對話式排錯與升級。
- **新增現場診斷能力，分兩階段**。v0 以照片與對話取得現場資訊；v1 才做原生 App 補上 LAN 掃描（TCP connect port 50000）與 UDP 出口測試。v1 明確不在本 change 範圍，但 v0 的介面必須讓 v1 可以接上。
- **DNS rebinding protection 偵測**（② task 1.4）由本 change 的客戶端回報路徑提供，解除 ② 的阻塞。
- **零 IT 文件的驗收是實測**：交給一個不懂 IT 的人，在無協助的情況下完成三個動作並成功收到完成通知。與 ③ 的交接演練同一種驗收模式。

## Capabilities

### New Capabilities

- `zero-it-documentation`: 文件依讀者拆分的結構、各文件的邊界、正確性約束，以及零 IT 文件的可讀性驗收。
- `customer-onboarding-journey`: 客戶從收到箱子到系統可用的完整經歷、三個物理動作的邊界、各階段客戶收到什麼。
- `customer-communication-channel`: LINE bot 的職責、部署位置、intake、進度推播、照片回傳與對話式排錯。
- `on-site-diagnostics`: 需要從客戶 LAN 內部才能回答的診斷問題，v0（照片/對話）與 v1（原生掃描）的分界與介面。

### Modified Capabilities

（無。①②③ 的 spec 不因本 change 改變；本 change 只消費它們建立的能力。）

## Impact

**`jg-cluster-template`（本 repo）**
- `README.md` — 大幅縮減為入口，並修正四處既有錯誤
- 新增 `README-zero-IT.md`（繁體中文，客戶語言）
- 新增進階使用者/手動路徑文件（承接現行 README 的 Stage 內容，清理後）
- `CLAUDE.md` — 更新文件結構說明

**`jg-base`**
- 新增 onboarding bot 部署（factory 側，jcom）：沿用 `default/linebot` 的 webhook gateway 形態，但為獨立部署，不與客戶叢集的 linebot 混用
- `apps/base/monitoring/daily-check` — 無變更（③ 已加入停滯工單回報）

**`jcom`（user repo）**
- 新增 onboarding bot 所需的 LINE 憑證欄位（`line_channel_access_token`、`line_channel_secret`、`line_notify_group_id` 已存在於 schema，複用即可）

**實體交付物**
- 隨箱紙本 SOP（印刷品），內容與 `README-zero-IT.md` 同源
- 箱內 QR code 指向 LINE bot 加好友連結

**解除的阻塞**
- `deployment-profiles` task 1.4（DNS rebinding protection 偵測方式）在本 change 取得客戶端回報路徑後可以定案。

**待驗證（spike，不得當成既定事實寫入 spec）**
- LINE Messaging API 接收客戶上傳圖片的流程與大小限制。
- LINE bot 能否在客戶尚未有任何叢集時，僅以 factory 側服務完成 intake 與綁定（客戶識別如何與工單關聯）。
- iOS 對 LAN 掃描的實際限制（無 raw socket 故無 ARP；mDNS 需 `com.apple.developer.networking.multicast` entitlement 且需個案核准），確認 TCP connect 掃描是否足以回答 v1 的診斷問題。
- 紙本 SOP 的實測讀者是誰、如何取得不受污染的測試對象（測試者不得事先知道流程）。
