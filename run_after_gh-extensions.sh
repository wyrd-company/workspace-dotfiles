#!/bin/bash
# Runs on every apply: installs missing extensions and upgrades the rest.
# ~/.local/share/gh/extensions is a shared cache mount, so most runs only upgrade.
# gh-vault-agent-app-token is installed by workspace-ansible: the gh shim needs it
# to mint the token these calls use.
set -e
gh="$HOME/.local/bin/gh"
dir="$HOME/.local/share/gh/extensions"
for ext in \
  yuler/gh-download \
  seachicken/gh-poi \
  agynio/gh-pr-review \
  github/gh-stack
do
  name=${ext#*/}
  if [ -d "$dir/$name" ]; then
    "$gh" extension upgrade "$name" || echo "gh-extensions: could not upgrade $name; keeping the installed version" >&2
  else
    "$gh" extension install "$ext"
  fi
done
