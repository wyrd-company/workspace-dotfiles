# Sources each ~/.config/shell/rc.d/*.sh into interactive bash and zsh, from the block chezmoi keeps in
# ~/.bashrc and ~/.zshrc. Managed by workspace-dotfiles; see docs/shell.md.
if [ -n "${ZSH_VERSION-}" ]; then
  # (N): no error when the directory has no files. eval keeps the zsh-only glob away from bash's parser.
  eval 'for _rc_d_file in "$HOME"/.config/shell/rc.d/*.sh(N); do . "$_rc_d_file"; done'
else
  for _rc_d_file in "$HOME"/.config/shell/rc.d/*.sh; do
    if [ -r "$_rc_d_file" ]; then . "$_rc_d_file"; fi
  done
fi
unset _rc_d_file
