#!/bin/bash
# Runs on every apply, after dot_npm-packages installs: links the commands of each package in ~/.npm-packages into
# ~/.local/bin, which scripts and agents have on PATH; the npm global bin is not. Removes links it made for packages
# no longer listed. Does not replace a file or another link already in ~/.local/bin. See docs/npm-packages.md.
set -uo pipefail

packages="$HOME/.npm-packages"
bin_dir="$HOME/.local/bin"
[ -r "$packages" ] || exit 0
prefix=${NPM_CONFIG_PREFIX:-$(npm prefix -g)} || exit 1
npm_bin="$prefix/bin"
mkdir -p "$bin_dir" || exit 1

failed=0
declare -A want=()

# The commands a package declares in its package.json bin field.
bins() {
  node -e '
    const p = require(process.argv[1]);
    let b = p.bin || {};
    if (typeof b === "string") b = { [p.name.replace(/^@[^/]+\//, "")]: b };
    for (const name of Object.keys(b)) console.log(name);
  ' "$1"
}

while IFS= read -r spec || [ -n "$spec" ]; do
  spec=${spec//[[:space:]]/}
  [ -n "$spec" ] || continue
  # Drop a version or tag: name@1.2 and @scope/name@latest name the package before the last @.
  pkg=$spec
  case $spec in
    @*/*@*) pkg=${spec%@*} ;;
    @*) ;;
    *@*) pkg=${spec%@*} ;;
  esac
  manifest="$prefix/lib/node_modules/$pkg/package.json"
  if [ ! -r "$manifest" ]; then
    echo "npm-bins: $pkg is not installed in $prefix" >&2
    failed=1
    continue
  fi
  names=$(bins "$manifest") || { echo "npm-bins: $pkg: could not read $manifest" >&2; failed=1; continue; }
  while IFS= read -r name; do
    case $name in
      "" | .* | *[!A-Za-z0-9._-]*) echo "npm-bins: $pkg: skipping command '$name'" >&2; continue ;;
    esac
    want[$name]=1
  done <<< "$names"
done < "$packages"

for name in "${!want[@]}"; do
  target="$npm_bin/$name"
  link="$bin_dir/$name"
  if [ ! -e "$target" ]; then
    echo "npm-bins: $target does not exist" >&2
    failed=1
  elif [ -L "$link" ]; then
    current=$(readlink "$link")
    if [ "$current" = "$target" ]; then
      continue
    elif [ "${current#"$npm_bin"/}" = "$current" ]; then
      echo "npm-bins: $link already links to $current; leaving it" >&2
    else
      ln -sfn "$target" "$link" || failed=1
    fi
  elif [ -e "$link" ]; then
    echo "npm-bins: $link already exists; leaving it" >&2
  else
    ln -s "$target" "$link" || failed=1
  fi
done

# Links into the npm global bin for commands no longer listed are ours to remove.
for link in "$bin_dir"/*; do
  [ -L "$link" ] || continue
  current=$(readlink "$link")
  [ "${current#"$npm_bin"/}" != "$current" ] || continue
  [ -n "${want[${link##*/}]+x}" ] || rm -f "$link" || failed=1
done

exit "$failed"
