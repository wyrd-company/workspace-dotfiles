# Ledger

`ledger` (`dot_local/bin/executable_ledger`) records what a thread or task acquires, such as Boat sandboxes,
worktrees, branches and preview deployments, together with how to remove each one. Whoever closes the work later,
whether the same agent, another agent or a person, reads the ledger instead of searching a transcript.

The `ledger` skill (wyrd-company/skills) covers when agents use it. This page covers how it works.

## Store

Each ledger is a [Skate](https://github.com/charmbracelet/skate) database in the default store,
`~/.local/share/charm/kv` (or `SKATE_STORE`). workspace-template binds `state/charm` there, so ledgers survive a
container rebuild. Skate v1 is local only: a ledger is visible to this workspace's container, not to Boat sandboxes
or other machines.

- **Ledger name.** `--db`, else `LEDGER_DB`, else `T3CODE_THREAD_ID`. A task's ledger is `task-<id>`. Skate lowercases
  database names and cuts them at a `/`, and thread ids can hold both (a delegated task's is
  `thread:delegated-task:command%3Amcp...`). So `ledger` lowercases every name and percent-encodes, in lowercase
  hex, each character outside `a-z 0-9 . _ : % -`. `Task-7` and `task-7` are one ledger. When a release or
  handoff empties a ledger, the ledger is deleted.
- **Key.** `kind:name`, naming the resource itself, so the same resource always has the same key: `boat:sandbox/<id>`,
  `worktree:<path>`, `gh:branch/<owner>/<repo>/<branch>`. Skate lowercases keys. The record keeps the original
  case for display, and `Foo:x` and `foo:x` are the same resource.
- **Value.** A one-line JSON record:

  ```json
  {"key": "boat:sandbox/sbx_1", "kind": "boat", "acquired_at": "2026-11-15T22:50:15Z",
   "acquired_by": "<thread>", "acquired_in": "<ledger>", "cleanup": "boat delete --yes sbx_1",
   "instructions": "...", "verify": "...", "handoffs": [{"at": "...", "from": "...", "to": "...", "by": "..."}]}
  ```

  - `cleanup` is a shell command that removes the resource. It must be safe to run twice.
  - `instructions` is for resources that someone has to remove by hand.
  - `verify` is optional. It exits 0 while the resource exists, 1 once it is gone, and anything else for unknown.

## Commands

```sh
ledger acquire worktree:/workspace/r/worktrees/x --cleanup "git -C /workspace/r worktree remove x" \
  --verify "test -d /workspace/r/worktrees/x || exit 1"
ledger acquire gh:branch/o/r/feat-x --instructions "Delete branch feat-x once PR #12 merges"
ledger list                      # this thread's ledger; --all for every ledger, --json for records
ledger show KEY
ledger handoff --to task-42 KEY  # another ledger is now responsible for it
ledger release KEY               # it is gone (removed some other way); does not run the cleanup
ledger clean [--dry-run] [KEY]   # verify, run cleanups, release what succeeded; exit 1 if anything is left
ledger dbs                       # ledgers and their entry counts
```

`handoff` writes the target before it deletes the source. If it stops halfway, the resource is in both ledgers,
never in neither, and a cleanup that is safe to run twice makes that harmless. `acquire` warns when another
ledger already holds the key.

## Locking

Skate's store (Badger) allows one writer per database at a time. A second concurrent `skate set` on the same
database fails rather than waiting. `ledger` holds an `flock` on `<store>.lock` around every store access and
retries briefly. Use `ledger` rather than calling `skate` directly on these databases. `clean` runs cleanup
commands without holding the lock, because a cleanup may itself call `ledger`, as `boat delete` does.

## Automatic entries

- **Boat.** The `boat` wrapper acquires `boat:sandbox/<id>` after `boat new` and `boat fork`, with
  `boat delete --yes [--org ...] <id>` as the cleanup. After a successful `boat delete`, it releases the sandbox
  from whichever ledger holds it. See [boat.md](boat.md).

Tests: `python3 -m unittest tests.test_ledger tests.test_boat`. The ledger tests use the real `skate` in a
temporary store.
