# Antigravity

The [Antigravity CLI](https://antigravity.google/product/cli) (`agy`) is installed by the `antigravity-cli`
devcontainer feature. It signs in with a personal Google subscription, once, and keeps the OAuth token in
`~/.gemini`, a workspace mount (`state/antigravity`). It does not use Xolotl: the gateway mode cannot carry
subscription traffic.

## What the dotfiles set

| Path | Purpose |
| --- | --- |
| `~/.gemini/AGENTS.md` | Core instructions, with the `wyrd-gemini[bot]` `gh` identity. `agy` sets `ANTIGRAVITY_AGENT=1`, which the `gh` shim reads. |
| `~/.gemini/config/mcp_config.json` | The mnemonic MCP server, run from the Wyrd marketplace checkout. |
| `~/.gemini/config/hooks.json` | A `SessionStart` hook, `~/.local/bin/agy-git-operator-hook`: it wraps the git-operator script, whose plain text Antigravity needs as `{"injectSteps": [{"userMessage": ...}]}`. |
| `~/.gemini/config/skills` | A link to the published skills at `~/.agents/skills`. |

`mcp_config.json` and `hooks.json` are modify templates, like `~/.claude.json`: chezmoi sets only its own
`mnemonic` server and `wyrd` hook group and keeps everything else, such as servers added with `agy mcp add`.

The sign-in, `settings.json` and conversations are the client's own and chezmoi does not touch them.

## T3 Code's Antigravity provider

T3 runs its own copy of the same binary with a separate profile at
`~/.t3/userdata/providers/antigravity/<hash>/`, a stand-in for `~/.gemini`, and its own sign-in.
`run_after_link-antigravity-t3-profile.sh` links `AGENTS.md`, `config/mcp_config.json`, `config/hooks.json` and
`config/skills` of each profile to the ones in `~/.gemini`, so both clients share one setup. T3's `config/config.json`,
`config/projects` and sign-in stay its own. The script replaces an empty file the provider created and leaves any
other real file where it is.

## Not covered

- Xolotl's MCP gateway: a remote MCP server in `mcp_config.json` takes only static `headers`, with no helper that
  reads the key through Wyrwood. A stdio bridge would be needed.
- Environment for the mnemonic server: the file passes the Vault socket, CA and SSH agent paths. Antigravity does not
  document whether a stdio server inherits the rest, such as `T3CODE_THREAD_ID`.
