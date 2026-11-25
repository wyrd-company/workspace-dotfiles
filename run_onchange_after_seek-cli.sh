#!/bin/bash
# Seek's client.yml (dot_config/seek/client.yml.tmpl, docs/seek.md) needs seek 0.4.0 or later. brew bundle installs a
# missing seek but leaves an older one in place, so upgrade it once. chezmoi runs this again only when it changes.
set -e
minimum=0.4.0
command -v seek >/dev/null || exit 0
installed=$(seek --version)
if [ "$(printf '%s\n%s\n' "$minimum" "$installed" | sort -V | head -n1)" != "$minimum" ]; then
  echo "seek $installed is older than $minimum, which ~/.config/seek/client.yml needs: upgrading" >&2
  brew upgrade wyrd-company/tools/seek-cli
fi
