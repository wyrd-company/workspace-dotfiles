# Boat

[Boat](https://boat.dev) is installed by its vendor's install script, through `.chezmoidata/install-scripts.yml`
(see [install-scripts.md](install-scripts.md)), to `~/.ascii/bin/boat`.

The vendor's script, and why the entry sets what it does:

- It ends by running `boat onboard`, an interactive sign-in, reading `/dev/tty` when it can. The two `sed`
  expressions replace both calls with `:`. The vendor suggests one, `s|"\$INSTALL_DIR/\$MODE" onboard|:|`, which
  leaves `: < /dev/tty` behind; with no terminal (Dagu, Ansible) opening `/dev/tty` fails and so does the script.
- With `$SHELL` set to bash or zsh it writes a PATH block and a `boat()` shell function into `~/.bashrc` or
  `~/.zshrc` (and `~/.zshenv` or `~/.profile`). The function calls `~/.ascii/bin/boat` directly, which would skip
  the API key wrapper below. `SHELL: /bin/sh` makes the script skip the rc files. The function's one extra, `boat
  new` exporting `BOAT_CURRENT_ID` into the calling shell, is lost; pass sandbox IDs explicitly.
- It links `~/.local/bin/boat` to the binary only when nothing else is there. chezmoi writes the wrapper first, so
  the link is never made. It also links `/usr/local/bin/boat` when that is writable by the user, which it is not in
  the workspaces.
- No `sha256`: the script changes with each release. It checks the binary it downloads against Boat's checksums.
- The binary updates itself (`--no-update` or `BOAT_NO_UPDATE=1` turns that off), so an unchanged entry is not
  reinstalled for upgrades.

## API key

`~/.local/bin/boat` (`dot_local/bin/executable_boat`) is a wrapper. It reads the API key from OpenBao on each call
and runs the real binary with it as `BOAT_API_KEY`, so the key is never in a config file and a rotation applies to
the next call. A `BOAT_API_KEY` already in the environment is used as is. The wrapper is a file on `PATH`, not a
shell alias, so agents, Dagu and scripts get the key too, not just interactive shells.

Create a key with `boat api-key create` (signed in, or on the dashboard); the secret is shown once. Store it on the
OpenBao server, in the `wyrwood` namespace (see [vault.md](vault.md)):

```bash
# Prompts without echo, so the key stays out of shell history; printf adds no newline (api_key=- keeps one)
read -rsp 'Boat API key: ' key; echo
printf %s "$key" | bao kv put -namespace=wyrwood kv/workspace/boat api_key=-
unset key
```

Every workspace binding that uses boat must select a Wyrwood policy with:

```hcl
path "kv/data/workspace/boat" {
  capabilities = ["read"]
}
```
