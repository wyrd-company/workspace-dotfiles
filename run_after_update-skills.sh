#!/bin/sh
# Runs on every apply. Brings the shared skills clone (~/.agents/skills) up to date,
# then links each skill into ~/.claude/skills, where Claude Code reads them.
set -e
shared="$HOME/.agents/skills"
claude="$HOME/.claude/skills"
[ -d "$shared" ] || exit 0

# Update only a clean checkout of main, and only by fast-forward, so a branch or
# uncommitted work in the clone is never disturbed. A failed pull (no network)
# keeps the current copy and does not fail the apply.
if [ -d "$shared/.git" ]; then
  branch=$(git -C "$shared" symbolic-ref --quiet --short HEAD || true)
  if [ "$branch" != main ]; then
    echo "update-skills: $shared is on '${branch:-a detached head}', not main; not updating" >&2
  elif [ -n "$(git -C "$shared" status --porcelain)" ]; then
    echo "update-skills: $shared has uncommitted changes; not updating" >&2
  else
    git -C "$shared" pull --ff-only --quiet ||
      echo "update-skills: could not update $shared; keeping the current copy" >&2
  fi
fi

# A link from ~/.claude/skills to the whole clone would leave no room for skills
# that only Claude Code has. Replace it with a folder of per-skill links.
if [ -L "$claude" ] && [ "$(readlink -f "$claude")" = "$(readlink -f "$shared")" ]; then
  rm "$claude"
fi
mkdir -p "$claude"

# Link every skill in the clone (<name>/SKILL.md) and prune links that point at
# skills no longer in it. Real folders are left alone.
for dir in "$shared"/*/; do
  [ -f "$dir/SKILL.md" ] || continue
  name=$(basename "$dir")
  link="$claude/$name"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "update-skills: $link exists and is not a symlink; skipping" >&2
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
