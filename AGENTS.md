# Workspace dotfiles

This is the dotfiles I use for each devcontainer workspace account, targeting the `vscode` user.

Secrets come from OpenBao through the Wyrwood vault socket; the container holds no token or secret file. See `docs/vault.md`.

## Git identity (operators)

Devcontainers are shared by several humans. Every commit and push must name the operator: run git as
`git <handle> ...` (for example `git boblangley push`). Operators are declared in `.chezmoidata/operators.yml`;
`run_onchange_after_git-operators.sh.tmpl` renders a `git-<handle>` wrapper, an operator env file and the
GitHub .pub for each. Bare `git commit` fails (`user.useConfigOnly`) and bare SSH git operations are refused by
`core.sshCommand = ~/.local/bin/git-ssh-guard`. No git hooks are involved, so repo hooks (lefthook) keep working.
The private keys come from the forwarded ssh-agent (wyrwood), which holds every operator's key.
Automation (workspace-ansible, Dagu, project-template hooks) commits as `wyrd-automation[bot]` through
`git automation`; it is not for interactive use.
