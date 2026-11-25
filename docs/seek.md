# Seek

[Seek](https://wyrd.foo/docs/seek/) is the web search, research and scrape CLI, installed from `dot_Brewfile`. A
workspace holds no provider keys. It sends every call to a Seek server, which holds them, and proves itself with a
client token that it reads from OpenBao through the Wyrwood socket.

chezmoi writes `~/.config/seek/client.yml` from `dot_config/seek/client.yml.tmpl` and `.chezmoidata/seek.yml`:

- `url`: the Seek server, `https://seek.internal`. While it is empty, no config is written. See
  [Direct mode](#direct-mode) to stop using a server after the file exists.
- `token`: the KV v2 field that holds the workspace client token, `kv/workspace/seek`, field `token`. The path is
  relative to the namespace that the socket sets.

The token's `vault` block names the socket, `auth: none` and `namespace: ""` itself. The socket adds the binding's login
and namespace, so seek sends neither. No exported variable overrides a source's own block, so an exported `BAO_ADDR`,
`BAO_TOKEN` or `BAO_NAMESPACE` changes neither where the token is read nor what seek sends. seek reads the token only
when a command calls the server.

This needs seek 0.4.0 or later: older clients ignore `client.yml`. `brew bundle` leaves an installed seek alone, so
`run_onchange_after_seek-cli.sh` runs `brew upgrade wyrd-company/tools/seek-cli` once when the installed seek is older.
Check with `seek --version`.

## Onboarding

The Seek server's operator does this once, for all workspaces:

1. Generate the workspace client token and store it, from a workstation that can write to `kv` in namespace
   `wyrwood`. The pipe keeps the token out of shell history and process arguments:

   ```bash
   openssl rand -hex 32 | bao kv put -namespace=wyrwood -mount=kv workspace/seek token=-
   ```

2. Add the token to the tokens the server accepts, keeping the tokens already there. Seek's `server.tokens` is a
   comma-separated list. For the homelab server it is the field `SEEK_SERVER_TOKEN` of `kv/homelab/seek` (see the
   homelab repository's `docs/external.md`). The server rereads the list on a request once
   `server.secret-refresh-seconds` (300) have passed, with no restart, so retry a search until it is accepted.

3. In Wyrwood's interface, give the policy that every workspace binding selects (`workspace`):

   ```hcl
   path "kv/data/workspace/seek" {
     capabilities = ["read"]
   }
   ```

   This is the only Seek path a workspace can read. The server's own secret also holds the provider keys, so
   workspaces get their own token rather than read access to it.

To rotate the token, change one place at a time so workspaces always hold a token the server accepts:

1. Add the new token to the server's list, keeping every token already there.
2. Wait until the server accepts it: a search that names the server (`SEEK_SERVER_URL`) and the new token
   (`SEEK_SERVER_TOKEN_VALUE`) succeeds.
3. Store it at `kv/workspace/seek`, and read it back to confirm.
4. Run a workspace search, as in [Checking](#checking).
5. Remove the old token from the server's list, and only that one.

## Checking

```bash
seek config show       # server.url and server.token = vault, auth: none; reads no secret
seek web exa "test"    # one real search through the server
```

`seek config show` names where each setting came from. If `server.url` or `server.token` comes from an environment
variable rather than `client.yml`, the search does not test this configuration: unset `SEEK_SERVER_URL`,
`SEEK_SERVER_TOKEN_VALUE` and the other `SEEK_SERVER_TOKEN_*` variables first.

Before onboarding step 3, a command that calls the server fails with
`server.token: vault GET /v1/kv/data/workspace/seek failed: HTTP 403`. If the token is stored but missing from the
server's list, the server answers `HTTP 401 ... missing or invalid seek server token`.

## Direct mode

To have seek call providers with local keys instead of the server, set `seek.url` to `""` in
`.chezmoidata/zz-fork/seek.yml` (see `docs/fork-overlay.md`). chezmoi then stops managing `~/.config/seek` but leaves
the file it wrote, so remove it once: `rm ~/.config/seek/client.yml`. `SEEK_SERVER_URL` also selects server mode, so
unset it where your shell exports it. Then configure the provider keys as seek's
[credentials guide](https://wyrd.foo/docs/seek/credentials/) says, and check with `seek config show` that
`server.url` is unset.

## Tests

Check the rendering with `python3 -m unittest tests.test_seek`. The tests that run seek are skipped when the
installed seek is older than 0.4. One runs seek against a synthetic Unix-socket KV server with `BAO_*` exported for
another server, and checks that the socket gets no login or namespace header.
