# What a wrongly-scoped Cloudflare token looks like

**A dated record, not a procedure.** Captured 2026-08-16 on this cluster while its
`cloudflare_token` was still broken; **repaired the same day in `546016a`**. It was
written down first because repairing the token destroys the evidence — the broken
credential stops existing, so afterwards nobody can demonstrate that a scope check
catches this without deliberately constructing a bad token.

If you run these calls today you will get case A-after below: one zone, `active`,
matching nameservers. **That confirms the repair, it does not contradict the
capture.** The token ids here belong to credentials that are gone.

The point of the record is narrow and it is not "we misconfigured a token". It is
that **three different credentials all pass "is this token valid?" and only one of
them works**, and that the two failures are silent at every layer — the API says
the credential is fine, and external-dns says nothing at all because it has
nothing to say.

## The three cases

All three are `cfut_…`, 53 characters, and all three return
`success: true, status: active, "This API Token is valid and active"` from
`GET /client/v4/user/tokens/verify`. Validity separates none of them.

| | token id | `GET /zones` | zone status | zone `name_servers` | live delegation | works |
|---|---|---|---|---|---|---|
| **A-before** — this cluster, broken | `e2702ae3…` | `200`, `success:true`, **0 zones** | — | — | — | no |
| **A-after** — same field, repaired | `7c3fa77e…` | `200`, **1 zone** `janncot.cc` `b67776ce…` | `active` | `marge` / `sage` | `marge` / `sage` | **yes** |
| **B** — `jgt-omni-accept`, same domain | `edca407f…` | `200`, **1 zone** `janncot.cc` `c9851d69…` | `moved` | `carioca` / `luke` | `marge` / `sage` | **no** |
| **C** — `jg-jiahd`, another working one | `9b8f84c1…` | `200`, **1 zone** `jiahd.cc` `07142156…` | `active` | `rajeev` / `shubhi` | `rajeev` / `shubhi` | **yes** |

Read the table by column rather than by row, because that is where the argument is:

- `http_status` and `success` are **identical in all four**. "The API accepted it"
  is not a check.
- `count` separates A-before from the rest — and nothing else does.
- `status` plus the nameserver comparison separates **B** from A-after — and
  nothing else does. So `count >= 1` is not the assertion either.

A-before and A-after are the *same field on the same cluster*, three days apart.
B and C differ in nothing cheap: both 53-character `cfut_` tokens, both verify
active, both return exactly one zone bearing the domain asked for.

Note the zone ids. A-after points at `b67776ce…`; B points at `c9851d69…`. Both
are live Cloudflare zones named `janncot.cc`, in two different accounts, and only
the first is the one the domain is delegated to.

### A — valid, sees nothing

Token id `e2702ae3f8a412cf4c15fb988cf77104` is byte-identical to
`backup_r2_access_key_id` in `cluster.yaml:50`. It is the **R2 API token**, pasted
into the DNS field. R2 tokens carry no zone permission, so:

```
$ curl -s -w '\n[http_status=%{http_code}]\n' \
    https://api.cloudflare.com/client/v4/zones -H "Authorization: Bearer $T"
{"result":[],"result_info":{"page":1,"per_page":20,"total_pages":0,"count":0,"total_count":0},"success":true,"errors":[],"messages":[]}
[http_status=200]
```

Verbatim, and `?name=janncot.cc` returns the identical body. **HTTP 200,
`success: true`, `errors: []`, `total_count: 0`.** Everyone expects a 403 here
and there is no 403 — it is an *empty answer to a well-formed question*. external-dns applies `--domain-filter=janncot.cc`
against that empty list, matches no hosted zone, and skips every record
**silently**: at `--log-level=info` it emits nothing at all. A pod that has run
for hours with zero log lines after startup reads as healthy and is not.

This is the failure that a validity check cannot see and a one-call scope check
can: **assert the zone is in the list, not that the token verifies.**

### B — valid, sees a zone of the right name, still inert

B is the more interesting one, and it is why "sees zone `janncot.cc`" is not
sufficient either.

`janncot.cc` exists as **two Cloudflare zones in two accounts**. B's token is
scoped to `c9851d69…`, whose status is `moved` and whose nameservers are
`carioca` / `luke`. The live delegation is elsewhere:

```
# Cloudflare DoH and Google DoH, independently:
janncot.cc      NS  →  marge.ns.cloudflare.com, sage.ns.cloudflare.com
im.janncot.cc   A   →  Status 3 (NXDOMAIN)
```

Zone `c9851d69…` nonetheless contains eight records, including a complete and
correct-looking answer for the hostname that does not resolve:

```
CNAME  im.janncot.cc            → external.janncot.cc
CNAME  external.janncot.cc      → edc29697-b3d7-4d30-bbba-fdd048012e68.cfargotunnel.com
TXT    k8s.cname-im.janncot.cc  → heritage=external-dns,external-dns/owner=default,…
```

That tunnel id is the one in this repo's `cloudflare-tunnel.json.old` — these are
**this cluster's own records**, written before the domain moved accounts, now
stranded in a zone nobody queries.

### C — what a pass looks like

Without this the other two only show that things are broken. `jg-jiahd`'s token,
same 53-character `cfut_` shape, same `active` verify response:

```
GET /zones?name=jiahd.cc  →  1 zone, id 07142156…, status "active",
                             name_servers [rajeev, shubhi]
DoH  NS jiahd.cc          →  [rajeev, shubhi]          ← matches
DoH  A  cc.jiahd.cc       →  Status 0, 172.67.159.120, 104.21.50.78
```

Zone `status: active` rather than `moved`, `name_servers` equal to the live
delegation as a set, and the records it publishes resolve from outside. That is
the whole of correct, and it is three calls.

So a token can be valid, and scoped to a zone with exactly the right name, and
every record it writes can still be unreachable. The assertion has to reach one
step further than the name:

```
zone.name_servers  ==  the NS set the domain is actually delegated to
```

Measured over DoH, not the local resolver — see the trap below.

## Reproducing it

Read-only, one call each. `$T` is the token, `$D` the domain.

```sh
# 1. validity — necessary, and proves nothing on its own
curl -s https://api.cloudflare.com/client/v4/user/tokens/verify \
  -H "Authorization: Bearer $T" | jq '.success, .result.status'

# 2. scope — catches case A
curl -s "https://api.cloudflare.com/client/v4/zones?name=$D" \
  -H "Authorization: Bearer $T" | jq '.result | length, .[0].id, .[0].status'

# 3. is it the delegated zone — catches case B
curl -s "https://api.cloudflare.com/client/v4/zones?name=$D" \
  -H "Authorization: Bearer $T" | jq -r '.[0].name_servers // .result[0].name_servers | sort | join(" ")'
curl -s -H 'accept: application/dns-json' \
  "https://cloudflare-dns.com/dns-query?name=$D&type=NS" | jq -r '[.Answer[].data] | sort | join(" ")'
# these two must match
```

## A trap that cost a measurement

`dig` from a host on this LAN does **not** answer this question, and the failure
is not "the default resolver is wrong" — naming a different server does not help:

```
$ dig +short NS janncot.cc @1.1.1.1
k8s-gateway.network.janncot.cc.          # not Cloudflare, and not 1.1.1.1 either
```

The mechanism, measured rather than assumed. Outbound port 53 is transparently
redirected by the LAN gateway, so **every** UDP/53 query is answered locally
whatever address is on the command line — including one that cannot exist:

```
$ dig +short NS janncot.cc @192.0.2.1      # TEST-NET-1, unroutable by definition
k8s-gateway.network.janncot.cc.            # …and it answered
$ dig +short A example.com @192.0.2.1
104.20.23.154                              # so does everything else
```

The host is `10.9.1.125` with `nameserver 10.9.1.1` — inside this appliance's own
`node_cidr` (`cluster.yaml:14`), behind a gateway that both intercepts :53 and
forwards this domain to the cluster's `k8s-gateway`. So the caveat belongs to the
**resolver path**, not to a job title: any host whose queries traverse 10.9.1.1
gets the wrong answer, and a laptop elsewhere does not. Two sessions on this same
host is one measurement, not two.

For anything about public delegation use DoH, which is HTTPS and therefore not
interceptable by the same trick, and cross-check a second provider:

```sh
curl -s -H 'accept: application/dns-json' "https://cloudflare-dns.com/dns-query?name=$H&type=$T"
curl -s "https://dns.google/resolve?name=$H&type=$T"
```

## What this cluster's chain of events was

1. Originally on Cloudflare account `6585a8…` with tunnel `edc29697…`
   (`cloudflare-tunnel.json.old`). external-dns held zone `c9851d69…` and
   `im.janncot.cc` resolved.
2. `janncot.cc` was moved to account `b66ae737…`. The old zone went `moved`, its
   NS pair stopped being authoritative, and its eight records went inert —
   without being deleted, and without anything logging a complaint.
3. Tunnel `kube` (`ba6225b6…`) was created in the new account and
   `cloudflare-tunnel.json` updated. That half is correct and the tunnel is up.
4. `cloudflare_token` was filled with the R2 token. external-dns could not see any
   zone from then on, so nothing was ever re-created in the new zone.
5. **2026-08-16, `546016a`** — token replaced with one scoped to zone `b67776ce…`.
   external-dns created six records within three seconds of the restart, and
   `https://im.janncot.cc` returned `HTTP/2 401 www-authenticate: Basic
   realm="ttyd"` through `cf-ray …-SJC`. Public path fixed.

Steps 2–4 each fail quietly. The visible symptom is one hostname not resolving,
four layers away from any of them.

Two things step 5 did **not** fix, recorded so nobody reads a green public path as
a green cluster:

- `im.janncot.cc` still does not resolve **on the LAN** — `k8s-gateway` answers
  NXDOMAIN. The route's `spec.parentRefs` names only `envoy-external`, which has
  no address because of the LB pool conflict; `envoy-internal` appears in
  `status.parents` via a Gateway merge but not in the spec. Which of those is the
  operative cause is not established.
- `envoy-external` remains `Programmed=False`. It does **not** affect external-dns
  — the `external-dns.alpha.kubernetes.io/target` annotation on the Gateway
  supplies the target and the missing address is irrelevant. That was an open
  question in the first version of this document, resolved by observation when the
  record appeared anyway.

## Related

- `cluster.yaml:32` — the field, repaired in `546016a`; the comment above it
  records both failure shapes so the next person filling it in sees them
- `docs/deploy/manual.md:141` — how the correct token is created
- `cloudflare-tunnel.json.old` — the stale credential the inert records point at
