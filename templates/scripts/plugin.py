from pathlib import Path
from typing import Any

import base64
import hashlib
import hmac
import ipaddress
import makejinja
import re
import json


# Return the filename of a path without the j2 extension
def basename(value: str) -> str:
    return Path(value).stem


# Base64-encode a string
def b64encode(value: str) -> str:
    return base64.b64encode(value.encode('utf-8')).decode('utf-8')


# Return the nth host in a CIDR range
def nthhost(value: str, query: int) -> str:
    try:
        network = ipaddress.ip_network(value, strict=False)
        if 0 <= query < network.num_addresses:
            return str(network[query])
    except ValueError:
        pass
    return False


# Return the age public or private key from age.key
def age_key(key_type: str, file_path: str = 'age.key') -> str:
    try:
        with open(file_path, 'r') as file:
            file_content = file.read().strip()
        if key_type == 'public':
            key_match = re.search(r"# public key: (age1[\w]+)", file_content)
            if not key_match:
                raise ValueError("Could not find public key in the age key file.")
            return key_match.group(1)
        elif key_type == 'private':
            key_match = re.search(r"(AGE-SECRET-KEY-[\w]+)", file_content)
            if not key_match:
                raise ValueError("Could not find private key in the age key file.")
            return key_match.group(1)
        else:
            raise ValueError("Invalid key type. Use 'public' or 'private'.")
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while processing {file_path}: {e}")


# Return cloudflare tunnel fields from cloudflare-tunnel.json
def cloudflare_tunnel_id(file_path: str = 'cloudflare-tunnel.json') -> str:
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
        tunnel_id = data.get("TunnelID")
        if tunnel_id is None:
            raise KeyError(f"Missing 'TunnelID' key in {file_path}")
        return tunnel_id

    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except json.JSONDecodeError:
        raise ValueError(f"Could not decode JSON file: {file_path}")
    except KeyError as e:
        raise KeyError(f"Error in JSON structure: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while processing {file_path}: {e}")


# Return cloudflare tunnel fields from cloudflare-tunnel.json in TUNNEL_TOKEN format
def cloudflare_tunnel_secret(file_path: str = 'cloudflare-tunnel.json') -> str:
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
        transformed_data = {
            "a": data["AccountTag"],
            "t": data["TunnelID"],
            "s": data["TunnelSecret"]
        }
        json_string = json.dumps(transformed_data, separators=(',', ':'))
        return base64.b64encode(json_string.encode('utf-8')).decode('utf-8')

    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except json.JSONDecodeError:
        raise ValueError(f"Could not decode JSON file: {file_path}")
    except KeyError as e:
        raise KeyError(f"Missing key in JSON file {file_path}: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while processing {file_path}: {e}")


# Return the GitHub deploy key from github-deploy.key
def github_deploy_key(file_path: str = 'github-deploy.key') -> str:
    try:
        with open(file_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while reading {file_path}: {e}")


# Return the Flux / GitHub push token from github-push-token.txt
def github_push_token(file_path: str = 'github-push-token.txt') -> str:
    try:
        with open(file_path, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while reading {file_path}: {e}")


# Return the shared claude-code Auth0 application's fields from auth0.json
#
# A local file rather than cluster.yaml fields because this template repo is
# public and every cluster fronts claude-code with the same Auth0 application:
# one copied file per cluster directory beats pasting the same client secret
# into twenty configs. Same idiom as cloudflare-tunnel.json — gitignored, read
# at render time, never committed.
#
# Missing here is a hard stop, not an empty default: OIDC mode gives ttyd no
# fallback (it binds loopback), so a cluster rendered with a blank client
# secret deploys a terminal nobody can reach.
def auth0_config(file_path: str = 'auth0.json') -> dict[str, str]:
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"File not found: {file_path} — claude-code defaults to Auth0 login. "
            f"Copy auth0.json from another cluster directory, or set "
            f"`claudecode_auth0: false` in cluster.yaml to use ttyd basic auth.")
    except json.JSONDecodeError:
        raise ValueError(f"Could not decode JSON file: {file_path}")

    missing = [k for k in ('domain', 'client_id', 'client_secret')
               if not data.get(k)]
    if missing:
        raise KeyError(f"Missing or empty in {file_path}: {', '.join(missing)}")
    return data


# Derive oauth2-proxy's cookie secret from the cluster's own age key
#
# Derived rather than generated so it is stable: a fresh random value on every
# render would sign every session out at each `task configure` and rewrite the
# encrypted secret for no reason. Derived rather than shared so a cookie minted
# for one cluster cannot be replayed at another — jg-jiahd and jgtest were
# hand-copied the same value, which is the mistake this closes.
#
# 32 bytes, base64url — the one length oauth2-proxy accepts besides 16 and 24.
def oauth2_cookie_secret(cluster_name: str, file_path: str = 'age.key') -> str:
    key = age_key('private', file_path)
    digest = hmac.new(key.encode('utf-8'),
                      f"claudecode-oauth2-cookie:{cluster_name}".encode('utf-8'),
                      hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode('utf-8')


# Return a list of files in the talos patches directory
def talos_patches(value: str) -> list[str]:
    path = Path(f'templates/config/talos/patches/{value}')
    if not path.is_dir():
        return []
    return [str(f) for f in sorted(path.glob('*.yaml.j2')) if f.is_file()]


class Plugin(makejinja.plugin.Plugin):
    def __init__(self, data: dict[str, Any]):
        self._data = data


    def data(self) -> makejinja.plugin.Data:
        data = self._data

        # Set default values for optional fields.
        # These must match the defaults documented in cluster.sample.yaml —
        # a documented default the code does not apply is a defect.
        data.setdefault('node_default_gateway', nthhost(data.get('node_cidr'), 1))
        data.setdefault('node_dns_servers', ['1.1.1.1', '1.0.0.1'])
        data.setdefault('node_ntp_servers', ['162.159.200.1', '162.159.200.123'])
        data.setdefault('cluster_pod_cidr', '10.42.0.0/16')
        # cluster_svc_cidr is required (no default) — see cluster.schema.cue.
        # coredns must sit at .10 of whatever service CIDR the cluster actually
        # uses, so derive it rather than hardcoding a value that is only correct
        # for one provisioning path. An explicit coredns_cluster_ip still wins.
        data.setdefault('coredns_cluster_ip', nthhost(data.get('cluster_svc_cidr'), 10))
        # Storage class for PVCs that do not pick one explicitly. Databases are
        # block-backed regardless — this selects what bulk media and file shares
        # get, which is the only thing the backend axis decides.
        _backend = data.get('storage_backend')
        data.setdefault('default_storage_class', {
            'nfs': 'sc-nas',
            'replicated': 'longhorn',
        }.get(_backend, 'local-path'))
        # The block tier, for anything that needs fsync durability and file
        # locking. Not derived from storage_backend: NFS is never a valid answer
        # here, whatever the cluster uses for bulk data. An existing cluster
        # whose database is already on NFS overrides this until it can be dumped
        # and restored — a PVC's storageClassName is immutable, so the move is
        # not something a re-render can perform.
        data.setdefault('db_storage_class', 'local-path')
        # Which claude-code instances stay up. Empty by default: each is a root
        # shell with cluster-admin that the tunnel makes reachable. Named here
        # rather than scaled by hand, which works until the next reconcile.
        data.setdefault('claude_code_always_on', [])
        # Auth0 OIDC in front of every claude-code instance, on by default.
        #
        # The alternative is ttyd basic auth, a single shared password in front
        # of a root shell with cluster-admin that the tunnel publishes to the
        # internet — one credential for every operator, rotated by editing
        # twenty configs, and no record of who opened the terminal. OIDC gives
        # per-person accounts, an email allowlist, and revocation in one place.
        #
        # What it costs: OIDC mode leaves ttyd on loopback with no fallback, so
        # the instance is reachable only while oauth2-proxy can reach Auth0 and
        # the callback URL is registered. claude-code is the rescue path for a
        # cluster whose Omni/SideroLink is down, so that path now depends on a
        # third party being up. A cluster that will not accept the trade turns
        # it off with `claudecode_auth0: false` and supplies ttyd_credential.
        data.setdefault(
            'claudecode_auth0_enabled',
            bool(data['claudecode_auth0']) if 'claudecode_auth0' in data
            else True)
        if data['claudecode_auth0_enabled']:
            # Read auth0.json only for what cluster.yaml has not already
            # answered. The clusters that configured Auth0 before the file
            # existed spell all of it out inline, and requiring the file from
            # them anyway would break their next `task configure` over a value
            # they already have.
            fields = ('domain', 'client_id', 'client_secret')
            if not all(data.get(f'claudecode_auth0_{f}') for f in fields) \
                    or not data.get('claudecode_allowed_emails'):
                auth0 = auth0_config()
                for field in fields:
                    data.setdefault(f'claudecode_auth0_{field}', auth0[field])
                # cluster.yaml wins where a cluster needs someone auth0.json
                # does not list — the client's own address, say.
                if auth0.get('allowed_emails'):
                    data.setdefault('claudecode_allowed_emails',
                                    auth0['allowed_emails'])
            if not data.get('claudecode_oauth2_cookie_secret'):
                data['claudecode_oauth2_cookie_secret'] = oauth2_cookie_secret(
                    data['cluster_name'])
        # Backups are encrypted to the cluster's own age public key, taken from
        # .sops.yaml rather than added as another field to fill in. The key is
        # already there, it is already the thing that travels with the cluster
        # at handover, and a public key is not a secret. The consequence worth
        # stating: whoever holds age.key can read the backups, and nobody else
        # can — including the operator holding the R2 credentials.
        if 'backup_age_recipient' not in data:
            sops_config = Path('.sops.yaml')
            recipient = ''
            if sops_config.is_file():
                match = re.search(r'age:\s*["\']?(age1[a-z0-9]+)',
                                  sops_config.read_text())
                if match:
                    recipient = match.group(1)
            data['backup_age_recipient'] = recipient
        # The three LAN-facing services listen on non-overlapping ports
        # (80/443, 53, 1883), so one address serves all of them. Collapsing them
        # turns "find several free addresses on a LAN you have never seen" into
        # "find one", which is the difference between a customer-supplied field
        # and a discovered one.
        #
        # Opt-in, because collapsing is a breaking change for anything on the
        # LAN that already talks to the old addresses — a DNS resolver setting,
        # an MQTT broker address, a HomeKit pairing. An appliance has no such
        # history, so it collapses from the start; an existing cluster does it
        # deliberately by setting lan_shared_addr.
        shared = data.get('lan_shared_addr')
        if shared:
            # Unconditional, not "only if already set". An appliance declares
            # none of these — validation forbids them — so a conditional
            # overwrite would leave them empty and the Gateway annotations null,
            # which is the one shape the Gateway CRD rejects. This field is
            # documented as superseding them, so it supersedes an absent one too.
            for field in ('cluster_gateway_addr', 'cluster_dns_gateway_addr',
                          'mqtt_lb_ip'):
                data[field] = shared
        # Empty is not a sharing key that everything shares — Cilium treats it
        # as no key at all, verified on jgt-omni. So the annotations can sit in
        # jg-base unconditionally and stay inert on clusters that do not share.
        # k8s-gateway answers internal names for clients whose resolver points
        # at it. That is the primary path everywhere, including appliance:
        # Cloudflare refuses to publish RFC1918 answers (D29), so there is no
        # public-DNS route to fall back from. The operator points the router's
        # DNS at it once during installation (D32).
        #
        # It costs no extra address — 4.3 shares one with envoy-internal and
        # mqtt — so the only reason to turn it off is a cluster that runs its
        # own resolver.
        data.setdefault(
            'deploy_k8s_gateway',
            bool(data['k8s_gateway']) if 'k8s_gateway' in data else True)
        # A LoadBalancer on every profile, appliance included. The appliance used
        # to make it a ClusterIP on the reasoning that nothing on the LAN
        # connects to it — cloudflared reaches it by in-cluster DNS. That
        # reasoning missed k8s-gateway, which answers a hostname from whatever
        # address its parent Gateway holds: on jgt-appliance every externally
        # routed name resolved to a ClusterIP no LAN client could reach. The
        # probe now finds a second address for it instead.
        data.setdefault('envoy_external_service_type', 'LoadBalancer')
        # An appliance shares whether or not the address is declared yet. It
        # discovers exactly one address, so on the first boot — before anything
        # is pinned — every LAN service has to share that one or all but the
        # first sit <pending> forever. Keying off `shared` alone left them with
        # jg-base's per-service defaults, which differ by service and therefore
        # share nothing: measured on jgt-appliance, k8s-gateway took 10.9.1.254
        # under key "k8s-gateway" and envoy-internal waited under "envoy-internal".
        share_lan = bool(shared) or data.get('deployment_profile') == 'appliance'
        data.setdefault('lan_sharing_key', 'lan' if share_lan else '')
        # An explicit namespace list, never "*": kustomize strips the quotes
        # around a substituted scalar, and a bare `*` is a YAML alias, so the
        # whole manifest fails to parse after substitution. Naming the two
        # namespaces is also the smaller permission.
        data.setdefault('lan_sharing_cross_namespace',
                        'network,mqtt' if share_lan else '')
        # Every address this cluster actually hands to a LoadBalancer, so the
        # pool can stop covering the customer's entire LAN. `cluster_api_addr`
        # is deliberately absent: it is a Talos VIP, not a Service.
        #
        # The wide pool is only disabled once there is something to replace it
        # with. An appliance declares no addresses at all — it discovers its one
        # address at runtime — so it keeps the wide pool until that lands.
        lb_addrs: list[str] = []
        for field in ('cluster_gateway_addr', 'cluster_dns_gateway_addr',
                      'cloudflare_gateway_addr'):
            if data.get(field):
                lb_addrs.append(str(data[field]))
        for extra, field in (('default/mqtt', 'mqtt_lb_ip'),
                             ('ingress-nginx/ingress-nginx', 'ingress_nginx_lb_ip'),
                             ('default/mariadb', 'mariadb_lb_ip'),
                             ('omni/omni', 'omni_udp_lb_ip')):
            if extra in (data.get('extras') or []) and data.get(field):
                lb_addrs.append(str(data[field]))
        seen: set[str] = set()
        addrs = [a for a in lb_addrs if not (a in seen or seen.add(a))]
        # There is exactly one pool per cluster. A second, narrower pool alongside
        # a wide one cannot work — being a subset it overlaps, and Cilium rejects
        # any overlap with PoolConflict whether or not the wide one is disabled.
        # So a cluster with nothing to enumerate writes out the whole node CIDR
        # here, which is what it was getting implicitly anyway.
        #
        # The appliance test comes FIRST, and the order is the whole fix for
        # ferry133/jg-cluster-template#10.
        #
        # It used to sit after `if addrs:` and was therefore unreachable exactly
        # when it mattered. `lan_shared_addr` back-fills cluster_gateway_addr and
        # cluster_dns_gateway_addr about eighty lines above, and those are two of
        # the three fields `addrs` is built from — so declaring the shared address
        # (which docs/operations/router-dns.md tells every appliance operator to
        # do before touching the router) silently populated `addrs` and took the
        # first branch. The result on jgt-appliance: a static `pool` holding
        # 10.9.1.254 overlapping lan-address-probe's `pool-discovered`
        # [10.9.1.254, 10.9.1.253], Cilium disabling the whole discovered pool
        # with PoolConflict=True, and .253 — the only address envoy-external can
        # use — ceasing to exist. Every LAN name in the cluster's domain went
        # NXDOMAIN while the same names answered fine over the public tunnel,
        # because cloudflared's origin is a ClusterIP and never needed the LB.
        #
        # An appliance discovers its addresses at runtime and lan-address-probe
        # owns allocating them, so the static pool must be empty on an appliance
        # unconditionally — whether or not the operator has since declared the
        # address he was told to declare.
        if data.get('deployment_profile') == 'appliance':
            blocks = []
        elif addrs:
            blocks = [{'start': a, 'stop': a} for a in addrs]
        else:
            blocks = [{'cidr': str(data.get('node_cidr'))}]
        data.setdefault('lb_pool_blocks',
                        json.dumps(blocks, separators=(',', ':')))
        # Whether local-path should claim the cluster-default StorageClass.
        # nfs-subdir claims it whenever it is running, and it only runs on an
        # NFS cluster, so the two never collide.
        data.setdefault(
            'local_path_is_default',
            'true' if data.get('storage_backend') != 'nfs' else 'false',
        )
        # Whether Longhorn is installed. `storage_backend: "replicated"` implies
        # it, but a NAS-backed cluster can ask for it too — the NAS is right for
        # bulk and wrong for a database, and Longhorn is the one block class that
        # does not pin the pod to a node. Those clusters cannot say so through
        # storage_backend, which also decides whether nfs-subdir runs.
        #
        # This is not db_storage_class: installing the tier and moving a database
        # onto it are separate, because storageClassName is immutable and moving
        # means dump and restore. Keeping them separate is what lets the install
        # be verified before anything depends on it.
        data.setdefault(
            'deploy_longhorn',
            bool(data['replicated_storage']) if 'replicated_storage' in data
            else data.get('storage_backend') == 'replicated')
        # Single-node clusters must not run components that require peers. The
        # node list is only authoritative on the manual path — the Omni path
        # always renders `nodes: []` — so an Omni cluster that is not an
        # appliance has to say so with `single_node`, or it is assumed to have
        # peers. Assuming wrongly here only costs a component that would have
        # worked; assuming the other way silently disables one that was needed.
        if 'single_node' in data:
            data.setdefault('is_single_node', bool(data['single_node']))
        elif data.get('deployment_profile') == 'appliance':
            data.setdefault('is_single_node', True)
        elif data.get('provisioning_path') == 'talos':
            data.setdefault('is_single_node', len(data.get('nodes') or []) <= 1)
        else:
            data.setdefault('is_single_node', False)
        data.setdefault('repository_branch', 'main')
        data.setdefault('repository_visibility', 'public')

        return data


    def filters(self) -> makejinja.plugin.Filters:
        return [
            basename,
            nthhost,
            b64encode,
        ]


    def functions(self) -> makejinja.plugin.Functions:
        return [
            age_key,
            cloudflare_tunnel_id,
            cloudflare_tunnel_secret,
            github_deploy_key,
            github_push_token,
            talos_patches,
        ]
