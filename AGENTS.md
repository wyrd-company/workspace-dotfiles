# Workspace dotfiles

This is the dotfiles I use for each devcontainer workspace account, targeting the `vscode` user.

Secrets come from OpenBao through the Wyrwood vault socket; the container holds no token or secret file. See `docs/vault.md`.

The AWS CLI is configured for Cloudflare R2, one profile per bucket, with keys read from OpenBao on each call. See `docs/aws-cli.md`.

Tools come from `dot_Brewfile`, `dot_npm-packages` and `dot_config/python/global-requirements.txt`, each installed by a
`run_onchange_` script. A tool whose only install is the vendor's `install.sh` goes in `.chezmoidata/install-scripts.yml`.
See `docs/install-scripts.md`.

chezmoi keeps one block in `~/.bashrc` and `~/.zshrc` that sources `~/.config/shell/rc.d/*.sh`; shell integration for a
tool goes there. The rest of those files is left alone. See `docs/shell.md`.

## Git identity (operators)

Devcontainers are shared by several humans, and every commit and push must name the operator who asked for it.
Operators are declared in `.chezmoidata/operators.yml`; `run_onchange_after_git-operators.sh.tmpl` renders a
`git-<handle>` wrapper, an operator env file and the GitHub .pub for each.

`~/.local/bin/git` is a shim in front of the real git. It is the one place that applies an identity (name, email
chosen by the GitHub owner of `origin`, and the SSH key in the forwarded ssh-agent), and it picks the operator from:

1. `GIT_OPERATOR`: set by `git <handle> ...` (`git-as`), for human terminals, or to `automation` by Dagu's base
   config, which runs `git automation` as `wyrd-automation[bot]`.
2. The T3 thread's registration: agent threads run `git operator set <handle>` once, with the handle the user
   gave, and plain `git` (including scripts and hooks) then runs as that operator. The registry is keyed by
   `T3CODE_THREAD_ID` under `~/.local/state/git-operators/`, with an append-only `log`. A thread started by
   another agent copies the starting thread's registration: `git operator set --from <thread-id>`.
3. Neither: commit creation and pushes stop in both terminals and T3 threads, even if a tool has added a
   global Git identity. A thread asks the user to register; a terminal asks for `git <handle> <command>`.

Inside a T3 thread, `GIT_OPERATOR=automation` and a `git <handle>` that differs from the registration are refused.
The requirement includes indirect commit creation (`merge`, `pull`, `rebase`, `cherry-pick`, `revert`, `am`,
stash creation, notes writes, history rewriting and commit-writing plumbing), and pushes over SSH, HTTPS and
local transports. Aliases are expanded before classification, and shell aliases and repository iterators
route nested Git calls through the shim. Selected operators supply the committer and SSH key even if stale
environment variables or command-line config name someone else; original authors can still be preserved.

Everything else needs no operator: fetch, clone, ls-remote, tags, branches, worktree management, inspection,
stash application/removal and explicit recovery modes. `merge --ff-only`, `pull --ff-only`,
`merge --no-commit`, `cherry-pick/revert --no-commit` and `commit --dry-run` are also allowed when no option
reenables commit creation. `pull --no-commit` still needs an operator because configuration may select a rebase.
`core.sshCommand = ~/.local/bin/git-ssh-guard` permits SSH reads through the forwarded agent and rejects
anonymous receive-pack calls. Private repository access still depends on the available credentials.
No git hooks are involved, so repo hooks (lefthook) keep working.
The private keys come from the forwarded ssh-agent (wyrwood), which holds every operator's key.
Automation (workspace-ansible, Dagu, project-template hooks) commits as `wyrd-automation[bot]` through
`git automation`; it is not for interactive use.

This is a policy for the workspace's Git entry points, not a security sandbox against arbitrary executable
code or explicitly invoking a different Git binary. Test it with `python3 -m unittest discover -s tests`;
the Git tests use isolated homes, local repositories and fake SSH, without real credentials or network access.

## Harness config the harness also writes

Root-owned configuration belongs to workspace-ansible; user-owned configuration belongs here.
Prefer `/etc` for common settings when the application supports it; otherwise use dotfiles.

Codex rewrites `~/.codex/config.toml` itself (hook trust, plugins, the model, `/statusline`), so chezmoi never owns
it. `dot_codex/modify_private_config.toml` is a modify template: it sets only its listed keys (`notice`, `tui`),
only when one is missing or differs, and otherwise passes the file through unchanged. The model is the user's.
System-wide Codex and Claude Code settings (the Xolotl provider, the plugin marketplace, the git-operator hook) are
in `/etc`, rendered by workspace-ansible.

Claude Code's `~/.claude.json` is also written by the client. `modify_private_dot_claude.json`
sets only the required Xolotl MCP connection keys, preserving other settings and passing an
unchanged file through byte for byte. It reads the URL from `/etc/workspace/config.yml`;
the shared header helper is installed by workspace-ansible.
