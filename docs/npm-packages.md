# npm packages

`dot_npm-packages` lists the global npm packages, one per line. Add or remove a line, then `chezmoi apply`.

The devcontainer sets `NPM_CONFIG_PREFIX=~/.npm-global`, so `npm install -g` puts commands in `~/.npm-global/bin`.
That directory is not on `PATH`, and is left off on purpose: editing `PATH` in `devcontainer.json` overrides what
devcontainer features add to it. `~/.local/bin` is on `PATH` for login shells, scripts and agents, so commands are
linked there instead.

## How it runs

1. `run_onchange_dot_npm-packages.sh.tmpl` runs `npm install -g` with the list whenever `dot_npm-packages` or the
   script changes. npm 11 skips package install scripts unless the package is in `--allow-scripts`; add a package to
   that flag when it needs its `postinstall` (npm warns `install-scripts ... not yet covered by allowScripts`).
2. `run_after_npm-bins.sh` runs on every apply. For each listed package it reads the `bin` field of its
   `package.json` and links each command into `~/.local/bin`, pointing at `~/.npm-global/bin/<command>`. It removes
   links into `~/.npm-global/bin` for commands no longer listed. A file or another link already in `~/.local/bin`
   (such as the `gh` and `git` shims) is left alone with a warning. A listed package that is not installed fails the
   run after the rest are linked.

Removing a package does not uninstall it: `~/.npm-global` is a bind mount shared with other workspaces, which may
still use it. Only its links go.

Tests: `python3 -m unittest tests.test_npm_bins`.
