# Pointing the router's DNS at the cluster

One configuration step, performed by the operator during installation. After it,
the customer never touches DNS again.

## Why this step exists

Internal hostnames (`homebridge.<domain>`, `mqtt.<domain>`, …) resolve to an
address on the customer's own LAN. Three ways to deliver that answer were
considered; only this one works end to end:

| | why not |
|---|---|
| Publish public A records with the private address | Cloudflare refuses to serve RFC1918 answers for zones it hosts. Measured: the API accepts the record, the authoritative NS returns NXDOMAIN, while a record with a public address created in the same breath resolves immediately. |
| mDNS / `.local` | Resolvers only route `.local` to multicast, so every hostname would have to change — and `.local` cannot hold a public TLS certificate, so anything with a login shows a certificate error unless a private CA is installed on every device. |
| Delegate a subdomain to another DNS provider | Works, but adds a second provider and its credentials, and puts an extra label in every hostname. |

`k8s-gateway` answers those names correctly. It just has to be asked, and a
resolver is only asked if something points at it.

## What to set

Set the LAN's **DNS server** to the cluster's shared LAN address — the same
address `envoy-internal` and `mqtt` use. Find it with:

```sh
kubectl -n network get svc k8s-gateway \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}{"\n"}'
```

Three ways to deliver that. Pick the first one your router supports.

| | internal names | cluster down | router support |
|---|---|---|---|
| **DHCP DNS server → cluster**, plus a secondary | all, automatically | slow but works | every router |
| Conditional forwarding — only `<domain>` to the cluster | all, automatically | only internal names break | dnsmasq-based (UniFi, OpenWrt, pfSense) |
| Per-host records on the router | added by hand | only those names break | some models |

**The default is the DHCP DNS server**, because it is the only one every router
has, and an appliance ships to whatever router the customer already owns.

`k8s-gateway` forwards domains it does not serve — verified, `github.com`
resolves through it — so under normal operation it is transparent to the LAN.
Always set a **secondary** DNS (the router itself, or 1.1.1.1): if the cluster
stops answering entirely, clients fall back after a timeout. Note what that does
*not* cover — if k8s-gateway answers *wrongly* (NXDOMAIN, SERVFAIL) the client
accepts that answer and never asks the secondary.

If the router does support conditional forwarding, prefer it: only queries for
`<domain>` go to the cluster, so a cluster outage cannot affect anything else.
UniFi's UDM/UDR run dnsmasq and support `server=/<domain>/<addr>` at that layer,
though whether the UI exposes it depends on the version.

## Pin the address before you set it

On an appliance the address is chosen by ARP probing (`lan-address-probe`),
which by default re-checks it and may reselect if something else starts
answering for it. **Once it is written into a router, it is an external
contract**: a reselection would leave the router pointing at nothing, and every
internal name would fail at once with nothing in the cluster looking wrong.

So before configuring the router, promote the discovered address to a declared
one:

```yaml
# cluster.yaml
lan_shared_addr: "10.9.x.y"   # the address the probe settled on
```

Re-render and push. From then on the address is fixed, and a collision is
reported for a human to act on rather than silently worked around.

## Verify

From a LAN client — a laptop on Wi-Fi, not the node:

```sh
# should return the cluster's LAN address
nslookup internal.<domain>
```

If it returns nothing, the DHCP lease has not been renewed yet. Reconnect the
client to the network and try again before changing anything.

## What happens if it is lost

A router reset, a replacement unit, or an ISP-pushed configuration all silently
undo this step. Every internal hostname stops resolving on the LAN while the
cluster itself stays perfectly healthy — which is exactly the kind of failure
nobody attributes correctly.

The daily health check asks the router directly and reports
`LAN cannot resolve internal names` as a FAIL, which also withholds the dead-man
ping. Re-doing the step above is the fix.
