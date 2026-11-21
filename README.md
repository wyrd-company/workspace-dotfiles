# workspace-dotfiles
Dotfiles for Wyrd Company workspaces

Root-owned configuration is managed by workspace-ansible; user-owned
configuration is managed here. Common settings go in `/etc` when supported by
the application. When an application requires a user configuration file,
dotfiles manages that file while preserving settings the application writes.

Claude Code's Xolotl MCP connection is added to `~/.claude.json` by a chezmoi
modify template. It reads `xolotl_url` from `/etc/workspace/config.yml` and uses
the `/usr/local/bin/xolotl-mcp-headers` helper installed by workspace-ansible.
The helper retrieves the workspace key through Wyrwood with `bao` at connection
time; no key is stored in the user configuration. Other servers, account state,
and optional Xolotl settings are preserved, and unchanged configuration passes
through byte for byte.

Claude's `managedMcpServers` setting rejects header helpers, and its exclusive
`managed-mcp.json` would disable plugin servers such as mnemonic. Codex supports
this connection in `/etc/codex/config.toml`, so that entry stays in Ansible.
Apply both repositories with `ansible-sync`, or run `chezmoi apply ~/.claude.json`
after the system helper is installed, then start a new Claude Code session.

T3 Code's `~/.t3/userdata/settings.json` is updated the same way. The workspace favorites, idle
and project-list preferences, and the Antigravity and Grok provider instances are merged in.
The rest of the file is left as T3 wrote it.

`skills sync` builds shared skills with workspace and project overlays and
maintains the Claude Code, Codex and Pi views. It also runs after every chezmoi
apply. See [Skills](docs/skills.md) for setup, migration, rollback and checks.

A fork overlays its own operators, data and instructions without editing upstream's files, in
`.chezmoidata/zz-fork/` and `.includes/fork/`. See [Fork overlay](docs/fork-overlay.md).
