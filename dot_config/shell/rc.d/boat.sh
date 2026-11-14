# boat in interactive bash and zsh. Managed by workspace-dotfiles; see docs/boat.md.
# Runs the API key wrapper, ~/.local/bin/boat. After `boat new`, `start` or `fork` the new sandbox is this
# shell's current one (BOAT_CURRENT_ID), and after `boat prompt` its conversation is (BOAT_CURRENT_CONVO): boat
# writes them to the files named by BOAT_CURRENT_ID_FILE and BOAT_CURRENT_CONVO_FILE.
boat() {
  local id_file= convo_file= rc=0 id= convo=
  id_file=$(mktemp) || return 1
  convo_file=$(mktemp) || { rm -f "$id_file"; return 1; }
  BOAT_CURRENT_ID_FILE=$id_file BOAT_CURRENT_CONVO_FILE=$convo_file command "$HOME/.local/bin/boat" "$@"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    case ${1-} in
      new | start | fork)
        id=$(tr -d '[:space:]' < "$id_file")
        if [ -n "$id" ]; then export BOAT_CURRENT_ID="$id"; fi
        ;;
      prompt)
        IFS= read -r convo < "$convo_file" || true
        if [ -n "$convo" ]; then export BOAT_CURRENT_CONVO="$convo"; fi
        ;;
    esac
  fi
  rm -f "$id_file" "$convo_file"
  return "$rc"
}
