# Boat

[Boat](https://boat.dev) is installed by its vendor's install script, through `.chezmoidata/install-scripts.yml`
(see [install-scripts.md](install-scripts.md)), to `~/.ascii/bin/boat`.

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
