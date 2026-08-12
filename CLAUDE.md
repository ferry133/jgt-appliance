# CLAUDE.md — jg-cluster-template / per-user cluster repo

## 三 Repo 架構

每個 extra app 橫跨三個 repo，**缺一不可**：

| Repo | 職責 |
|------|------|
| `ferry133/jg-base` | App 的 K8s manifests（ks.yaml + app/ 資料夾） |
| `ferry133/jg-cluster-template`（此 repo） | CUE schema、cluster-secrets 模板、cluster.sample.yaml 文件 |
| 各 user repo（此 repo / jgu4 等） | cluster.yaml 填值 → task configure → push |

## Base App vs Extra App

`kubernetes/apps/base/`（jg-base）內的 app 每個叢集都會裝，**不列在 `extras:`**。
目前 base 含 cert-manager、flux-system、kube-system、network、storage、
**claudecode**、**monitoring**。

`claudecode/claude-code` 自 2026-08-07 起改為 base app：每個叢集預設起一個名為 `im`
的 Claude Code web terminal（`im.<cloudflare_domain>`），讓 ferry133 永遠有一條不依賴
Omni/SideroLink 的遠端支援入口。參考部署是 jg-jiahd 的 `cc.jiahd.cc`——它在
`cluster.yaml` 明寫 `claude_instances: ["cc"]`，不吃預設值。

- 共用資源（namespace、cluster-admin SA、OCIRepository、secrets）在 jg-base
  `kubernetes/apps/base/claudecode/`。
- **每個 instance 的 HelmRelease 仍由 user repo 渲染**（`claude_instances`，預設
  `["im"]`）：instance 名稱與 `oauth2-proxy` / `talos-mcp` sidecar 的有無屬於
  template-time 結構，無法用 Flux `${VAR}` 表達。
- 連帶影響：`nas_server` / `nas_path` / `nas_coding_path` 三個欄位在 CUE schema
  已改為**必填**。
- `claudecode/postgres`（MCP memory server 用的專屬 DB）仍是 opt-in extra。
- **既有叢集要遷移**（Flux Kustomization 改名，直接 push 有 prune 掉 PVC 的時序風險）：
  步驟見 `jg-base/README.md` 的「Migration: claude-code + daily-check extras → base」。
  jg-jiahd 與 jcom 的 pre-push annotation 已於 2026-08-08 套用。
  `cluster.yaml` 的 `extras:` 若還留著 `claudecode/claude-code`，renderer 會自動略過。

`monitoring/daily-check` 同日一併改為 base app：每叢集自己跑每日健檢 CronJob（08:00
Asia/Taipei，Gmail SMTP + healthchecks.io dead-man switch）。`daily_check_*` 欄位維持
optional——沒填的叢集 CronJob 會印一行 "not configured" 然後 exit 0，不會每天留下失敗
Job，但也等於沒有健檢，實務上每個叢集都該填。遷移注意事項（`monitoring` namespace 從
`app/` 上移，舊 Kustomization 的 inventory 仍含它）同樣見 `jg-base/README.md`。

## ⚠️ 新增或修改 Extra App 的完整 Checklist

不論從哪個 repo 起頭，都必須同步完成以下所有步驟：

### Step 1 — `jg-base`：新增 App manifests
- [ ] `kubernetes/apps/extras/<ns>/<app>/kustomization.yaml`（resources: [./ks.yaml]）
- [ ] `kubernetes/apps/extras/<ns>/<app>/ks.yaml`（Flux Kustomization，sourceRef: jg-base）
- [ ] `kubernetes/apps/extras/<ns>/<app>/app/`：Deployment、Service、HTTPRoute、PVC、Secret 等
- [ ] Secret 值用 `${VAR_NAME}` 佔位符（由 cluster-secrets postBuild substituteFrom 注入）

### Step 2 — `jg-cluster-template`：同步更新 Schema 與模板
- [ ] `.taskfiles/template/resources/cluster.schema.cue`：加入新 optional 欄位（`field?: string`）
- [ ] `templates/config/kubernetes/components/sops/cluster-secrets.sops.yaml.j2`：加入 `VAR_NAME: "#{ var_name | default('') }#"` 行
- [ ] `cluster.sample.yaml`：在 extras 清單加入說明，並加入 config 欄位範例（加 `#` 注解）

### Step 3 — User Repo（此 repo）：啟用 App
- [ ] `cluster.yaml`：在 `extras` 加入 `<ns>/<app>`，填入對應 config 欄位的實際值
- [ ] `task configure --yes`：重新生成 `kubernetes/flux/cluster/ks.yaml` 和 `cluster-secrets.sops.yaml`
- [ ] commit & push（三個 repo 依序：jg-base → jg-cluster-template → user repo）

## 文件結構（依讀者拆分）

| 檔案 | 讀者 | 內容 |
|------|------|------|
| `README.md` | 任何人 | 入口，只做導向，**不含任何部署步驟** |
| `README-zero-IT.md` | 收到硬體的客戶 | 繁中，三個物理動作，無指令無術語 |
| `docs/deploy/manual.md` | 進階使用者 | 完整手動部署，兩條供裝路徑 |
| `CLAUDE.md`（本檔） | 維護者 | 架構、慣例、程式碼看不出來的規則 |

一份程序只寫在一個地方。operator runbook 由 `factory-agent` change 承擔，
其他文件**只連結不複述**——分岔的文件必然有一份是錯的，而錯的那份會被照著執行。

`README-zero-IT.md` 需隨箱出貨紙本：客戶讀它的時候網路還沒通，以 URL 為唯一入口
的設計在那一刻就是失效的。紙本與此檔須同源產生，不可手抄。

## 兩條供裝路徑

| 路徑 | 適用 | 節點資訊來源 |
|------|------|--------------|
| **(B) Omni** | 預設。機器經 SideroLink 自行回連，遠端可見 | Omni |
| **(A) 手動 Talos** | 進階使用者、無 Omni 時的逃生梯 | `nodes.yaml`（每節點需 name / address / controller / disk / mac_addr / schematic_id） |

手動路徑的檔案（2026-08-09 自上游 `cluster-template` 移植回來）：

- `templates/config/talos/` — talconfig、talenv、global 與 controller patches
- `nodes.sample.yaml`、`.taskfiles/template/resources/nodes.schema.cue`
- `task bootstrap:talos` 一次完成 secret → genconfig → apply → bootstrap → kubeconfig
- 日常操作：`task talos:apply-node IP=<ip>` / `upgrade-node IP=<ip>` / `upgrade-k8s` / `reset`

兩條路徑產出的叢集形狀相同：talconfig 設 `cniConfig: none`，controller patch 關掉
coreDNS 與 kube-proxy——與 Omni 使用者要手貼的 MachineConfigPatch 一致，CNI / DNS
一律由 jg-base 安裝。

`nodes.yaml` 對 Omni 叢集是 `nodes: []`；`task configure` 會自動產生它（makejinja
宣告的 data 檔缺一個就整個中止），所以既有 Omni repo 不需要手動補檔。

> ⚠️ 上游的 `task template:tidy`（「從 template 畢業」）**已移除**。per-user repo 每次
> 改 `cluster.yaml` 都要重跑 `task configure`，跑 tidy 會搬走 `templates/` 與
> `makejinja.toml`，永久廢掉這個流程。不要從上游重新引入。

## 命名慣例

- Secret 環境變數：以 app 名稱為 prefix，全大寫，e.g. `SYNOPHOTO_AUTH0_DOMAIN`
- CUE schema 欄位：小寫 snake_case，e.g. `synophoto_auth0_domain?: string`
- `cluster.yaml` 欄位：同 CUE schema 欄位名稱

## kubectl Access（產生此 repo 後需填入）

```sh
kubectl --kubeconfig ~/coding/<repo>/kubeconfig-sa <command>
```

詳細設定方式見下方 Omni SA 建立流程。

---

## Troubleshooting

### `cloudflare-tunnel` CrashLoopBackOff — QUIC blocked

**症狀**：cloudflared pod 持續 CrashLoopBackOff，logs 顯示重複 `Failed to dial a quic connection: timeout: handshake did not complete in time`（連到 198.41.x.x），`/ready` 回 503。Cloudflare dashboard 顯示 tunnel `Down` / `Active replicas: 0`。

**根因**：node 出口封鎖 UDP 7844（QUIC），但 TCP 443 正常。不是 token 過期、不是 Cloudflare 端問題、token rotate 救不了。

**修復**：在 user repo 的 `templates/config/kubernetes/flux/cluster/ks.yaml.j2` 的 `cluster-apps-base` Kustomization 的 nested patches 內，加一段 patch 強制改 protocol：

```yaml
- patch: |-
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      name: cloudflare-tunnel
    spec:
      values:
        controllers:
          cloudflare-tunnel:
            containers:
              app:
                env:
                  TUNNEL_POST_QUANTUM: false
                  TUNNEL_TRANSPORT_PROTOCOL: http2
  target:
    group: helm.toolkit.fluxcd.io
    kind: HelmRelease
    name: cloudflare-tunnel
```

然後 `task configure --yes` → commit & push。約 1 分鐘後 cloudflared 應 `1/1 Running`。

**為什麼不改 jg-base？** 其他 cluster（jgu2、jcom 等）QUIC 正常，default 保留 QUIC 較好。這是 per-cluster workaround。

**參考**：jg-jiahd commit `ac1c818`（2026-05-13；原 jgu5 repo 已於 2026-05-30 改名）。

---

## Omni Service Account 建立 / 更新流程

適用情境：Omni 升級後 SA key 失效、第一次建立新 user repo。

### Step 1 — 建立或更新 SA（Omni UI）

1. 開啟 `https://omni.janncot.com` → **Settings → Service Accounts**
2. 若舊 SA `claude-code` 存在且失效 → 點 **…** → **Destroy**
3. **Create Service Account**：Name `claude-code`、Role `Admin`、TTL `1 year`
4. 建立後複製完整 SA token（`eyJ...` 格式）

### Step 2 — 更新 ~/.config/omni/env

```sh
cat > ~/.config/omni/env << 'ENVEOF'
# SA: claude-code@serviceaccount.omni.sidero.dev, Admin, renewed <date>
# NOTE: OMNI_ENDPOINT 指向 localhost，需先開 port-forward：
#   KUBECONFIG=~/coding/jcom/kubeconfig kubectl port-forward -n omni svc/omni 18080:8080 &
export OMNI_ENDPOINT=grpc://localhost:18080
export OMNI_SERVICE_ACCOUNT_KEY=<貼上 SA token>
ENVEOF
```

### Step 3 — 開 port-forward 並測試

```sh
KUBECONFIG=~/coding/jcom/kubeconfig kubectl port-forward -n omni svc/omni 18080:8080 &
source ~/.config/omni/env
omnictl get clusters   # 應列出所有 cluster
```

### Step 4 — 為每個 cluster 產生 kubeconfig-sa

```sh
source ~/.config/omni/env
omnictl kubeconfig ~/coding/<repo>/kubeconfig-sa \
  --cluster <cluster-name> \
  --service-account \
  --user ferry133 \
  --ttl 8760h
```

**保留兩個檔案的慣例**：
- `kubeconfig` — 原始 OIDC 版（需瀏覽器登入；mise 預設 `KUBECONFIG` 指這個）
- `kubeconfig-sa` — 內嵌 SA token，非互動可用
- 不要 `cp kubeconfig-sa kubeconfig` 覆蓋。所有自動化（CI、scripts、本機 kubectl）都應**明確帶 `--kubeconfig kubeconfig-sa`** 或 `export KUBECONFIG=<repo>/kubeconfig-sa`。
- 留著 OIDC kubeconfig 可在 SA 過期時用瀏覽器登 Omni 救援。

### Step 5 — 驗證

```sh
cd ~/coding/<repo>
kubectl --kubeconfig kubeconfig-sa get nodes
```

### 注意事項

- `jcom` 使用 Talos client cert kubeconfig，**不需要** kubeconfig-sa
- Omni UI 的 Edit User 對話框只有 Role，沒有 Public Keys 管理（v1.7.x 已移除）
- PGP user key 有 lifetime 限制（Omni 限制從現在起約數小時），不適合長期使用，改用 SA

---

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`ferry133/jg-cluster-template`), operated via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
