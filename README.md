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
