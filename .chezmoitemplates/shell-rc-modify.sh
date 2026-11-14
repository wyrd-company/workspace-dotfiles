#!/bin/bash
# chezmoi modify script for a shell startup file the user and installers also write. It owns two things
# and passes everything else through: see docs/shell.md.
#  - With add_block, keeps one block that sources ~/.config/shell/rc.sh, appended when missing.
# An unterminated block is left alone: removing to the end of the file would delete the user's settings.
set -euo pipefail
add_block={{ if .add_block }}1{{ else }}0{{ end }}
export BLOCK='# BEGIN workspace-dotfiles shell
# Managed by chezmoi (workspace-dotfiles): sources ~/.config/shell/rc.d/*.sh. See docs/shell.md.
if [ -r "$HOME/.config/shell/rc.sh" ]; then . "$HOME/.config/shell/rc.sh"; fi
# END workspace-dotfiles shell'

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
cat > "$dir/in"

# awk runs END after an exit in a rule, and END's exit sets the status: so `bad`, not `exit 1`.
if ! awk '
  $0 == "# BEGIN workspace-dotfiles shell" { if (o) bad = 1; o = 1 }
  $0 == "# END workspace-dotfiles shell" { if (!o) bad = 1; o = 0 }
  END { exit (bad || o) }
' "$dir/in"; then
  echo "shell-rc: unbalanced workspace-dotfiles block markers; leaving the file unchanged" >&2
  cat "$dir/in"
  exit 0
fi

awk -v add="$add_block" '
  $0 == "# BEGIN workspace-dotfiles shell" { ours = 1; if (add) { print ENVIRON["BLOCK"]; placed = 1 } next }
  ours { if ($0 == "# END workspace-dotfiles shell") ours = 0; next }
  { print; last = $0 }
  END { if (add && !placed) { if (NR && last != "") print ""; print ENVIRON["BLOCK"] } }
' "$dir/in" > "$dir/out"

# Unchanged content passes through byte for byte, whatever its final newline.
if cmp -s "$dir/in" "$dir/out" || { [ -s "$dir/in" ] && [ "$(cat "$dir/in")" = "$(cat "$dir/out")" ]; }; then
  cat "$dir/in"
else
  cat "$dir/out"
fi
