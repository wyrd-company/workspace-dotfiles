# Deck

[Deck](https://wyrd.foo/tools/deck) lets agents hold Discord conversations: `deck post`, `deck listen`,
`deck reply`, `deck inbox`. The CLI (from `dot_Brewfile`) talks over SSH to a Deck service, which holds the bot
tokens. `deck skill` prints its instructions for agents.

chezmoi writes `~/.config/deck/config.yml` from `dot_config/deck/config.yml.tmpl` and `.chezmoidata/deck.yml`:

- `service`: the service's address and its host key, pinned. While `deck.host_key` is empty, no config is written.
- `key`: Transit key `deck-<workspace>`, with `workspace` from `/etc/workspace/config.yml`. The workspace signs
  through the Wyrwood socket; the private key never leaves OpenBao.
- `session.variables`: `T3CODE_THREAD_ID`, then `CLAUDE_CODE_SESSION_ID`, then `CODEX_THREAD_ID`, so each thread
  keeps its own conversations.
- `store.path`: `~/.local/share/deck/deck.db`, the workspace's mounted Deck state.

## Onboarding a workspace

The service's operator does this once per workspace:

1. Creates Transit key `deck-<workspace>` and registers its public line, with grants (bot, server, parent channels),
   in the service's `keys`.
2. Gives the workspace's Wyrwood binding policy `deck-client` with value `deck_key: <workspace>`: in devcontainer.json,
   add it to `customizations.menagerie.wyrwood.policies` and `values`.

Then `deck channels` lists what the workspace was granted. An unregistered key fails with
`SSH authentication failed`; an ungranted channel is refused (exit 3).

Check the rendering with `python3 -m unittest tests.test_deck`.
