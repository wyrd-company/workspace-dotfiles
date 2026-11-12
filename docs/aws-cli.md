# AWS CLI (Cloudflare R2)

The AWS CLI (`awscli` in `dot_Brewfile`) is set up for Cloudflare R2's S3 API, with one profile per bucket:

| Profile              | Bucket               | Access                                       |
| -------------------- | -------------------- | -------------------------------------------- |
| `assets-wyrd-foo`    | `assets-wyrd-foo`    | Public, served at `https://assets.wyrd.foo/` |
| `workspace-archives` | `workspace-archives` | Private, for archiving                       |

Uploads to the public bucket are how agents attach images to issues and pull requests. `gh --attach` does not work
with the GitHub App tokens agents use: the upload endpoint answers 404 to installation tokens
([cli/cli#14309](https://github.com/cli/cli/issues/14309)).

## How it fits together

- `.chezmoidata/r2.yml` lists the buckets. Nothing in it is secret.
- `private_dot_aws/private_config.tmpl` renders `~/.aws/config` (mode 0600, in a 0700 `~/.aws`). It reads the Cloudflare account ID from OpenBao
  when chezmoi applies, so the account ID stays out of this public repository. The account ID is shared through a
  `[services r2]` section that sets the S3 endpoint, and each bucket gets a profile that uses it.
- Each profile's `credential_process` is `~/.local/bin/aws-bao-credentials kv/workspace/r2/buckets/<bucket>`. It reads
  the bucket's S3 key from OpenBao through the Wyrwood socket on every AWS CLI call. Nothing is written to disk, and
  there is no `~/.aws/credentials`.
- `request_checksum_calculation` and `response_checksum_validation` are `when_required`, because R2 does not accept
  every checksum newer AWS CLI versions send by default.

chezmoi owns `~/.aws/config`; do not run `aws configure`, which would write to it.

Each bucket has its own R2 token and its own OpenBao secret, so a binding can be given one bucket without the
other. For example, a workspace can be allowed to publish assets but not read the archives.

## Setup

Run these in order. Paths are namespace-relative, as in [vault.md](vault.md): pass `-namespace=wyrwood` on the
OpenBao server.

### 1. Cloudflare

1. **Account ID.** In the Cloudflare dashboard, open **R2 Object Storage**. **Account Details** shows the
   **Account ID**, and the S3 API endpoint is `https://<account-id>.r2.cloudflarestorage.com`.
2. **Buckets.**
   - `assets-wyrd-foo` is public. Under the bucket's **Settings → Custom Domains**, connect `assets.wyrd.foo`.
   - `workspace-archives` is private. Create it, and leave **Public Development URL** disabled and add no custom
     domain.
3. **One API token per bucket.** In **R2 Object Storage → Manage API tokens**, choose **Create Account API token**
   for each bucket:
   - **Permissions**: **Object Read & Write**.
   - **Specify bucket(s)**: **Apply to specific buckets only**, with only that bucket.
   - Name it after the bucket, for example `workspace assets-wyrd-foo`.

   Copy the **Access Key ID** and **Secret Access Key**. Cloudflare shows the secret only once.

### 2. OpenBao

Use **Wyrwood → OpenBao UI** in the `wyrwood` namespace and the `kv` engine, or the CLI on the OpenBao server with a
token that can write to `kv` in the `wyrwood` namespace.

| Path                                  | Fields                                |
| ------------------------------------- | ------------------------------------- |
| `kv/workspace/r2/account`             | `account_id`                          |
| `kv/workspace/r2/buckets/<bucket>`    | `access_key_id`, `secret_access_key`  |

```bash
bao kv put -namespace=wyrwood kv/workspace/r2/account account_id='<account-id>'

# Once per bucket. Prompts without echo, so the key stays out of shell history.
bucket=assets-wyrd-foo   # then workspace-archives
read -rp  'Access Key ID: ' access_key_id
read -rsp 'Secret Access Key: ' secret_access_key; echo
printf %s "$secret_access_key" | bao kv put -namespace=wyrwood "kv/workspace/r2/buckets/$bucket" \
  access_key_id="$access_key_id" secret_access_key=-
unset access_key_id secret_access_key

bao kv get -namespace=wyrwood -field=access_key_id "kv/workspace/r2/buckets/$bucket"
```

### 3. Wyrwood

`chezmoi apply` reads `kv/workspace/r2/account` to render `~/.aws/config`, and a read it is denied stops the whole
apply. **Every workspace binding must select a policy with this grant before this config reaches it**:

```hcl
path "kv/data/workspace/r2/account" {
  capabilities = ["read"]
}
```

Add it to a policy every workspace binding already selects, as for `kv/data/workspace/operators/*`.

Grant bucket keys only to bindings that should use them. Create one policy per bucket in **Wyrwood → Policies** and
choose **Save and validate**:

```yaml
name: r2-assets-wyrd-foo
openbao:
  agent-token-renewal: true
  policy: |
    path "kv/data/workspace/r2/buckets/assets-wyrd-foo" { capabilities = ["read"] }
```

```yaml
name: r2-workspace-archives
openbao:
  agent-token-renewal: true
  policy: |
    path "kv/data/workspace/r2/buckets/workspace-archives" { capabilities = ["read"] }
```

Then select them on each binding that needs them, alongside the policies it already has. Changing a binding's
policies gives the agent a new token and revokes the old one. KV v2 ACL paths include `data/`; the `bao kv` paths do
not. No list or write grants are needed.

### 4. Apply and check

```bash
chezmoi apply
aws --profile assets-wyrd-foo s3 ls s3://assets-wyrd-foo
aws --profile workspace-archives s3 ls s3://workspace-archives
```

## Usage

```bash
# Public asset: the object key is the URL path under https://assets.wyrd.foo/
aws --profile assets-wyrd-foo s3 cp ./login.png s3://assets-wyrd-foo/<repo>/<pr>/login.png
# Embed in markdown: ![Login error state](https://assets.wyrd.foo/<repo>/<pr>/login.png)

# Private archive
aws --profile workspace-archives s3 cp ./run.tar.zst s3://workspace-archives/<path>/run.tar.zst
aws --profile workspace-archives s3 cp s3://workspace-archives/<path>/run.tar.zst .
```

`aws s3 cp` sets `Content-Type` from the file extension, which the custom domain serves. Everything in
`assets-wyrd-foo` is public, so never upload secrets, logs with credentials, or private data there.

## Adding a bucket

1. Create the bucket and its token in Cloudflare (step 1).
2. Store the key at `kv/workspace/r2/buckets/<bucket>` (step 2).
3. Create an `r2-<bucket>` policy and select it on the bindings that need it (step 3).
4. Add the bucket to `.chezmoidata/r2.yml`. Its name is also its profile name.

## Rotating a key

Create a new token for the bucket in Cloudflare and `bao kv put` it over the old one. The next AWS CLI call uses it,
since nothing is cached. Then delete the old token in Cloudflare.

## Troubleshooting

- `aws-bao-credentials: Cannot read kv/workspace/r2/buckets/<bucket> through Wyrwood`: the binding has no policy
  for that bucket, or the secret is missing. Fix the Wyrwood policy; do not log in or put a key in the container.
- `chezmoi apply` fails on `kv/workspace/r2/account`: the binding lacks the account grant from step 3.
- `must contain nonempty access_key_id and secret_access_key strings`: the secret's fields are misnamed or empty.
- `AccessDenied` from R2: the token is not scoped to that bucket, or lacks **Object Read & Write**.
