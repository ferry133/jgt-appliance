# KubeSpan 跨站點 / 跨 NAT 網路 — 發現與建議

> 範圍:Talos + Sidero Omni 管理的叢集(jg-jiahd 及 ~20 個同結構叢集)如何把節點橫跨不同站點/網段加入。
> 結論日期:2026-06-25。實測叢集:jg-jiahd(CP 在站點 A `10.9.9.x`,remote worker 在站點 B `10.9.1.x`,公網 `1.34.181.95`)。

---

## TL;DR

1. **KubeSpan 沒有 NAT 穿透,也沒有 relay/TURN/ICE。** 兩個節點若各自在自己的 NAT 後面、且沒有任一端「對外可達」,KubeSpan 的資料面**連不起來** —— 這是 Talos 的根本限制,不是 Omni 設定能解決的。
2. **Omni / SideroLink 只負責「管理面」,不轉送叢集資料面流量。** 註冊、下設定、kubectl/talosctl proxy 走 Omni;但 etcd、pod↔pod、kubelet 走 KubeSpan 的點對點,**不經過 Omni**。
3. **WireGuard 只要一端可達,握手就雙向成立。** → 可擴展的正解是把**「可達錨點」放在控制平面(最好是 public IP)**,之後**任意數量的 remote worker、在任何 NAT 後面,都零設定加入**(它們主動往外連到可達的 CP)。
4. **逐節點 port-forward / 防火牆 / 固定 IP 不可擴展** —— 只適合一次性 workaround,不適合做為 20 叢集的常態。
5. **跨網際網路的節點請當 worker,不要當 control-plane**:etcd 對延遲極敏感,WAN 抖動會觸發 leader 重選、危及整個叢集。

---

## 背景

目標是「像 Omni 宣傳的那樣,隨手把節點從任何地方加進叢集」。Omni 確實讓**加機器**這件事零摩擦 —— 但那是**管理面**。叢集要真的能跨站點一起運作,**資料面**(節點↔節點)必須連得起來,而那靠 KubeSpan。

---

## 核心限制:KubeSpan 無 NAT 穿透 / 無 relay

官方文件與社群討論一致確認:

- KubeSpan 是**點對點 WireGuard mesh**,靠 discovery 服務交換各節點的「對外 apparent IP」,然後節點間**直接**建立 WireGuard。
- 它**沒有** TURN/ICE 這類 NAT 穿透,也**沒有中繼節點**。
- 文件原話:雙重 NAT「常常能自動通」(UDP 穿透通常寬鬆),但**不保證** —— 兩端都在防火牆後時,「the connection may not be established correctly - it depends on each end sending out packets in a limited time window」。
- 社群結論:**兩組機器各自在自己 NAT 後面 → KubeSpan 連不起來**;但「一組在私網、另一組有 public IP」**可行**。
- **最佳實踐(文件原話)**:「ensure that one end of all possible node-node communication allows UDP port 51820, inbound」。

KubeSpan 的 WireGuard 埠是 **UDP 51820,寫死、不能改**。

---

## 兩條獨立的 WireGuard 網路(關鍵釐清)

**KubeSpan 連線「會不會經過 Omni(jcom)當 relay?」→ 不會。**

| | **SideroLink**(經 Omni / jcom) | **KubeSpan**(節點↔節點) |
|---|---|---|
| 用途 | 管理面:註冊、下設定、talosctl/kubectl proxy、機器狀態 | 資料面:etcd、pod↔pod、kubelet |
| 路徑 | 每個節點**主動往外**連 Omni 公開端點 → **經過 jcom** | 節點之間**直接點對點**,**不經過 Omni** |
| NAT 友善 | ✅(出站發起,免 port-forward) | ❌(需一端可達) |
| Omni 在 KubeSpan 的角色 | — | 只當 **discovery**:交換「對方對外 IP」,**只給地址、不轉送流量**,**無 TURN/ICE** |

為什麼不乾脆用 SideroLink 當中繼?SideroLink 是為低頻寬控制流量設計;若把整個叢集資料面繞經 Omni,Omni 會變頻寬瓶頸 + 資料面單點故障。社群一直在要求 KubeSpan 加 relay,但目前沒有。

> **附帶機會**:jcom(第三站點,跑 Omni)本身**對外可達**(節點都連得到它的公開 UDP 端點)。因此那個站點/那種有 public IP 的位置,**很適合放一台 jg-jiahd 的「public 錨點」節點**(見下方錨點模型)。注意 jcom 節點本身是獨立的單節點叢集,不能直接當 jg-jiahd 的 KubeSpan peer;要的是「在可達的位置放一台屬於 jg-jiahd 的節點」。

---

## 我們案例為什麼會卡

- 站點 A(CP ×2,`10.9.9.x`)與站點 B(worker,`10.9.1.x` / 公網 `1.34.181.95`)**各自在自己的 NAT 後面** → 典型「雙重 NAT」,KubeSpan 自動穿透不成立。
- 另外站點 B 的 UniFi router 自己在公網 **51820** 跑了一個 WireGuard VPN server,增加干擾。
- 實測(用 hostNetwork 測試 pod,結果寫進 pod `terminated.message` 繞過壞掉的反向 log 路徑):
  - 兩網段雙向 ping / 所有 TCP 埠全 FAIL;
  - KubeSpan ULA 互 ping 雙向 FAIL → 隧道 DOWN;
  - 而**同站點**的兩台 CP 之間 KubeSpan ULA 互通 → 證明 KubeSpan 設定本身正確,卡的是跨站可達性。

---

## 目前的 workaround(現有 remote worker)— 不可擴展

> ⚠️ **已於 2026-06-25 被「錨點模型」取代**(patch `510` 已移除、worker 改走 CP 錨點)。本節保留作為「讓 worker 自己對外可達」做法的對照;實際採用的是下方的錨點模型。

讓**站點 B 這台 worker 對外可達**:

1. 站點 B router:**Port Forward 對外 `UDP 51830` → `10.9.1.171:51820`**(用空閒埠,VPN server 留在 51820 不動)。
2. 防火牆規則:**Src Port = Any**、Dst Port = 51830。
3. Omni 機器專屬 ConfigPatch,告訴叢集「往這個公網 endpoint 找它」:

```yaml
# omnictl apply -f <file>
metadata:
    namespace: default
    type: ConfigPatches.omni.sidero.dev
    id: 510-jg-jiahd-glb-kubespan-endpoint
    labels:
        omni.sidero.dev/cluster: jg-jiahd
        omni.sidero.dev/machine: ad19f7e3-8da5-90d1-63dc-48210b732612   # 該 worker 的 machine ID
spec:
    data: |-
        apiVersion: v1alpha1
        kind: KubeSpanEndpointsConfig          # 注意:Span 大寫 S!Kubespan(小寫) 會被 Omni 拒絕 "not registered"
        extraAnnouncedEndpoints:
          - 1.34.181.95:51830                  # 公網 IP : 對外轉發埠
```

結果:約 1 分鐘 KubeSpan peer 變 `up`,`kubectl logs`、跨節點 pod、CoreDNS 全部恢復。

**為什麼不可擴展**:每加一台 remote worker 都要再來一輪 port-forward + 防火牆 + 固定 IP + 一條機器專屬 patch。20 叢集 × 多台 = 無法維護。而且還依賴節點內網 IP 固定(DHCP 一變就斷)與站點 B 公網 IP 固定。

---

## 可擴展的正解:錨點模型(Anchor the control plane)

**把「可達端」從每台 worker 翻轉到控制平面,設定成本就從「每台 worker」變成「每個叢集一次」。**

- WireGuard 只要一端可達,握手就雙向成立。
- 所以只要**控制平面節點對外可達**,**任何** remote worker(任何 NAT 後)都**零設定**加入:它主動往外連到可達的 CP,隧道一通即雙向(CP→worker 的 kubelet/logs 流量也回得來)。

兩種落地:

1. **(最乾淨、最可擴展)控制平面放在 public IP**
   例如一台雲端小 VM 當 CP/錨點(或放在 jcom 那種對外可達的站點)。官方明講「一組私網 + 一組 public IP」可行。之後 20 叢集的 remote worker 全部零設定。
2. **(沿用現有硬體)CP 站點做一次性可達設定**
   站點 A 對每台 CP 各做一個 port-forward(對外埠 → CP:51820)+ 一條 `KubeSpanEndpointsConfig` patch(announce 站點 A 公網 IP : 各自對外埠)。**每個叢集設定一次**,之後該叢集的 worker 全零設定。
   - 注意:worker 可能需要連到**所有** CP(pod 可能落在任一 CP),所以理想是每台 CP 都可達。

### 加第 N 台 remote worker(錨點模型下)

| 項目 | 需要設定嗎? |
|---|---|
| Port forward | ❌ 不用 |
| 防火牆規則 | ❌ 不用 |
| 固定內網 IP | ❌ 不用 |
| 機器專屬 endpoint patch | ❌ 不用 |
| 在 Omni 把機器加進叢集、指定 worker 角色 | ✅ 就這一步 |

前提:控制平面(錨點)已經可達。

### 實作驗證(jg-jiahd 範例,2026-06-25)

方案 2(沿用現有硬體、CP 站點一次性可達)已在 jg-jiahd 實作並驗證。

**站點 A 路由器(UniFi,固定公網 `220.132.89.94`)只加 port-forward:**

| 對外 (UDP) | → 內網目標 | 對應 CP / machine ID |
|---|---|---|
| 50822 | `10.9.9.22:51820` | talos-dk0-t6p / `730b41a1-…-48210b73264d` |
| 50823 | `10.9.9.23:51820` | talos-9mf-rjc / `a1936aea-…-48210b6fdd3b` |

> **乾淨的 port-forward 不需要另外加防火牆規則。** UniFi(及多數路由器)建立 port-forward 時會**自動放行**該轉發流量(DNAT 的同時隱含允許 inbound)。站點 A 只做了上面兩條 port-forward、**沒有**任何手動 firewall policy,就直接通了 —— 已實證 worker 確實從網際網路打進這兩個埠。
>
> (站點 B 當時之所以要談防火牆 / `Src Port=Any`,是因為那邊**先手動建了** firewall policy 去框這個流量 → 反而要把它設對。沒手動建 policy,就走「port-forward 自動放行」最單純的路。)

**每台 CP 一條 machine-scoped announce patch**(格式同前面 `510` 那段,只是綁到 CP 機器):

```yaml
# 511-jg-jiahd-cp-dk0-kubespan-endpoint  → machine 730b41a1…/10.9.9.22
spec.data: |-
  apiVersion: v1alpha1
  kind: KubeSpanEndpointsConfig
  extraAnnouncedEndpoints:
    - 220.132.89.94:50822
# 512-jg-jiahd-cp-9mf-kubespan-endpoint  → machine a1936aea…/10.9.9.23
#   extraAnnouncedEndpoints: [ 220.132.89.94:50823 ]
```

- 套用到 CP 是**免重啟的網路設定**(etcd 全程 2/2、節點不掉);仍建議**一台一台**來,保護脆弱的 2 成員 quorum。

**關鍵驗證**:刪除 worker 自己的舊 workaround(patch `510` + 站點 B 的 51830 轉發)後,worker 純靠「主動連 CP 錨點」運作 → **約 2.7 分鐘 KubeSpan 持續 `up`、0 次 down**,worker pod→kube-svc/CoreDNS OK,`kubectl logs`(CP→worker 反向)OK。**證明:此後任何 remote worker 零設定即可加入。**

### 限制(誠實說明)

- **跨站 worker 彼此的「直接 pod↔pod」**:若兩台 worker 各在自己 NAT 後、且都不可達 → 它們之間連不起來。多數工作負載是 worker→中央服務/CP,沒問題;但若你需要兩個 remote 站點的 pod 直接互打,該站也要有可達端。

---

## 給 ~20 叢集的策略

| 目標 | 建議架構 | 擴展性 |
|---|---|---|
| 只是要 Omni **集中管理**多叢集 | 每叢集節點**同站**(不跨 NAT),KubeSpan 不需要 | ✅ 完全零摩擦 |
| **單一叢集跨站**(remote worker) | **錨點放 public IP**(雲端 CP 或 CP 站點一次性 port-forward),worker 零設定 | ✅ per-cluster 一次性 |
| 跨站 worker **彼此**直接 pod 通訊 | 該站也要有可達端 | ⚠️ 受限 |

---

## 操作參考(verbatim)

**Omni / omnictl 存取**(jcom 跑 Omni,gRPC 串流需 port-forward):
```sh
KUBECONFIG=~/coding/jcom/kubeconfig kubectl port-forward -n omni svc/omni 18080:8080 &
source ~/.config/omni/env          # OMNI_ENDPOINT + OMNI_SERVICE_ACCOUNT_KEY
omnictl get machines
omnictl get clustermachinestatus   # ID + ready/stage;apid=false 常代表該機器資料面(KubeSpan)不通
omnictl apply -f patch.yaml
```

**找 worker 的 machine ID**:`omnictl get clustermachinestatus`,對照 MAC(ULA 尾碼 `fe73:2612` ↔ MAC `…73:26:12`)。

**ConfigPatch 標籤慣例**:
- cluster 全域:`omni.sidero.dev/cluster: <cluster>`
- machine-set:`omni.sidero.dev/machine-set: <set>`
- **單一機器**:`omni.sidero.dev/machine: <machine-id>`(endpoint patch 必須用這個,**不可** cluster 全域 —— 否則 CP 也會去 announce 錯誤的公網位址)

**KubeSpan 啟用**(cluster 全域,所有節點自動套用 —— 已存在 `500-jg-jiahd-kubespan`):
```yaml
machine:
  network:
    kubespan:
      enabled: true
      advertiseKubernetesNetworks: false   # 搭 Cilium 必須 false(pod 流量由 CNI 處理)
```

**驗證 KubeSpan 是否通**(talosctl 經 Omni 的串流會失敗,改用測試 pod):
- 從 CP 節點 hostNetwork pod ping 對方的 KubeSpan ULA(`fd5c:…`)→ 通 = `up`。
- worker 上 pod nc `10.96.0.1:443`(kube API)、`10.96.0.10:53`(CoreDNS)→ OK = 跨節點通。
- `kubectl logs <worker-pod>` 能讀到內容 = apiserver→kubelet(反向)通。
- 讀不到對方節點 pod 的 log,通常代表 apiserver→kubelet:10250(KubeSpan 反向)斷。

**繞過壞掉的反向路徑讀結果**:測試 pod 把結果寫進 `/dev/termination-log`,再讀 `.status.containerStatuses[0].state.terminated.message`(這條走 kubelet→apiserver,出站方向,永遠可讀)。

---

## 決策紀錄

- **remote 節點 = worker,不是 control-plane**:etcd 跨 WAN 延遲敏感,會危及 quorum;worker 斷線只是 NotReady、pod 重排,風險低。
- **jcom 的 Cilium 必須是 native + MTU 1500(例外)**:jcom 單節點且 host Omni,全域 tunnel/MTU 1370 會壓垮 Omni 的 SideroLink WireGuard(`sendmmsg: message too long`)→ Omni 變慢。見 jcom repo commit `f5d7fc3`。
- **KubeSpan 多節點叢集的 Cilium = vxlan tunnel + MTU 1370**(jg-base `9ba156f`):native + autoDirectNodeRoutes 假設同網段,與 KubeSpan 不相容。

---

## 來源

- KubeSpan(Talos v1.13 docs):<https://docs.siderolabs.com/talos/v1.13/networking/kubespan>
- KubeSpanEndpointsConfig 參考:<https://docs.siderolabs.com/talos/v1.12/reference/configuration/network/kubespanendpointsconfig>
- Proper KubeSpan port forwarding support — talos #9038:<https://github.com/siderolabs/talos/issues/9038>
- NAT Traversal? — talos discussion #8338:<https://github.com/siderolabs/talos/discussions/8338>
- Only one node at a time working behind NAT? — talos #9237:<https://github.com/siderolabs/talos/discussions/9237>
- Omni for Kubernetes cluster management:<https://www.siderolabs.com/omni-for-kubernetes-cluster-management>
