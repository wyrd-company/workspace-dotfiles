# Fork overlay

A workspace can run on a fork of this repository and still pull upstream's changes without merge conflicts. The
fork adds files under two paths that upstream never commits to. Everything else stays upstream's.

| Path in the fork | Combines with upstream | Effect |
| --- | --- | --- |
| `.chezmoidata/zz-fork/*.yml` | Merged | Data. Maps deep-merge into upstream's, lists replace upstream's. |
| `.includes/fork/*.md` | Added | Operator-written notes, appended to every harness's instructions. |

## Data: `.chezmoidata/zz-fork/*.yml`

chezmoi reads `.chezmoidata/` recursively in lexical path order, and later files win. `zz-fork/` sorts after every
upstream file, so it overrides them. The rule for a key is:

- A map is merged key by key. Set only the keys you change.
- A list is replaced as a whole. To change one operator, restate all of them.
- A scalar is replaced.

Do not edit `.chezmoidata/operators.yml` or any other upstream data file in a fork.

Example, `.chezmoidata/zz-fork/operators.yml`, replaces the operators list:

```yaml
operators:
  - handle: jdoe
    name: Jo Doe
    github_pubkey: "ssh-ed25519 AAAA... ssh-operator-jdoe"
```

Example, `.chezmoidata/zz-fork/deck.yml`, changes one key and keeps the rest of `deck`:

```yaml
deck:
  default_channel: wyrdbot/1287000000000000002
```

## Instructions: `.includes/fork/*.md`

`.chezmoitemplates/instructions.md` renders `.includes/CORE-INSTRUCTIONS.md`, then every `.includes/fork/*.md` in
sorted file-name order, inside one `<fork-instructions>` tag after `</core-instructions>`. The Claude Code, Codex, pi
and Grok harness files all use it, so the notes reach every harness. Without fork files the output is exactly
upstream's. Number the files (`10-operators.md`, `20-network.md`) to control the order.

The notes are the operators' own: who they are, how they like to work, what the workspace is for. They are not
core instructions, so they go in their own tag and are never mixed into `CORE-INSTRUCTIONS.md`.

Example, `.includes/fork/10-operators.md`:

```markdown
- Jo Doe (`jdoe`) runs this workspace and reviews every PR. Jo prefers short summaries, with the proof first.
- Ask Jo before touching billing.
```

The harness files then end the core with:

```text
</core-instructions>

<fork-instructions>
- Jo Doe (`jdoe`) runs this workspace and reviews every PR. Jo prefers short summaries, with the proof first.
- Ask Jo before touching billing.
</fork-instructions>

<claude-instructions>
```

## What keeps this working

- `.chezmoiignore` ignores `.includes/**/*.*`, so the notes are never written to the home directory as files.
  `.chezmoidata/` is never a target.
- The template resolves the notes with `glob (joinPath .chezmoi.sourceDir ".includes" "fork" "*.md")`. `glob` and
  `stat` resolve a relative pattern against the working directory, not the source directory, so keep the path
  absolute. `include` of a path inside the source directory is fine.
- Nothing upstream may add a file under `.chezmoidata/zz-fork/` or `.includes/fork/`.

`tests/test_fork_overlay.py` renders with and without these paths into a temporary destination and home.
