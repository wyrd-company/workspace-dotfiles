# Install scripts

Some tools are only distributed through the vendor's `install.sh`: the `curl -fsSL https://... | sh` line on
their install page. Use `dot_Brewfile`, `dot_npm-packages` or `dot_config/python/global-requirements.txt` when the
tool is available there; use this when it is not.

## Add a tool

Add an entry to `install_scripts` in `.chezmoidata/install-scripts.yml`, then `chezmoi apply`.

```yaml
install_scripts:
  - name: uv
    url: https://astral.sh/uv/install.sh
    bin: ~/.local/bin/uv
    env:
      UV_INSTALL_DIR: ~/.local/bin
      UV_NO_MODIFY_PATH: 1
```

| Field    | Required | Meaning |
| -------- | -------- | ------- |
| `name`   | yes      | Letters, digits, `.`, `_`, `-`. Names the tool in logs and its state file. |
| `url`    | yes      | `https://` URL of the install script. |
| `bin`    | yes      | What the script installs: a command on `PATH`, or a path starting with `~/`. |
| `shell`  | no       | The interpreter the vendor pipes to, `sh` by default. |
| `sha256` | no       | Checksum the downloaded script must match. Pin it when the vendor publishes one. |
| `args`   | no       | Arguments passed to the script, as `sh -s -- <args>` would. |
| `env`    | no       | Environment variables the script reads, such as its install dir or version. |

A value in `env`, or an argument, that starts with `~/` is passed as an absolute path under `$HOME`.

Read the script before adding it. Most take an install dir and a switch to leave shell rc files alone; set them in
`env` or `args`, and prefer installing into `~/.local/bin`. Set `bin` to a `~/` path when the install dir may not be
on `PATH` while chezmoi runs.

## How it runs

`run_after_install-scripts.sh.tmpl` runs on every apply, after chezmoi has written the files and run the
Brewfile, npm and pip scripts. For each entry it:

1. Skips the entry, without a download, when `bin` exists and the entry is unchanged since its last successful
   install. The state is one file per tool under `~/.local/state/install-scripts/`, holding a hash of the entry.
2. Otherwise downloads the script to a temporary directory over HTTPS, refusing a redirect to any other protocol,
   checks `sha256` when one is set, and runs it there with `env` and `args`, with no input so a prompt cannot wait
   for an answer.
3. Records the install only when the script exits 0 and `bin` then exists.

Changing any field of an entry (for example a pinned version in `env`) reinstalls that tool; deleting its binary
does too. Upgrades of unchanged entries are left to the tool's own updater, such as `uv self update`. Removing an
entry does not uninstall the tool.

A failed entry does not stop the others. The run lists the failures and exits 1, and they are retried on the next
apply. Tests: `python3 -m unittest tests.test_install_scripts`, against a fake `curl` without network access.
