#!/bin/bash
# Seek's client.yml (dot_config/seek/client.yml.tmpl, docs/seek.md) needs seek 0.4.0 or later. brew bundle installs a
# missing seek but leaves an older one in place, so upgrade it once. chezmoi runs this again only when it changes or
# until it succeeds, so it fails while seek is still too old.
set -e
minimum=0.4.0
formula=wyrd-company/tools/seek-cli
command -v seek >/dev/null || exit 0
too_old() {
  installed=$(seek --version)
  [ "$(printf '%s\n%s\n' "$minimum" "$installed" | sort -V | head -n1)" != "$minimum" ]
}
too_old || exit 0
echo "seek $installed is older than $minimum, which ~/.config/seek/client.yml needs: upgrading" >&2
brew upgrade "$formula" || true
# A stale tap can report the old release as current: refresh the taps and try once more. A refresh can fail part way
# yet still advance the tap, so the version check below decides, not brew's exit status.
if too_old; then
  brew update --quiet || true
  brew upgrade "$formula" || true
fi
if too_old; then
  echo "seek is still $installed after brew upgrade; $minimum or later is needed. Run: brew update && brew upgrade $formula" >&2
  exit 1
fi
