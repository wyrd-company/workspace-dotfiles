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

To rotate the token, from a workstation that can read and write `kv` in namespace `wyrwood`, in one shell so the
tokens stay in variables and out of history and process arguments. The server's list can hold other clients' tokens
too; these steps add and remove only the workspace token. The commands are for the homelab server.

1. Generate the new token and append it to the server's list, keeping every token already there:

   ```bash
   old=$(bao kv get -namespace=wyrwood -mount=kv -field=token workspace/seek)
   new=$(openssl rand -hex 32)
   list=$(bao kv get -namespace=wyrwood -mount=kv -field=SEEK_SERVER_TOKEN homelab/seek)
   printf '%s,%s' "$list" "$new" | bao kv patch -namespace=wyrwood -mount=kv homelab/seek SEEK_SERVER_TOKEN=-
   ```

   The server rereads its list on the first request after `server.secret-refresh-seconds` (300) have passed, so it
   can still refuse the new token for a while.

2. Check that the server accepts the new token before any workspace uses it. Repeat after a short wait until this
   search succeeds:

   ```bash
   SEEK_SERVER_URL=https://seek.internal SEEK_SERVER_TOKEN_VALUE=$new seek web exa "test"
   ```

   Name the server: without `SEEK_SERVER_URL`, a workstation with no client config calls providers directly and the
   search proves nothing.

3. Store the new token for workspaces, and confirm OpenBao now holds it. Stop here if either command fails or the
   check does not print `stored`: workspaces still use the old token, so it must stay on the server's list.

   ```bash
   printf '%s' "$new" | bao kv put -namespace=wyrwood -mount=kv workspace/seek token=-
   [ "$(bao kv get -namespace=wyrwood -mount=kv -field=token workspace/seek)" = "$new" ] && echo stored
   ```

4. From a workspace, run a search (see [Checking](#checking)). It must succeed before you go on. After step 3 it can
   only be using the new token.

5. Remove only the old workspace token from the server's list, keeping every other entry, then clear the shell's
   copies:

   ```bash
   list=$(bao kv get -namespace=wyrwood -mount=kv -field=SEEK_SERVER_TOKEN homelab/seek)
   printf '%s' "$list" |
     OLD=$old awk 'BEGIN { RS = ","; ORS = "" } $0 != ENVIRON["OLD"] { printf "%s%s", sep, $0; sep = "," }' |
     bao kv patch -namespace=wyrwood -mount=kv homelab/seek SEEK_SERVER_TOKEN=-
   unset old new list
   ```

A workspace reads `kv/workspace/seek` on every call, so it uses the new token from step 3 with no restart.

## Checking

```bash
seek config show       # server.url and server.token = vault, auth: none; reads no secret
seek web exa "test"    # one real search through the server
```

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
