## Context

這個 change 不是設計出來的，是 `revive-talos-path` 的驗收工作（task 5.7）撞出來的。原本只想確認「模板改動不會弄壞既有叢集」，結果發現 jcom 根本收不了模板更新。

2026-08-09 逐檔比對（相對 `revive-talos-path` 動工前的模板 HEAD）：

```
jcom                                                      jg-jiahd
──────────────────────────────────────────────────────    ────────
ks.yaml.j2                     54 行                      19 行
.taskfiles/template/Taskfile.yaml  31 行                   —
plugin.py                      22 行                       —
.taskfiles/bootstrap/Taskfile.yaml 14 行                   —
bootstrap-apps.sh              10 行                       —
Taskfile.yaml                   4 行                       —
makejinja.toml                  2 行                       —
```

jg-jiahd 只有一個檔漂移（QUIC workaround），所以模板改動能乾淨套用、渲染結果零 diff。jcom 則是另一支血脈：它保留了完整的手動 Talos 工具鏈，而模板在某個時點把那些檔案拿掉了。

分岔是雙向的。實際內容：

**jcom 有、模板沒有**
- `plugin.py` 的 `talos_patches`、三個 node 預設、`cluster_svc_cidr: '10.43.0.0/16'`、`cilium_bgp_enabled`、`spegel_enabled`、`cilium_loadbalancer_mode`
- `.taskfiles/template/Taskfile.yaml` 的 `TEMPLATE_NODE_CONFIG_FILE`、`validate-talos-config`、`validate-kubernetes-config`（kubeconform）、`encrypt-secrets` 含 `TALOS_DIR`
- `01-apps.yaml.j2` 用 `spegel_enabled` 做單節點 gating

**模板有、jcom 沒有**
- `trello-notifier.yaml` 作為 makejinja data 檔（jcom 無此檔 → 套用模板的 `makejinja.toml` 會讓渲染中止）
- `bootstrap-apps.sh` 改用固定 namespace 清單（jcom 仍是舊的掃 `kubernetes/apps/*/`，在現行結構下會取到錯的 namespace）

`revive-talos-path` 已經把前四項的前半段拉回模板了——其中 `encrypt-secrets` 含 `TALOS_DIR` 與 kubeconform 接線是**比對 jcom 才發現模板漏掉的**，等於 jcom 已經在幫模板抓 bug，只是沒有人在看。


### 例外會自己消失，但沒有人會發現

盤點時 jg-jiahd 只有一個真正的 per-cluster 例外：強制 cloudflared 走 http2，因為該站點的上游防火牆擋 UDP 7844（QUIC）。2.3 把它分類為「真正的例外，待遷移到新機制」。

實作 5.1 時發現**它已經不是例外了**。jg-base commit `140d14c`（2026-07-23）把 `TUNNEL_TRANSPORT_PROTOCOL: http2` 與 `TUNNEL_POST_QUANTUM: false` 收為全域預設——那個 patch 設的正是同樣兩個值，已經多餘了三個星期。

沒有任何機制會告訴你這件事。例外一旦寫下就靜靜留著，而上游採納它的那一刻，沒有東西把兩者連起來。CLAUDE.md 到現在還寫著「為什麼不改 jg-base？其他 cluster QUIC 正常，default 保留 QUIC 較好」——那個判斷在 jg-base 改變的當天就過期了，但它讀起來仍然像現行決策。

**這正是 4.2 要求「例外須記錄什麼條件成立時可移除」的理由**，而這個案例顯示光記錄還不夠：條件成立時要有人去看。4.6 的漂移偵測應該一併回報「已與上游相同的例外」——它們是分歧清冊裡最容易清掉、也最容易被忽略的一類。

順帶：`storage_backend: replicated` 之後只剩 jcom 的 Cilium native-routing 一個真實例外，per-cluster 例外機制（Group 4）的需求規模因此比提案時小得多。

### YAML 可解析，不代表語意正確

移除那段 patch 時，我第一次的切割留下了孤立的 `spec: values:` 區塊和連續兩個 `target:`。`task configure` 回傳 0——`cue vet` 驗的是 `cluster.yaml`，kubeconform 驗的是渲染出的 Kubernetes 物件，而那段壞掉的結構仍是合法 YAML 且仍能組成合法的 Kustomization，只是 patch 目標錯了。

檢查鏈裡沒有一環會問「這個 patch 還是你想要的那個 patch 嗎」。還原後改以**完整區塊比對**移除（前後錨點都驗），並用「渲染後與另一個叢集逐字相同」作為驗收——那才是真正想要的性質。


### 一個例外不值得一套機制

提案時假設需要 per-cluster 例外機制（overlay 目錄／通用 patch 注入／條件渲染）。盤點後真實例外只剩**一個**：jcom 的 Cilium native-routing（它託管 Omni，tunnel 模式的 MTU 1370 太小，SideroLink WireGuard 會 `sendmmsg: message too long`）。

jg-jiahd 的 QUIC workaround 因上游採納而消失，jcom 的 Spegel suspend 則是單節點通則而非例外——② 的 gating 已經涵蓋。

而 4.7 本來就寫著「同一例外出現於多個叢集 → 升格為設定選項」。**若那是終點，就從那裡開始**：具名設定選項，不造通用注入機制。為一個例外造一套能表達任意 YAML 的機制，複雜度遠超收益，而且那種機制本身會變成新的漂移來源（任意 YAML 無法被 schema 驗證）。

真正缺的不是機制，是**偵測**。

### 漂移偵測要回答兩個方向，而第二個沒人問過

`scripts/check-template-drift.py` 比對整個 `templates/` / `.taskfiles/` / `scripts/`，分三類：

| | 意義 |
|---|---|
| DRIFTED | 內容不同——例外，或沒人寫下來的手改 |
| BEHIND | 本地缺少——**這個叢集正在錯過哪些改進** |
| EXTRA | 僅本地有——整份新增，需要交代 |

原本 4.6 只要求偵測「手改」。實跑後 BEHIND 這一類同樣重要：jg-jiahd 缺 4 個檔（含整個 `.taskfiles/talos/`），jcom 缺 2 個。分歧不只是「改了什麼」，也是「沒收到什麼」——而後者不會有任何症狀，直到有人問「為什麼這個叢集沒有那個功能」。

三個叢集的形狀因此一眼可辨：

```
jgt-omni    0 DRIFTED   2 BEHIND    幾乎對齊
jg-jiahd    9 DRIFTED   4 BEHIND    3.1 只同步了 ② 需要的四個檔
jcom       11 DRIFTED   2 BEHIND    schema 255 行、plugin 164 行 — 更舊的世代
```

腳本的結語刻意提醒反方向：**一個因上游採納而變得多餘的例外，讀起來仍然像現行決策**。那正是 jg-jiahd 那三個星期發生的事。

### Spegel：結論反轉，因為前提被別的工作改掉了

1.3 原本的框架是「若效益不明顯，從 jg-base 移除比 gating 簡單」。

效益實測確實不明顯——jg-jiahd 3 節點上 `spegel_mirror_requests_total` 在約 3 小時 90 次請求的窗口內 `hit=4 / miss=86`，**命中率 4.4%**。原因合理：家用叢集的 workload 多是 `replicas: 1`，只有 DaemonSet 會在多節點共用 image，而那些在建叢集時就拉好了。

但**「移除比 gating 簡單」這個前提在 ② 完成後就不成立了**：gating 現在是免費的（`is_single_node` → 生成 suspend patch），而移除是對所有叢集的變更。爆炸半徑也比原本記的小——② 的 1.0 實測顯示 containerd 2.2.6 在 spegel 失敗時會於 200ms 後回退上游，image 仍拉得動；jcom 那次全叢集拉不動是舊的 2.1.6。

所以結論是**不移除**。這個 spike 的價值不在於它的原始問題，而在於它讓兩個假設同時被檢查：效益（低）與替代方案的成本（已歸零）。**只檢查其中一個都會得到錯的答案。**


### 副本驗證抓到三個東西，其中一個是我自己當天造的

6.5 要求「在副本上完整同步並比對渲染輸出，逐項解釋差異」。做完之後漂移從 13 個檔案降到 1 個，而比對抓到三件事——**沒有一件會在套用當下報錯**：

1. **`LB_POOL_BLOCKS` 漏了 `10.9.8.8`**（`omni/omni` 的 udp-gateway）。narrow pool 推導自 cluster.yaml 宣告的位址，而 jcom 從未宣告過這個——它在 jg-base 裡是寫死的，直到 6.1 才變成變數。依 D26，既有配發不會被收回，所以套用後一切正常，直到那個 Service 下次重建。
2. **claude-code `replicas: 1 → 0`**，會關掉 jcom 的 `im`。
3. **我當天加的 `claude_code_always_on` 表達不出 jcom 的需求**。它的舊模板寫的是 `1 if instance == "im" else 0`——`im` 常駐供支援用、`cc` 按需 scale，活叢集確認 `im=1 / cc=0`。一個全域布林會不是關掉 `im` 就是開起 `cc`。已改為 instance 名稱清單。

第三項值得單獨記：那個欄位是我在**同一個工作階段**為了解決 jgt-omni 的相同問題而加的，加的時候只看到一個叢集的形狀。**「把漂移收成設定」這個動作本身也會漏掉需求**——而發現它的方式是去讀第二個叢集的漂移在說什麼。jcom 手改模板的那一行，正是需求規格。

### 指紋比對比 diff 有用

`ks.yaml` 的 diff 難讀：手寫的長註解變成一行生成註解、patch 順序改變、三個新的 suspend 混在中間。看起來像大改。

改用「按 target 名稱分組 + patch 內容 sha1」比對後，一眼就清楚：

```
BEFORE                          AFTER
<generic>  a847ff96f0           <generic>  a847ff96f0
cilium     c73f48c3fe           cilium     c73f48c3fe   ← 手寫 → 宣告，內容不變
spegel     865a2051b0           spegel     865a2051b0
                                lan-address-probe / longhorn  ← 新增，預期
```

**Cilium 那個例外從手寫 JSON6902 變成 `cilium_native_routing: true`，產出位元組相同。** 這是「行為不變」最強的證據形式——比讀 diff 判斷「看起來一樣」可靠得多。

### `talenv.yaml.j2` 不是模板內容，是叢集狀態

同步時唯一刻意保留的檔案。jcom 是 Talos v1.12.4 / K8s v1.35.2，模板是 v1.13.8 / v1.35.1——盲目覆蓋會升級 Talos 並**降級 K8s**。

這揭露漂移偵測的一個分類缺口：它把所有 `templates/` 下的檔案一視同仁，但版本宣告檔承載的是每個叢集自己的升級節奏。`check-template-drift.py` 目前會把它報成 DRIFTED，那是誤報——應該有一類「預期分歧」的標記。

## Goals / Non-Goals

**Goals:**
- jcom 回到「能把模板更新當例行操作」的狀態。
- 每一項差異都有歸屬與理由，不留「不知道為什麼在這裡」。
- 讓 per-cluster 例外有正式表達方式，止住製造分岔的機制。
- 單節點安全性由設定決定，不靠事後 patch。

**Non-Goals:**
- 不重新設計 Flux 的整體結構。
- 不處理 jg-jiahd 以外其他 user repo（同樣機制適用，但逐一遷移不在此範圍）。
- 不決定 Spegel 在多節點叢集上該不該留——那是獨立問題，只確保單節點不會被它害死。
- 不代替 `deployment-profiles` 定義 profile 軸；本 change 提供它需要的 gating 機制。

## Decisions

### D1. 根因是「產物被手改」，不是「有人偷懶」

`kubernetes/flux/cluster/ks.yaml` 是渲染產物，但每個叢集的例外都被手寫進它的 `.j2`。jcom 的 Spegel suspend、jg-jiahd 的 QUIC workaround，兩個都在同一個檔案。

問題在於：**手改過的模板檔，和「還沒同步的舊版本」在檔案層級長得一模一樣**。沒有任何訊號能區分「這是本叢集刻意的例外」與「這只是落後了」。所以每加一個 workaround，該叢集就更難吃更新，而下一個 workaround 又只能繼續手改——分岔是這個機制的必然產物。

因此本 change 的重點不是「把 jcom 合回來」，而是**拆掉製造分岔的機制**。只做合併不改機制，一年後會回到同一個地方。

### D2. 分類只有三種，且不允許「先放著」

每一項差異必須是「收進模板」「從叢集移除」「宣告為 per-cluster 例外」其中之一。刻意不提供第四種「暫時保留」——那正是現況，而現況的成因就是沒有人被迫做決定。

「不知道為什麼在這裡」的項目本身就是發現，必須查清楚再分類。

### D3. 收回模板的判準是「其他叢集也會受益」，不是「誰比較新」

`encrypt-secrets` 含 `TALOS_DIR`：任何走手動路徑的叢集都需要 → 收回。
`bootstrap-apps.sh` 的 namespace 掃描：jcom 的是舊版且在現行目錄結構下會取到錯的值，模板的固定清單是刻意修正 → jcom 改用模板版。

規格明訂採納時要記錄「哪一邊比較好」，避免同一個判斷被反覆重打。

### D4. Spegel 是單節點安全性的第一個案例，不是特例

jcom 的 patch 註解記錄了完整事故：Spegel 在單節點起不來，臨死前寫 `hosts.toml` 把**所有** registry 導向死掉的 `:29999/:30021`，全叢集未快取的 image 都拉不動。

`jg-base/kubernetes/apps/base/kube-system/kustomization.yaml:12` 至今仍**無條件**部署它。jg-jiahd 有 3 節點所以沒事，jcom 有 1 節點所以被害。而 `deployment-profiles` 的 `appliance` **就是單節點**——每一台都會重現。

所以這不能繼續用 per-cluster patch 解。規格因此要求兩件事：一是這類元件由設定 gating；二是**失敗必須被隔離**——一個元件起不來就讓全叢集拉不到 image，這個爆炸半徑本身才是主要問題，gating 只是止血。

*Alternative considered*：直接從 jg-base 移除 Spegel。列為 spike——若多節點上的實際效益不明顯，移除比 gating 簡單得多。

### D5. 完成的定義是「同步過一次」，不是「看起來對齊了」

規格把驗收設在實際跑一次模板同步並比對渲染結果（加密檔需解密後比對）。理由與 `revive-talos-path` 5.7 相同：那次也是先以為會乾淨，實際跑才發現一個 `cp` 打錯把根 Taskfile 蓋掉、以及檢查腳本自己誤判。宣稱不算數。

### D6. 遷移順序：先建機制，再遷例外，最後同步

若先同步再處理例外，jcom 的 Spegel suspend 會在同步過程中消失，而單節點 gating 還沒進去——那台叢集會在中間狀態下失去 image 拉取能力。所以順序不能顛倒。

## Risks / Trade-offs

- **jcom 是產線叢集** → 全程先在副本驗證；`revive-talos-path` 5.7 已經證明副本驗證可行且能抓到真問題。
- **拆掉手改機制會動到 jg-jiahd 的 QUIC workaround** → 該 workaround 必須先在新機制上重現並驗證，才能拆掉舊的；不可同時進行。
- **單節點 gating 需要渲染期知道節點數** → 手動路徑可從 `nodes` 得知，Omni 路徑不行（`nodes: []`）。這是實作上的真實困難，可能要靠 profile 或明確欄位表達，與 `deployment-profiles` 相依。
- **「收進模板」會讓模板變複雜** → 判準限定在「其他叢集也會受益」，只服務單一叢集的留在 per-cluster 例外。
- **分岔可能不只 jcom** → 其他 user repo 未盤點。本 change 建立的機制與清冊格式應可重用，但逐一遷移不在範圍內。

## Migration Plan

1. **盤點**：把 jcom 的 54 行 `ks.yaml.j2` 差異逐項分類（spike：多少是真例外、多少是舊版殘留）。
2. **建機制**：per-cluster 例外的表達方式先做出來並在副本驗證。
3. **單節點 gating**：先讓 Spegel 可由設定停用（jg-base + 模板），這是 jcom 遷移的前提。
4. **遷移例外**：jcom 的 Spegel suspend、jg-jiahd 的 QUIC workaround 改用新機制，各自驗證行為不變。
5. **同步 jcom**：在副本上套用模板，比對渲染輸出，逐項解釋差異，通過後才對真 repo 執行。
6. **回歸**：jg-jiahd 重跑 5.7 式的比對，確認機制變更沒有影響它。
7. **Rollback**：每一步都在副本先行；真 repo 的變更以 git 保留，可還原。

## Open Questions

- jcom `ks.yaml.j2` 那 54 行，實際上有多少是 per-cluster 例外、多少是舊版殘留？決定遷移工作量。
- `cilium_bgp_enabled` / `cilium_loadbalancer_mode` 還有消費端嗎，還是已是死碼？（`spegel_enabled` 確定仍在用。）
- Spegel 在多節點叢集上的實際效益如何？若不明顯，從 jg-base 移除比 gating 簡單。
- per-cluster 例外要用什麼形式：Flux post-build substitution、獨立 overlay 目錄、還是 `cluster.yaml` 驅動的條件渲染？三者對「能不能偵測未宣告漂移」的支援程度不同。
- Omni 路徑下渲染期如何得知節點數？`nodes` 恆為空，可能要靠 profile 或新欄位。
- 其他 user repo（jgu4 等）的分岔程度未知，是否要一併盤點？
