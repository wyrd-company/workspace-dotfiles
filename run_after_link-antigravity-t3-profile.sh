#!/bin/bash
# Runs on every apply: T3 Code's Antigravity provider keeps its own profile, a stand-in for ~/.gemini at
# ~/.t3/userdata/providers/antigravity/<hash>/, so its sessions would miss the instructions, MCP servers, hooks and
# skills in ~/.gemini. Links those into each profile. Only these entries are shared: the profile's own
# config/config.json, config/projects and sign-in stay T3's. Does not replace a real file or directory.
# See docs/antigravity.md.
set -uo pipefail

gemini="$HOME/.gemini"
profiles="$HOME/.t3/userdata/providers/antigravity"
[ -d "$profiles" ] || exit 0

link() { # link <target> <name>: make <name> a link to <target> unless <name> is a real file or directory
  local target=$1 name=$2
  [ -e "$target" ] || [ -L "$target" ] || return 0
  if [ -L "$name" ]; then
    [ "$(readlink "$name")" = "$target" ] && return 0
    rm -f "$name"
  elif [ -e "$name" ]; then
    # An empty file the provider created at first start is safe to replace; anything else is the user's.
    [ -f "$name" ] && [ ! -s "$name" ] || { echo "antigravity: $name exists; leaving it" >&2; return 0; }
    rm -f "$name"
  fi
  ln -s "$target" "$name"
}

for profile in "$profiles"/*/; do
  profile=${profile%/}
  [ -d "$profile/config" ] || continue
  link "$gemini/AGENTS.md" "$profile/AGENTS.md"
  for entry in mcp_config.json hooks.json skills; do
    link "$gemini/config/$entry" "$profile/config/$entry"
  done
done
