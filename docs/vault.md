# Vault

Private data comes from OpenBao through the Wyrwood socket (`BAO_ADDR`). The container holds no token; the Wyrwood agent adds the token of the policies bound to the container.

Everything is in the `wyrwood` namespace, which Wyrwood shares with Xolotl. The socket sets the namespace from the binding, so paths inside the container are namespace-relative, like every path below. On the OpenBao server, pass `-namespace=wyrwood`: without it a write lands in the root namespace, where no container looks. The policies are in that namespace too.

chezmoi reads OpenBao with its `vault` template function, which runs `bao kv get -format=json <path>` (see `.chezmoi.yaml.tmpl`). KV v2 fields are under `.data.data` in the result.

## Operator emails

`.chezmoidata/operators.yml` holds each operator's handle, name, and GitHub public key. Their emails are kept out of the repository in OpenBao at `kv/workspace/operators/<handle>`, one field per GitHub owner:

- `default`: used when the `origin` remote's owner has no field of its own
- `<github-owner>`: used for repositories owned by that user or organization, for example `wyrd-company`

### Writing

On the OpenBao server, with a token that can write to `kv` in the `wyrwood` namespace:

```bash
# Check kv is mounted as KV v2: Options should show map[version:2]
bao secrets list -namespace=wyrwood -detailed | grep '^kv/'

bao kv put -namespace=wyrwood kv/workspace/operators/<handle> \
  default='<email>' \
  <github-owner>='<email>'

bao kv get -namespace=wyrwood kv/workspace/operators/<handle>
```

Add an owner to an existing operator with `bao kv patch -namespace=wyrwood kv/workspace/operators/<handle> <github-owner>='<email>'`. A new operator also needs an entry in `.chezmoidata/operators.yml`.

### Policy

Every workspace binding must select a Wyrwood policy with:

```hcl
path "kv/data/workspace/operators/*" {
  capabilities = ["read"]
}
```

KV v2 ACL paths include `data/`; the `bao kv` and chezmoi paths do not. No `sys/internal/ui/mounts` grant is needed: OpenBao answers the KV version lookup for tokens with a capability inside the mount.

## GitHub App tokens

`gh vault-agent-app-token` (configured in `dot_config/gh-vault-agent-app-token/config.yml`) mints GitHub App installation tokens by signing the App JWT with an OpenBao Transit key. The `gh` shim (`dot_local/bin/executable_gh`) calls it when `GH_LOGIN` or an agent harness marker is set.

Automation (workspace-ansible, Dagu, and `git automation`, which project-template hooks use) uses git over HTTPS as `wyrd-automation[bot]`, with this as its credential helper; humans and agents use SSH through `git <handle>`. Every workspace binding must select a Wyrwood policy with:

```hcl
path "transit/sign/gh-app-wyrd-automation" {
  capabilities = ["update"]
}
```

Each agent App in the config (`wyrd-claude[bot]`, `wyrd-codex[bot]`, `wyrd-pi[bot]`, `wyrd-grok[bot]`) needs the same grant on its own `transit/sign/<transit_key>` for agent sessions to mint tokens.

## ntfy

Dagu notifies through public [ntfy.sh](https://ntfy.sh), where anyone who knows a topic can read it, so the topic is a secret. It is at `kv/workspace/ntfy`, field `topic`, and `base.yml` in workspace-ansible gives it to every workflow as `NTFY_TOPIC`.

```bash
# Prompts without echo, so the topic stays out of shell history; printf adds no newline (topic=- keeps one)
read -rsp 'ntfy topic: ' topic; echo
printf %s "$topic" | bao kv put -namespace=wyrwood kv/workspace/ntfy topic=-
unset topic
```

Every workspace binding must select a Wyrwood policy with:

```hcl
path "kv/data/workspace/ntfy" {
  capabilities = ["read"]
}
```
