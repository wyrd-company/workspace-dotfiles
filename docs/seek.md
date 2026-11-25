# Seek

[Seek](https://wyrd.foo/docs/seek/) is the web search, research and scrape CLI, installed from `dot_Brewfile`. A
workspace holds no provider keys. It sends every call to a Seek server, which holds them, and proves itself with a
client token that it reads from OpenBao through the Wyrwood socket.

chezmoi writes `~/.config/seek/client.yml` from `dot_config/seek/client.yml.tmpl` and `.chezmoidata/seek.yml`:

- `url`: the Seek server, `https://seek.internal`. While it is empty, no config is written and `seek` calls providers
  with whatever local keys it finds.
- `token`: the KV v2 field that holds the workspace client token, `kv/workspace/seek`, field `token`. The path is
  relative to the namespace that the socket sets.

The token's `vault` block names the socket and `auth: none` itself. The socket adds the binding's login and namespace,
so seek sends no token of its own. Because the block is the token's own, an exported `BAO_ADDR`, `BAO_TOKEN` or
`BAO_NAMESPACE` does not change where the token is read. seek reads it only when a command calls the server.

This needs seek 0.4.0 or later. Older clients ignore `client.yml`.

## Onboarding

The Seek server's operator does this once, for all workspaces:

1. Generate the workspace client token and store it, from a workstation that can write to `kv` in namespace
   `wyrwood`. The pipe keeps the token out of shell history and process arguments:

   ```bash
   openssl rand -hex 32 | bao kv put -namespace=wyrwood -mount=kv workspace/seek token=-
   ```

2. Add the token to the tokens the server accepts. Seek's `server.tokens` is a comma-separated list. For the homelab
   server it is the field `SEEK_SERVER_TOKEN` of `kv/homelab/seek` (see the homelab repository's `docs/external.md`).
   The server reads it again within `server.secret-refresh-seconds` (300), with no restart.

3. In Wyrwood's interface, give the policy that every workspace binding selects (`workspace`):

   ```hcl
   path "kv/data/workspace/seek" {
     capabilities = ["read"]
   }
   ```

   This is the only Seek path a workspace can read. The server's own secret also holds the provider keys, so
   workspaces get their own token rather than read access to it.

To rotate the token, add the new token to the server's list, store it at `kv/workspace/seek`, then remove the old one
from the list.

## Checking

```bash
seek config show       # server.url and server.token = vault, auth: none; reads no secret
seek web exa "test"    # one real search through the server
```

Before step 3, a command that calls the server fails with
`server.token: vault GET /v1/kv/data/workspace/seek failed: HTTP 403`. If the token is stored but missing from the
server's list, the server answers `HTTP 401 ... missing or invalid seek server token`.

Check the rendering with `python3 -m unittest tests.test_seek`. The test that runs `seek config validate` is skipped
when the installed seek is older than 0.4.
