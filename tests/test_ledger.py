"""Exercise ledger against the real skate, in a temporary store."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


LEDGER = Path(__file__).resolve().parents[1] / "dot_local/bin/executable_ledger"


@unittest.skipUnless(shutil.which("skate") and shutil.which("jq") and shutil.which("flock"),
                     "needs skate, jq and flock")
class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ledger-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("LEDGER_", "T3CODE_"))}
        self.env.update(SKATE_STORE=str(self.root / "kv"), T3CODE_THREAD_ID="thr-1")

    def ledger(self, *args, check=True, **settings):
        result = subprocess.run(["bash", str(LEDGER), *args], env={**self.env, **settings},
                                text=True, capture_output=True, timeout=60)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def records(self, *args):
        return json.loads(self.ledger("list", "--json", *args).stdout)

    def test_acquire_records_the_resource_in_the_thread_ledger(self):
        self.ledger("acquire", "worktree:/w/Repo", "--cleanup", "git worktree remove /w/Repo", "--verify", "test -d /w")
        [record] = self.records()
        self.assertEqual(record["db"], "thr-1")
        self.assertEqual(record["key"], "worktree:/w/Repo")  # Skate lowercases keys; the record keeps the case
        self.assertEqual(record["kind"], "worktree")
        self.assertEqual(record["acquired_by"], "thr-1")
        self.assertEqual(record["cleanup"], "git worktree remove /w/Repo")
        self.assertNotIn("instructions", record)

    def test_acquire_refuses_bad_input_and_duplicates(self):
        for args, message in (
            (["acquire", "nokind", "--cleanup", "x"], "bad key"),
            (["acquire", "a:b c", "--cleanup", "x"], "bad key"),
            (["acquire", "a:b@c", "--cleanup", "x"], "bad key"),
            (["acquire", "a:b"], "needs --cleanup or --instructions"),
            (["--db", "x@y", "acquire", "a:b", "--cleanup", "x"], "bad ledger name"),
        ):
            with self.subTest(args=args):
                result = self.ledger(*args, check=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
        self.ledger("acquire", "a:b", "--instructions", "one")
        result = self.ledger("acquire", "a:b", "--instructions", "two", check=False)
        self.assertIn("already in ledger thr-1", result.stderr)
        self.ledger("acquire", "a:b", "--instructions", "two", "--replace")
        self.assertEqual(self.records()[0]["instructions"], "two")

    def test_no_ledger_without_a_thread(self):
        result = self.ledger("list", check=False, T3CODE_THREAD_ID="")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no ledger", result.stderr)
        self.ledger("list", T3CODE_THREAD_ID="", LEDGER_DB="task-1")

    def test_handoff_moves_the_resource_and_keeps_its_history(self):
        self.ledger("acquire", "boat:sandbox/sbx_1", "--cleanup", "boat delete --yes sbx_1")
        self.assertEqual(self.ledger("handoff", "--to", "task-7", "boat:sandbox/sbx_1").stdout,
                         "boat:sandbox/sbx_1 -> task-7\n")
        self.assertEqual(self.records(), [])
        [record] = self.records("--all")
        self.assertEqual(record["db"], "task-7")
        self.assertEqual(record["acquired_in"], "thr-1")
        self.assertEqual([(h["from"], h["to"], h["by"]) for h in record["handoffs"]], [("thr-1", "task-7", "thr-1")])
        result = self.ledger("handoff", "--to", "task-8", "boat:sandbox/sbx_1", check=False)
        self.assertIn("not in ledger thr-1", result.stderr)

    def test_acquire_warns_when_another_ledger_holds_the_key(self):
        self.ledger("acquire", "a:b", "--instructions", "x", LEDGER_DB="other")
        self.assertIn("also in ledger other", self.ledger("acquire", "a:b", "--instructions", "x").stderr)

    def test_release(self):
        self.ledger("acquire", "a:b", "--instructions", "x")
        self.ledger("acquire", "a:c", "--instructions", "x", LEDGER_DB="other")
        self.ledger("release", "a:b")
        result = self.ledger("release", "a:b", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not in ledger thr-1", result.stderr)
        self.ledger("release", "--missing-ok", "a:b")
        self.ledger("release", "--all-dbs", "a:c")
        self.assertEqual(self.records("--all"), [])

    def test_clean_runs_cleanups_honours_verify_and_keeps_what_is_left(self):
        present = self.root / "present"
        present.mkdir()
        self.ledger("acquire", "dir:present", "--cleanup", f"rm -r '{present}'", "--verify", f"test -d '{present}'")
        self.ledger("acquire", "dir:gone", "--cleanup", "false", "--verify", "test -d /nonexistent-ledger-test")
        self.ledger("acquire", "dir:unknown", "--cleanup", "true", "--verify", "exit 7")  # unknown: clean up
        self.ledger("acquire", "dir:broken", "--cleanup", "false")
        self.ledger("acquire", "gh:branch/x", "--instructions", "delete branch x")
        dry = self.ledger("clean", "--dry-run")
        self.assertIn("gh:branch/x\tBY HAND: delete branch x", dry.stdout)
        self.assertTrue(present.exists())
        result = self.ledger("clean", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(present.exists())
        self.assertIn("dir:gone: already gone, released", result.stdout)
        self.assertIn("dir:present: cleaned up, released", result.stdout)
        self.assertIn("dir:unknown: cleaned up, released", result.stdout)
        self.assertIn("dir:broken: cleanup failed, kept", result.stderr)
        self.assertIn("gh:branch/x: by hand, kept: delete branch x", result.stdout)
        self.assertEqual(sorted(r["key"] for r in self.records()), ["dir:broken", "gh:branch/x"])

    def test_clean_named_keys_only(self):
        self.ledger("acquire", "a:one", "--cleanup", "true")
        self.ledger("acquire", "a:two", "--cleanup", "true")
        self.ledger("clean", "A:One")
        self.assertEqual([r["key"] for r in self.records()], ["a:two"])
        self.assertIn("not in ledger", self.ledger("clean", "a:none", check=False).stderr)

    def test_a_cleanup_that_calls_ledger_does_not_deadlock(self):
        self.ledger("acquire", "a:self", "--cleanup", f"bash '{LEDGER}' release --missing-ok --all-dbs a:self")
        self.assertIn("a:self: cleaned up, released", self.ledger("clean").stdout)

    def test_parallel_writers_to_one_ledger_all_land(self):
        with ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda i: self.ledger("acquire", f"k:{i}", "--cleanup", "true", check=False),
                                    range(8)))
        self.assertEqual([r.returncode for r in results], [0] * 8, [r.stderr for r in results])
        self.assertEqual(len(self.records()), 8)

    def test_dbs_counts_entries(self):
        self.ledger("acquire", "a:1", "--instructions", "x")
        self.ledger("acquire", "a:2", "--instructions", "x")
        self.ledger("acquire", "a:1", "--instructions", "x", LEDGER_DB="task-2")
        self.assertEqual(self.ledger("dbs").stdout, "task-2\t1\nthr-1\t2\n")


if __name__ == "__main__":
    unittest.main()
