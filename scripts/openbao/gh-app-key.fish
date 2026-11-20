#!/usr/bin/env fish
# Imports a GitHub App's private key into OpenBao Transit (wyrwood namespace), checks that Transit holds the same key
# as the downloaded file, then deletes the file. Transit refuses to import over an existing key, so this is for a new
# App only. Run it on a workstation that can reach OpenBao, not in a workspace container. See docs/vault.md.
#   fish scripts/openbao/gh-app-key.fish

set -q BAO_ADDR; or set -x BAO_ADDR https://openbao.internal:8200

# Tokenize like the shell, so quoted, escaped or dragged-in paths work; rejoin an unquoted path with spaces.
read --tokenize --list --prompt-str 'Path to the downloaded .pem: ' pem
set pem (string join ' ' -- $pem | string replace --regex '^~(?=/|$)' $HOME)
if not test -f "$pem"
    echo "Not found: [$pem]"
    exit 1
end
if not openssl pkey -in $pem -noout 2>/dev/null
    echo "Not a private key: $pem"
    exit 1
end

read --prompt-str 'Transit key name (gh-app-wyrd-<name>): ' key
if not string match --quiet --regex '^gh-app-[a-z0-9-]+$' -- $key
    echo "The key name should look like gh-app-wyrd-<name>: lowercase letters, digits and dashes."
    exit 1
end

# Use BAO_TOKEN or the token from `bao login`; ask for one (without echo) only when neither is valid.
if not bao token lookup >/dev/null 2>&1
    read --silent --prompt-str 'OpenBao token: ' token
    set -x BAO_TOKEN $token
    set -e token
    if not bao token lookup >/dev/null 2>&1
        echo "OpenBao rejected the token, or $BAO_ADDR is unreachable."
        exit 1
    end
end

if bao read -namespace=wyrwood transit/keys/$key >/dev/null 2>&1
    echo "Transit key $key already exists; the key file is untouched."
    exit 1
end

set der (openssl pkcs8 -topk8 -nocrypt -in $pem -outform DER | base64 -w0)
bao transit import -namespace=wyrwood transit/keys/$key $der type=rsa-2048
or begin
    set -e der
    echo "Import failed; the key file is untouched."
    exit 1
end
set -e der

set transit_hash (bao read -namespace=wyrwood -format=json transit/keys/$key \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["keys"]["1"]["public_key"], end="")' \
    | openssl pkey -pubin -outform DER | sha256sum | string split -f1 ' ')
set file_hash (openssl pkey -in $pem -pubout -outform DER | sha256sum | string split -f1 ' ')
echo "Transit: $transit_hash"
echo "File:    $file_hash"

if test "$transit_hash" != "$file_hash"
    echo "MISMATCH: kept $pem. Delete transit/keys/$key in the wyrwood namespace before trying again."
    exit 1
end
echo "Match."

shred -u $pem
and echo "Deleted $pem."
or begin
    echo "Could not delete $pem; delete it by hand."
    exit 1
end

echo
echo "Next: grant transit/sign/$key in Wyrwood, and add the App to dot_config/gh-vault-agent-app-token/config.yml."
