## 1. Spikes（先做，結果會改變後面的設計）

- [x] 1.1 上游 `.mise.toml` 的 talhelper `3.1.5` 與 talos `1.12.4` 與本 repo **完全相同**，無相容性缺口（唯 kubectl 1.35.1 vs 1.35.2，無影響）
- [x] 1.2 `talenv.yaml.j2` 硬編 `talosVersion: v1.12.4` / `kubernetesVersion: v1.35.1` 並帶 renovate 註解。**不與 `.mise.toml` 對齊**——後者 pin 的是 CLI（talosctl / kubectl），前者是叢集元件（installer image / kubelet），是不同東西。本 repo 無 `.renovaterc.json5`，故需手動 bump
- [x] 1.3 實測確認：手動 Talos = `10.43.0.0/16`（jcom）、Omni = `10.96.0.0/12`（jg-jiahd），兩者確實不同；並查出 `cluster_svc_cidr` 無消費端、真正生效的是硬編兩處的 `coredns_cluster_ip`。結論見 `design.md` D3
- [x] 1.4 決議：新增必填欄位 `provisioning_path: "omni" | "talos"`（無預設）。推導方案已證實不可行——`nodes.yaml` 對每個 repo 都會自動生成。結論見 `design.md`

## 2. 修既有缺陷（與移植無關，可獨立驗證，先做）

- [x] 2.1 修 `.taskfiles/template/Taskfile.yaml` 的懸空變數 `TEMPLATE_NODE_CONFIG_FILE`（依上游補回 vars 定義）
- [x] 2.2 移除上游繼承而來、在此 repo 不適用的 `tidy` 任務（原「驗證可執行」改為移除：per-user repo 永不「畢業」，跑 tidy 會廢掉 `task configure`）；連帶移除僅供其使用的 `PRIVATE_DIR`，並在原處留下說明註解
- [x] 2.3 `cluster_svc_cidr` 改為必填無預設（CUE 移除 `*"10.43.0.0/16"`、`plugin.py` 移除 setdefault）；`coredns_cluster_ip` 改由 `nthhost(cluster_svc_cidr, 10)` 推導，取代兩處硬編的 `10.96.0.10`
- [x] 2.4 `cluster.sample.yaml` 更新：`cluster_svc_cidr` 標為必填並列出兩條路徑的實測值（Omni `/12`、手動 `/16`，原文誤植 Omni 為 `/16`）；`node_default_gateway` 註明預設為 node_cidr 的 .1；coredns 改註明為推導值
- [x] 2.5 掃過所有 Taskfile 與模板：無其他懸空變數（12 個 vars 皆有定義）；預設值分歧僅 `cluster_svc_cidr` 一項（`repository_branch` / `cilium_loadbalancer_mode` 各只有單邊定義，符合 spec）
- [x] 2.6 移除無人引用的 `.taskfiles/template/resources/cluster.schema.json`（零引用；缺 26 個 `.cue` 欄位、留 1 個已移除欄位；`cue vet` 才是實際驗證者）

## 3. 移植檔案（先不接線）

- [x] 3.1 移植 `templates/config/talos/talconfig.yaml.j2`
- [x] 3.2 移植 `templates/config/talos/talenv.yaml.j2`
- [x] 3.3 移植 `templates/config/talos/patches/global/`（machine-network、machine-time、machine-files、machine-kubelet、machine-sysctls）
- [x] 3.4 移植 `templates/config/talos/patches/controller/cluster.yaml.j2`
- [x] 3.5 移植 `templates/config/talos/patches/README.md.j2`
- [x] 3.6 移植 `nodes.sample.yaml`
- [x] 3.7 移植 `.taskfiles/template/resources/nodes.schema.cue`
- [x] 3.8 移植 `.taskfiles/talos/Taskfile.yaml`（generate-config / apply-node / upgrade-node / upgrade-k8s / reset）
- [x] 3.9 在 `.taskfiles/bootstrap/Taskfile.yaml` 補上 `talos` 任務
- [x] 3.10 確認移植後的模板仍設 `cniConfig: none`、`coreDNS.disabled`、`proxy.disabled`（與 jg-base 相容）

## 4. 接線

- [x] 4.1 `makejinja.toml` 的 `data` 加入 `./nodes.yaml`
- [x] 4.2 根 `Taskfile.yaml` 加入 `TALOS_DIR` 與 `TALOSCONFIG` 變數
- [x] 4.3 根 `Taskfile.yaml` 加入 `includes: talos:`
- [x] 4.4 新增 `generate-node-config` internal task，由 `task init` **與** `task configure` 共用；有 sample 就複製、無 sample（舊 repo）則產生 `nodes: []`，兩種情況皆已實測
- [x] 4.5 把 `nodes.schema.cue` 納入 `task configure` 的驗證階段，且在渲染之前執行
- [x] 4.6 驗證 `.gitignore` 已涵蓋 `nodes.yaml` 與 `/talos/`（現況已有，僅確認）

## 5. 路徑共存

- [x] 5.1 CUE 加入 `provisioning_path` 與跨檔約束（`omni ⇒ nodes: []`、`talos ⇒ list.MinItems(1)`）；`validate-schemas` 改為 `yq` 合併兩檔後單次 `cue vet`（多檔是各自驗證，無法表達跨檔約束）
- [x] 5.2 `bootstrap-apps.sh` 的 `TALOSCONFIG` 檢查改為僅 `talos` 路徑執行
- [x] 5.3 `talhelper` 檢查改為僅 `talos` 路徑執行；路徑讀自 `cluster.yaml`，未宣告時 error 而非猜預設
- [x] 5.4 實測（乾淨環境 + bash 5.3）：omni 路徑在無 talhelper、無 TALOSCONFIG 下通過前置檢查
- [x] 5.5 實測：talos 路徑缺 TALOSCONFIG 或缺 talhelper 皆 fail fast；未宣告 provisioning_path 時指名該欄位並列出可接受值
- [x] 5.6 由 ② 承接：② 只需加 `appliance ⇒ provisioning_path: "omni"`，本 change 的 `omni ⇒ nodes: []` 會讓 appliance 併存手動節點宣告自動被拒，不需另寫規則
- [x] 5.7 **jg-jiahd（Omni）驗證乾淨**：在副本上同步 ① 的改動（排除其 QUIC workaround 的 `ks.yaml.j2`）+ 加 `provisioning_path: "omni"`，`task configure` 通過，`ks.yaml` 與解密後 `cluster-secrets` **完全相同**、檔案數不變。副作用僅多渲染 gitignored 的 `talos/` 與 `nodes.yaml: []`。已於最終狀態（含 1.13.8、validate-manifests、encrypt-secrets 修正）重跑一次，結果不變
- [ ] 5.8 jcom 無法以同法驗證——它是保留完整手動 Talos 工具鏈的**較舊血脈**，非「模板+客製化」。直接同步會壞：其模板用到我略過的 `spegel_enabled`（`01-apps.yaml.j2`、`ks.yaml.j2`），且我的 `makejinja.toml` 宣告的 `trello-notifier.yaml` 在 jcom 不存在會讓 makejinja 中止。需獨立的合併工作，不屬 ①

## 5c. 比對 jcom 後補上的缺口

- [x] 5c.1 `encrypt-secrets` 加入 `TALOS_DIR`（移植時漏掉；jcom 有。否則手動路徑的 talos 側 secret 不會被涵蓋）（已於最終狀態回歸驗證：`talsecret.sops.yaml` encrypted=true）
- [x] 5c.3 採納 jcom 的 `cloudflare-tunnel.json` 前置檢查——2026-08-11 走真實 template 流程時第二次踩到：缺檔時 `task configure` 渲染到一半才以 Python traceback 中止，留下半套 `kubernetes/`。加上後改為渲染前擋下、訊息含建立指令、`kubernetes/` 完全不被寫入
- [x] 5c.2 `kubeconform.sh` 接上：新增 `template:validate-manifests`（alias `lint`）並納入 `task configure`（渲染後、加密前）。實測 2.1s，驗過 3 個 Flux Kustomization + GitRepository + HelmRelease；`-ignore-missing-schemas` 讓離線時降級而非失敗。這是唯一檢查**渲染輸出**的環節——`cue vet` 只看輸入

## 6. 完整性檢查

> 已接進 `task configure`（`check-integrity`），另有 `task template:check` 可單獨執行。

- [x] 6.1 實作 `scripts/check-template-integrity.py` 的懸空變數檢查（indent-aware 解析所有 Taskfile 的 vars/env，含 `requires: vars:` 的 list 形式）
- [x] 6.2 實作分歧預設檢查（AST 解析 `plugin.py` 的 setdefault vs CUE 的 `*"..."`）；另加第三項檢查：`cluster.sample.yaml` 註解記載的預設須等於實際生效值；實跑 jg-jiahd 時抓到自身誤判並修正：sample 的 `# field: ""` 是「未設值」不是「預設為空」
- [x] 6.3 注入懸空變數 → `FAIL dangling task variables`，指名檔案:行號與變數名；exit 1
- [x] 6.4 注入分歧預設 → `FAIL divergent defaults`，指名欄位與兩邊的值；文件不符亦能命中；exit 1

## 7. 文件與交接

- [x] 7.1 `README.md:205` 的 `just bootstrap talos` 改為 `task bootstrap:talos`
- [x] 7.2 確認 `README.md:164` 的 `nodes.yaml` 指示現在有對應的 sample 與 schema
- [x] 7.3 通知 `zero-it-onboarding` task 2.2 阻塞已解除
- [x] 7.4 在 `CLAUDE.md` 補上手動 Talos 路徑的存在與適用情境

## 7b. 版本升級（驗收準備時決定：升到 Talos 1.13.2）

- [x] 7b.1 `talenv.yaml.j2` 的 `talosVersion` v1.12.4 → v1.13.8
- [x] 7b.2 `.mise.toml` 的 `aqua:siderolabs/talos` 1.12.4 → 1.13.8
- [x] 7b.3 `.mise.toml` 的 `aqua:budimanjojo/talhelper` 3.1.5 → 3.1.16（**必須同動**：3.1.5 會以 "not a supported Talos version" 拒絕 v1.13.2/v1.13.8）
- [x] 7b.4 `kubernetesVersion` 維持 v1.35.1（Talos 1.13.2 支援 1.31–1.36，且與 kubectl 1.35.2 對齊）
- [x] 7b.5 離線驗證 `talhelper genconfig` 產出正確：CNI none、coreDNS/proxy disabled、svc 10.43.0.0/16、disk `/dev/nvme0n1`、installer image 帶 `:v1.13.8`、MAC 選擇器與 VIP 皆正確（Talos 1.13 的 multi-doc 格式）
- [x] 7b.6 決定升到 **1.13.8**（1.13.x 最新）。原本選 1.13.2 是為對齊機器現況，但既然要重灌該理由已不成立；已驗證 talhelper 3.1.16 接受 v1.13.8，installer image 正確帶 `:v1.13.8`

## 8. 驗收

> 8.2 已於 2026-08-10 以真實 public repo 補完（首次用假 repository_name 只驗到 bootstrap 層）。

> Phase 0–2 已於 2026-08-09 完成（測試 repo `~/coding/jgt-talos-accept`，機器
> `e755a600-e306-1208-904b-6e3ed1880a00` / 10.9.1.238，硬體資訊取自 Omni MachineStatus）。
> 8.1–8.4 待機器改以純 Talos 映像開機、於 LAN 上開出 apid 後執行。

- [x] 8.1 實機 bootstrap 成功（jgt-cp-1 / 10.9.1.238）：`task bootstrap:talos` 完成 gensecret → genconfig → apply → etcd bootstrap → kubeconfig，Node 於約 90 秒後註冊
- [x] 8.2 **完整驗證**（2026-08-10，用真實 public repo `ferry133/jgt-talos-accept` 重跑）：`bootstrap:apps` 成功，Flux 同步 jg-base，`cilium` 與 `coredns` 的 HelmRelease 皆 True 且由 Flux(Helm) 管理，`kube-proxy` / `flannel` 仍為 0。手動路徑產出的叢集與 Omni 路徑一致，Flux 層亦確認。預期失敗者：spegel（單節點）、cloudflare-tunnel（假 token）、claudecode/im（無 secret/NAS）
- [x] 8.3 `apply-node` ✓、`upgrade-node` ✓（完整重開機序列後 uncordon）、`upgrade-k8s` ✓（**但需節點 Ready，見下方順序約束**）
- [x] 8.4 `reset` 未帶 `--yes` 時拒絕執行（確認機制有效）；帶 `--yes` 後節點回到 maintenance mode（apid 回應 v1.13.8），叢集消失
- [x] 8.7 實機順序約束：`talos:upgrade-k8s` 會等節點 Ready，而沒有 CNI 的叢集永遠不會 Ready——k8s 升級必須排在 `bootstrap:apps` 之後。首次嘗試即以 `node is not ready / timeout` 失敗，裝好 Cilium 後重試成功
- [x] 8.8 跨版本安裝驗證：開機 ISO 為 v1.13.2，安裝進磁碟的是 config 指定的 v1.13.8（`OS-IMAGE: Talos (v1.13.8)`），maintenance mode 版本不需與目標版本一致
- [x] 8.9 `coredns_cluster_ip` 推導鏈端到端驗證：`cluster_svc_cidr: 10.43.0.0/16` → `nthhost(·,10)` → 實際 Service `kube-dns=10.43.0.10`；apiserver 的 `--service-cluster-ip-range` 亦為 `10.43.0.0/16`
- [x] 8.5 節點 schema 負面測試全數通過：缺 name、缺 schematic_id、重複 name/address/mac_addr、保留字 `global`、格式錯誤的 mac_addr 與 schematic_id 皆被拒絕並指名欄位
- [x] 8.6 所有 spike 結論已回寫 `proposal.md` / `design.md` / spec；proposal 的「待驗證」清單已改為結論並全數結案
