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

## Pushover

`pushover` requires an explicit recipient and reads that recipient's credentials
at `kv/workspace/pushover/<recipient>` using `bao kv get` through the Wyrwood
socket in `BAO_ADDR`. Recipient names use operator handles:

Each KV v2 secret has two string fields:

- `user_key`: the destination Pushover user or group key
- `app_token`: the application API token to use when notifying this recipient

Secrets are in the `wyrwood` namespace; the container uses namespace-relative
paths. The CLI discovers supported recipients by listing direct child secrets
under `kv/workspace/pushover`; names must start with a letter or digit and
contain only letters, digits, underscores, or hyphens. New recipients need no
script change. One credential read per notification keeps both fields at the
same KV version and applies rotation to the next notification. Envconsul's
process supervision is unnecessary for this one-shot command. The script
requires `bao`, `jq`, and `curl`.

### Provisioning

In Wyrwood, open **OpenBao UI** and sign in. Confirm the namespace is `wyrwood`,
open the `kv` secrets engine, and create `workspace/pushover/<recipient>` with
the fields above. The user key is on the recipient's Pushover dashboard; create
a Pushover application such as **Workspace notifications** to obtain an
application API token.

In **Wyrwood → Policies**, edit a policy selected by each workspace binding
that should send notifications. Add the following grant, preserving the other
grants, then choose **Save and validate**:

```hcl
path "kv/data/workspace/pushover/*" {
  capabilities = ["read"]
}
path "kv/metadata/workspace/pushover" {
  capabilities = ["list"]
}
```

Wyrwood propagates the policy change to its bindings. KV v2 ACL paths include
`data/`; the `bao kv get` path does not. Recipient discovery needs `list` on
the exact parent metadata path; it does not require reading metadata or listing
other directories. The container needs no write or token-management permissions.
A `403` means the bound policy does not grant the requested path; update the
Wyrwood policy rather than logging in or supplying a token inside the container.

### Usage

```bash
pushover --list-recipients
pushover --recipient <operator> --title 'Build complete' --message 'All checks passed.'
pushover --recipient <operator> --message 'The review is ready.'
```

Omitting `--recipient` lists the supported recipients and exits with an error,
without sending anything. Unsupported recipients also fail with the list. No
recipient is inferred from the current Git operator or container account.
`--list-recipients` lists names and exits successfully without sending.

`--user` and `--token` override the respective fields; supplying both skips the
credential read, but still requires a supported recipient. `PUSHOVER_SECRET_ROOT`
selects another namespace-relative directory with the same per-recipient layout
and corresponding grants. It replaces the old `PUSHOVER_SECRET_PATH` setting;
there is no single-secret override. Help and version do not access OpenBao.
`--quiet` suppresses output, including recipient lists, while retaining exit
status for callers.

Credentials are never written to `~/.pushover/config`, and the old `--config`
flow is replaced by OpenBao provisioning above. Remove any old local credential
file after migration. Update this chezmoi-managed script through
workspace-dotfiles; the upstream `--upgrade` installer would replace the
Wyrwood integration and is disabled.

## Cloudflare R2 (AWS CLI)

The AWS CLI profiles read the Cloudflare account ID at `kv/workspace/r2/account` (when chezmoi applies) and each
bucket's S3 key at `kv/workspace/r2/buckets/<bucket>` (on every call). Every workspace binding needs `read` on
`kv/data/workspace/r2/account`; bucket keys are granted per binding. See [aws-cli.md](aws-cli.md) for the
Cloudflare, OpenBao and Wyrwood steps.

## Boat

The `boat` wrapper reads the Boat API key at `kv/workspace/boat`, field `api_key`, on every call. See
[boat.md](boat.md) for creating the key, storing it, and the policy grant.
