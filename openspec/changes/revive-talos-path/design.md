## Context

`README.md` 完整記載了 (A) Talos 手動路徑，但這個 repo 沒有任何 talos 模板。已查證的狀態：

```
jg-cluster-template/templates/config/
  bootstrap/  kubernetes/          ← 沒有 talos/

README.md:164   「填 nodes.yaml」   ← 無 nodes.sample.yaml、無 nodes.schema.cue
README.md:205   just bootstrap talos ← 無 justfile；正確指令是 task bootstrap:talos
Taskfile.yaml                       ← 無 TALOS_DIR、無 TALOSCONFIG 變數、無 talos include
makejinja.toml  data = [cluster.yaml, trello-notifier.yaml]  ← 無 nodes.yaml
```

而且已經在 repo 裡造成兩個實際缺陷：

```
.taskfiles/template/Taskfile.yaml:123  {{.TEMPLATE_NODE_CONFIG_FILE}}
    此變數在本 repo 完全未定義 → task template:tidy 直接失敗

scripts/bootstrap-apps.sh:140-141      check_env ... TALOSCONFIG
                                       check_cli ... talhelper
    Omni 使用者用不到，卻被強制安裝與設定
```

上游 `~/coding/cluster-template` 素材完整：`templates/config/talos/`（talconfig、talenv、global 四個 patch、controller patch、patches README）、`.taskfiles/talos/Taskfile.yaml`（generate-config / apply-node / upgrade-node / upgrade-k8s / reset）、`.taskfiles/bootstrap/Taskfile.yaml` 的 `talos` 任務、`nodes.sample.yaml`、`nodes.schema.cue`。

## Goals / Non-Goals

**Goals:**
- 手動 Talos 路徑可用：文件裡的每一個指令都真的存在。
- 兩條路徑共存，且一條的前置條件不擋另一條。
- 修掉因為半途移除而留下的兩個既有缺陷。
- 解除 ④ task 2.2 的相依。

**Non-Goals:**
- 不改變 Omni 路徑的任何行為。
- 不讓 appliance profile 支援手動 Talos（②已規定僅限 Omni，本 change 遵守）。
- 不重新設計 Talos 設定內容；上游模板已與 `jg-base` 相容，照移即可。
- 不處理 KubeSpan / 跨站點（`docs/kubespan-cross-site-networking.md` 是獨立主題）。

## Decisions

### D1. 這是 port，不是重新設計

上游模板已經是本 repo 的來源，且**已查證與 `jg-base` 相容**：

```
talconfig.yaml.j2               cniConfig: name: none
patches/controller/cluster.yaml.j2:12   coreDNS.disabled: true
patches/controller/cluster.yaml.j2:19   proxy.disabled: true
```

這三項正是 README 要求 Omni 使用者手動貼上的 MachineConfigPatch 內容。也就是兩條路徑產出的叢集形狀本來就一致，不需要為了相容而改寫模板。

同樣查證過：上游 `cluster.schema.cue` 的欄位是本 repo 的**子集**，本 repo 是超集，所以 cluster 層級不缺任何 Talos 路徑要用的欄位。移植只需新增 `nodes.schema.cue`。

*Alternative considered*：重寫一套較簡化的 Talos 模板。捨棄——上游模板已在大量叢集上驗證過，自行簡化只會引入未經驗證的差異。

### D2. 前置條件依路徑條件化，而不是放寬

`bootstrap-apps.sh` 目前無條件要求 `TALOSCONFIG` 與 `talhelper`。兩種修法：

- 放寬成「有就檢查、沒有就跳過」——會讓手動路徑的使用者在真的缺工具時走到很後面才失敗。
- **依路徑判定**——Omni 路徑不檢查，手動路徑照常嚴格檢查。

採後者。規格明訂「路徑由設定決定，不是從現場檔案存在與否推測」，因為推測會在檔案殘留時給出錯誤答案。

### D3. `cluster_svc_cidr` 的預設值矛盾要正面解決

```
cluster.schema.cue:14   cluster_svc_cidr: *"10.43.0.0/16" | ...
plugin.py:130           data.setdefault('cluster_svc_cidr', '10.96.0.0/16')
```

`cue vet` 只驗證、不回寫，makejinja 直接讀 `cluster.yaml`，因此**實際生效的是 10.96**，CUE 的 10.43 是死的且會誤導讀者。而 `cluster.sample.yaml:34-36` 又敘述兩條路徑的正確預設不同。

規格因此要求：一個欄位只能有一個生效預設；若兩條路徑的正確值本來就不同，就**明確按路徑表達**，而不是讓其中一個默默覆蓋另一個。

#### Spike 1.3 實測結論（2026-08-09）

直接讀兩個叢集 kube-apiserver 的 `--service-cluster-ip-range`：

| 叢集 | 供裝路徑 | 實際 service CIDR | coredns clusterIP |
|---|---|---|---|
| jcom | Talos 手動 | `10.43.0.0/16` | `10.43.0.10` |
| jg-jiahd | Omni | `10.96.0.0/12` | `10.96.0.10` |

**兩條路徑的正確值確實不同**，證實預設必須按路徑表達。上游本身是一致的（CUE 與 `plugin.py` 皆為 `10.43.0.0/16`）——本 repo fork 時只改了 `plugin.py` 未改 CUE，才產生分歧。

順帶查出三件更重要的事：

1. **`cluster_svc_cidr` 在本 repo 沒有任何消費端**。它只出現在 `plugin.py:130` 的 setdefault（設了沒人讀）與 schema 的 `!=` 交叉檢查。所以今天的分歧沒有造成實害。
2. **真正生效的是 `coredns_cluster_ip`，而它在兩處各自硬編預設 `10.96.0.10`**（`bootstrap/helmfile.d/templates/values.yaml.gotmpl.j2:10`、`kubernetes/components/sops/cluster-secrets.sops.yaml.j2:16`），餵給 `jg-base` 的 coredns `clusterIP`。今天不出事，是因為 jcom 在 `cluster.yaml:93` 明寫 `coredns_cluster_ip: 10.43.0.10` 覆寫掉。**手動路徑復活後，任何忘記設這個欄位的新叢集會拿到 `10.96.0.10`——落在 `10.43.0.0/16` 之外，coredns Service 建不起來。**
3. 既有的 `nthhost` filter 已足以推導：`nthhost(10.96.0.0/12, 10) = 10.96.0.10`、`nthhost(10.43.0.0/16, 10) = 10.43.0.10`。把 `coredns_cluster_ip` 改為由 `cluster_svc_cidr` 推導（明寫者優先），兩個既有叢集的渲染結果都不變。

另外兩個附帶發現：
- `jg-jiahd/cluster.yaml:21` 寫 `cluster_svc_cidr: "10.96.0.0/16"` 並註記「Don't change — align with Omni default」，但該叢集實際跑的是 `/12`。因為無人消費，此註記至今無害但已失實。
- `.taskfiles/template/resources/cluster.schema.json` **無任何引用**，是與 `.cue` 平行且未同步的重複來源，屬本 change `template-rendering-integrity` 要處理的同一類問題。

#### 決議（2026-08-09）

`cluster_svc_cidr` **改為必填、無預設**，`coredns_cluster_ip` 改由 `nthhost(cluster_svc_cidr, 10)` 推導（明寫者仍優先）。

選這個而非「挑一個路徑的值當預設」，是因為猜錯的後果不對稱：猜錯只會在叢集起來之後、coredns Service 因 clusterIP 落在 service CIDR 外而建不起來時才浮現，遠端很難診斷；而必填讓它在 `cue vet` 當場失敗。同時這個作法**不需要先知道供裝路徑**，所以不被 task 1.4 阻塞。

驗證結果：

| 輸入 | 推導出的 coredns IP | 對應實測 |
|---|---|---|
| `10.96.0.0/12` | `10.96.0.10` | jg-jiahd 實際值 ✓ |
| `10.43.0.0/16` | `10.43.0.10` | jcom 實際值 ✓ |
| `10.96.0.0/16` | `10.96.0.10` | jg-jiahd `cluster.yaml:21` 宣告值，結果相同 ✓ |
| 明寫 `coredns_cluster_ip` | 照明寫值 | 覆寫仍有效 ✓ |

遷移影響（兩者皆**無渲染 diff**，且因 user repo 各有模板副本，不會立即中斷）：
- **jg-jiahd**：已於 `cluster.yaml:21` 宣告，直接通過。
- **jcom**：未宣告（`:36` 註解掉），需補 `cluster_svc_cidr: "10.43.0.0/16"`；它已明寫 `coredns_cluster_ip: 10.43.0.10`，補上後輸出不變。

### D4. 缺陷檢查要可執行，不能只靠讀

懸空變數與預設值矛盾這兩類缺陷的共同點是：**讀檔案看不出來，跑到才知道**。`TEMPLATE_NODE_CONFIG_FILE` 已經在 repo 裡躺了一段時間沒被發現，就是證據。

所以規格要求這些性質可被檢查執行驗證，而不只是這次修好。否則下次再從 repo 拿掉某條路徑時，會重演一模一樣的事。

### D5. 節點值先驗證再渲染

節點的 MAC、磁碟、schematic ID 填錯，症狀是「機器不會開」——遠端看不出原因，排查很慢。上游 `nodes.schema.cue` 已有格式檢查與跨節點唯一性檢查（name / address / mac_addr 不得重複），照移並保持在渲染之前執行。

### D6. `cluster_api_addr` 在兩條路徑的角色不同，不是衝突

手動路徑的 talconfig 用它當 endpoint 與 VIP，所以**必填**。②決定 appliance 不需要它，因為 Omni 自己 proxy。兩者並行不悖——這是同一個欄位在不同路徑下的不同必要性，正好是 D3 要求「按路徑表達」的另一個實例。

### D7. Talos 與 talhelper 的版本是綁在一起的

2026-08-09 驗收準備時實測發現：**talhelper 會用內嵌的清單驗證 `talosVersion`**，pin 的 3.1.5 直接拒絕 v1.13.2：

```
field: "talosVersion"
  * "v1.13.2" is not a supported Talos version
```

所以「升 Talos」永遠不是單一 pin 的改動，至少是 `talenv.yaml.j2` + `.mise.toml` 的 talos + talhelper 三處同動。已驗證的組合：**Talos v1.13.2 + talhelper 3.1.16**（3.1.5 不行）。

連帶發現：**Talos 1.13 改用 multi-document 設定格式**。網路設定從 `machine.network.interfaces` 移到獨立文件：

```
kind: LinkAliasConfig    selector: glob("<node-mac>", mac(link.hardware_addr))
kind: Layer2VIPConfig    name: 10.9.1.239   link: ethSel0
kind: LinkConfig         addresses: [10.9.1.238/24]   routes: [gateway 10.9.1.1]
kind: HostnameConfig     hostname: jgt-cp-1
```

`talconfig.yaml.j2` **不需要修改**——格式轉換由 talhelper 負責，模板的輸入語法不變。這也說明為什麼移植上游模板時不必顧慮 Talos 版本差異，只要 talhelper 跟得上。

`kubernetesVersion` 維持 `v1.35.1`：Talos 1.13.2 的預設是 1.36.0，但支援回推 6 個版本（1.31–1.36），且 1.35.1 與 `.mise.toml` 的 kubectl 1.35.2 對齊。

### D8. 實機驗收結論（2026-08-10，jgt-cp-1 / 10.9.1.238）

手動路徑在真實硬體上完整跑通：bootstrap → 叢集形狀 → 節點生命週期 → reset。三個值得記住的發現：

**`upgrade-k8s` 有順序約束。** `talosctl upgrade-k8s` 會等節點 Ready 才繼續，而沒有 CNI 的叢集永遠不會 Ready。首次嘗試以 `node is not ready / timeout` 失敗，裝好 Cilium 後重試成功。所以 **k8s 升級必須排在 `bootstrap:apps` 之後**——這不是 task 的缺陷，但值得寫進文件，否則新手會以為升級壞了。

**跨版本安裝可行。** 開機 ISO 是 v1.13.2，安裝進磁碟的是 config 指定的 v1.13.8（`OS-IMAGE: Talos (v1.13.8)`）。maintenance mode 的版本不必與目標版本一致，所以升 pin 之後不需要重燒 USB。

**PATH 上的舊 talhelper 會蓋掉 pin 的版本。** 首次 `task bootstrap:talos` 以 `"v1.13.8" is not a supported Talos version` 失敗——`/usr/local/bin/talhelper` 是 mise 管不到的 3.1.5。改用 `mise exec -- task ...` 才解析到 3.1.16。① 把 talhelper 的最低版本推到 3.1.16，這個殘留檔案因此從無害變成會擋人，值得清掉。

驗收數據：

```
Node        jgt-cp-1  Ready  control-plane  v1.35.1  10.9.1.238  Talos (v1.13.8)
kube-proxy  0 pods        flannel  0 pods          ← 內建元件確實停用
cilium      2 pods        coredns  2 pods          ← 由 bootstrap 提供
service-cluster-ip-range = 10.43.0.0/16
kube-dns clusterIP       = 10.43.0.10              ← 推導鏈端到端驗證
reset 未帶 --yes → 拒絕；帶 --yes → 回 maintenance mode
```

倒數第二行是 ① 修掉的 `cluster_svc_cidr` 分歧預設的最終證明：宣告值 → `nthhost(·,10)` → cluster-secrets → bootstrap helmfile → 實際運行的 Service，整條鏈在真實叢集上一致。

**驗證範圍的限制（重要）**：上表的 Cilium 與 CoreDNS 來自 **bootstrap helmfile**，不是 jg-base 經由 Flux。`task bootstrap:apps` 實際上是**失敗的**——前四個 release（cilium、coredns、cert-manager、flux-operator）安裝成功，第五個 `flux-instance` 因為 FluxInstance 指向丟棄測試的假 `repository_name`（`ferry133/jgt-talos-accept`，不存在）而永遠 `InProgress`，helm `--wait` 逾時後整個 task 以 exit 1 結束。

所以「手動路徑產出的叢集與 Omni 路徑一致」只在 **bootstrap 層**成立；**Flux / jg-base 層未驗證**，需要真實 repo 與 Cloudflare 憑證才能補完。順帶一提，這也表示 jg-base 的 Spegel 從未被部署到這個測試叢集——現行模板的 `bootstrap/helmfile.d/01-apps.yaml` 不含 spegel（0 處），它只存在於 jg-base 的 Flux 路徑上，所以 `reconcile-jcom-lineage` 記錄的單節點 Spegel 風險在這次驗收中沒有被觸發，也沒有被排除。

## Risks / Trade-offs

- **上游模板針對的 Talos 版本可能與本 repo pin 的不同**（`.mise.toml:27` talos 1.12.4、`:12` talhelper 3.1.5） → 列為 spike，移植前先確認相容性。
- **手動路徑無人實際使用時會再次腐化** → D4 的可執行檢查是主要防線；另外文件拆分（④）會讓它有明確歸屬，不再夾在 Omni 步驟中間。
- **兩條路徑的 CI/驗證成本翻倍** → 接受。手動路徑是給進階使用者與逃生用的，不需要與 Omni 路徑同等的自動化覆蓋。
- **`bootstrap-apps.sh` 條件化可能誤判路徑** → 由設定決定而非推測，並在誤判時 fail fast 而非略過檢查。
- **修 `cluster_svc_cidr` 預設可能改變既有叢集的渲染結果** → 既有叢集的 `cluster.yaml` 多半已明寫該值；未明寫者需逐一確認後再改，不可直接切換預設。

## Migration Plan

1. **先修兩個既有缺陷**（懸空變數、預設值矛盾）——與移植無關，本身就是 bug，可獨立驗證。
2. 移植模板與 schema，先不接線（不動 `makejinja.toml`、不動 Taskfile），確認檔案齊全。
3. 接線：`makejinja.toml` 加 `nodes.yaml`、根 Taskfile 加變數與 include、補 `bootstrap:talos`。
4. 條件化 `bootstrap-apps.sh` 的前置檢查，並確認 Omni 路徑不受影響（既有叢集跑一次 `task configure` 應無 diff）。
5. 在實機或 VM 上實測一次完整手動 bootstrap。
6. 更新 `README.md:205`，通知 ④ 的 task 2.2 解除阻塞。
7. **Rollback**：移植的檔案都是新增；未接線前完全無影響。接線後若出問題，回退 `makejinja.toml` 與 Taskfile 兩處即可。

## Open Questions

- 上游模板與本 repo pin 的 Talos 1.12.4 / talhelper 3.1.5 是否相容？若不相容，是升級 pin 還是調整模板？
- `talenv.yaml.j2` 的 `talosVersion` / `kubernetesVersion` 從哪裡取值？要與 `.mise.toml` 的 pin 對齊，還是獨立管理？
- 手動 Talos 叢集的正確 `cluster_svc_cidr` 預設究竟是什麼？`cluster.sample.yaml:34-36` 的敘述需實測確認後才能寫進 schema。
- ~~手動路徑要不要納入獨立欄位，還是由「有無 `nodes.yaml`」推導？~~ **已決議（2026-08-09）**：新增必填欄位 `provisioning_path: "omni" | "talos"`，無預設。

  推導方案在實作中被證實不可行：`nodes.yaml` 現在對**每個** repo 都會自動生成（makejinja 缺一個宣告的 data 檔就整個中止），所以它的存在與否無法區分兩條路徑；殘留的 `talos/` 目錄同樣會誤導。

  連帶的實作決定：
  - **跨檔約束**：`omni ⇒ nodes: []`、`talos ⇒ list.MinItems(1)`。`cue vet` 對多個資料檔是各自驗證而非合併，所以 `validate-schemas` 改為先用 `yq` 把 `cluster.yaml` 與 `nodes.yaml` 合成單一檔再驗——這也更貼近實際，因為 makejinja 本來就是把兩者合成同一個 render context。
  - **`bootstrap-apps.sh` 條件化**：`TALOSCONFIG` 與 `talhelper` 只在 `talos` 路徑檢查。路徑讀自 `cluster.yaml`，未宣告時直接 error 而非猜測預設。
  - **與 ② 的組合**：②「appliance ⇒ Omni」只需加一條 `appliance ⇒ provisioning_path: "omni"`，本 change 的 `omni ⇒ nodes: []` 會讓「appliance 併存手動節點宣告」自動被拒絕，不需要另寫規則。
