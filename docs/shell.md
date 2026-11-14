# Shell startup files

`~/.bashrc`, `~/.zshrc`, `~/.profile` and `~/.zshenv` come from the image and are also written by the user and by
installers, so chezmoi does not own them. Each has a `modify_dot_<name>.tmpl` script, rendered from
`.chezmoitemplates/shell-rc-modify.sh`. It changes only what it owns and passes everything else through, byte for
byte when there is nothing to change. This is the same approach as the Codex and Claude Code config files.

- In `~/.bashrc` and `~/.zshrc` it keeps one block, appended when missing:

  ```sh
  # BEGIN workspace-dotfiles shell
  # Managed by chezmoi (workspace-dotfiles): sources ~/.config/shell/rc.d/*.sh. See docs/shell.md.
  if [ -r "$HOME/.config/shell/rc.sh" ]; then . "$HOME/.config/shell/rc.sh"; fi
  # END workspace-dotfiles shell
  ```

- In all four it removes the blocks boat's install script writes (see [boat.md](boat.md)).

A file with an unbalanced marker is left unchanged, with a warning, rather than losing everything after the marker.

## Adding shell integration

Add a file to `dot_config/shell/rc.d/`, named `<tool>.sh`. `~/.config/shell/rc.sh` sources every `rc.d/*.sh` into
interactive bash and zsh, so the file must work in both: functions, aliases, completions and variables for
interactive use. Anything scripts and agents need belongs on `PATH` instead, in `dot_local/bin/`, because
non-interactive shells read no rc file.

Tests: `python3 -m unittest tests.test_shell_rc`.
