# Workspace dotfiles

This is the dotfiles I use for each devcontainer workspace account, targeting the `vscode` user.

Secrets come from OpenBao through the Wyrwood vault socket; the container holds no token or secret file. See `docs/vault.md`.

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
3. Neither: a T3 thread with no registration stops at the first command that needs an identity and says to
   ask the user. Outside a thread git passes through unchanged.

Inside a T3 thread, `GIT_OPERATOR=automation` and a `git <handle>` that differs from the registration are refused.
With no operator, bare `git commit` fails (`user.useConfigOnly`) and bare SSH git operations are refused by
`core.sshCommand = ~/.local/bin/git-ssh-guard`. No git hooks are involved, so repo hooks (lefthook) keep working.
The private keys come from the forwarded ssh-agent (wyrwood), which holds every operator's key.
Automation (workspace-ansible, Dagu, project-template hooks) commits as `wyrd-automation[bot]` through
`git automation`; it is not for interactive use.
