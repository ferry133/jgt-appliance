# age.key escrow

`age.key` is the only thing that can read this cluster's backups. They are
encrypted to the cluster's own public key, which is what keeps them private from
whoever owns the R2 account — and what makes the key irreplaceable.

On a single-node appliance the key lives on the one disk whose failure the
backups exist to survive. **An unescrowed key means the off-site backups are
ciphertext nobody can open**, which is worse than having none, because it looks
like protection right up until the morning it is needed.

Validation refuses to render an appliance until `age_key_escrowed: true` is set
in `cluster.yaml`. That field is not defaulted: it has to be written by whoever
did the escrow, for the same reason `accept_node_pinning` is not defaulted.

## What to escrow

| | |
|---|---|
| `age.key` | the private key; without it nothing else here matters |
| `cluster.yaml` | not secret-free — holds Cloudflare and R2 credentials |
| `kubeconfig` / `kubeconfig-sa` | cluster access, replaceable but slow to rebuild |

The per-user repository does **not** need escrowing: it is on GitHub, and it
holds only what is already encrypted with the same key.

## Where

Somewhere that survives the appliance and is not the appliance:

- a password manager entry on the operator's account, or
- an encrypted archive in a location independent of the R2 bucket

Do not put it in the same R2 bucket as the backups. Any store that fails or is
lost together with the thing it protects is not a second copy.

## Verifying the escrow before declaring it

Restore-test the copy, not the original. An escrowed key that was truncated on
the way in reads exactly like one that works:

```sh
# from the escrowed copy, not from the cluster
age-keygen -y escrowed-age.key
```

It must print the same public key as the `age:` line in `.sops.yaml`. If it does
not, the escrow is wrong and `age_key_escrowed: true` would be a false
statement.

## Handover

Handing the cluster to the customer means handing over `age.key`. From that
moment the operator's copy is a second key to someone else's data — either
destroy it, or say plainly that it still exists. "The customer can take the keys
back" only means something if the operator's copy is accounted for.
