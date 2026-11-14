#!/bin/bash
# Runs on every apply: installs missing extensions and upgrades the rest.
# ~/.local/share/gh/extensions is a shared cache mount, so most runs only upgrade.
# gh-vault-agent-app-token is installed by workspace-ansible: the gh shim needs it
# to mint the token these calls use.
set -e
# An agent's calls go through the gh shim, which mints its GitHub App token for the
# owner of a repository and stops when it has none, as from the home directory where
# chezmoi runs this. Name this repository so agents use their app. A human's calls
# pass through the shim and use their own gh login; extension commands ignore GH_REPO.
export GH_REPO="${GH_REPO:-wyrd-company/workspace-dotfiles}"
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
