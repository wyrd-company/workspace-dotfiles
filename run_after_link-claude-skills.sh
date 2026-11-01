#!/bin/sh
# Claude Code reads ~/.claude/skills/<name>, and accepts a symlink there. Link every
# skill in the shared clone (~/.agents/skills/<name>/SKILL.md) and prune links that
# point at skills no longer in the clone. Real folders are left alone.
set -e
shared="$HOME/.agents/skills"
claude="$HOME/.claude/skills"
[ -d "$shared" ] || exit 0
mkdir -p "$claude"
for dir in "$shared"/*/; do
  [ -f "$dir/SKILL.md" ] || continue
  name=$(basename "$dir")
  link="$claude/$name"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "link-claude-skills: $link exists and is not a symlink; skipping" >&2
    continue
  fi
  ln -sfn "$shared/$name" "$link"
done
for link in "$claude"/*; do
  [ -L "$link" ] || continue
  case "$(readlink "$link")" in
    "$shared"/*) [ -f "$link/SKILL.md" ] || rm -f "$link" ;;
  esac
done
