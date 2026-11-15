"""Exercise the boat wrapper with a fake bao and a fake boat binary, without OpenBao or network access."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO / "dot_local/bin/executable_boat"
FAKE_BAO = r'''#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["BOAT_TEST_CALLS"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
if os.environ.get("BOAT_TEST_DENY"):
    print("permission denied", file=sys.stderr)
    sys.exit(2)
sys.stdout.write(os.environ.get("BOAT_TEST_KEY", "bk_from_bao"))
'''
# Prints what the real boat would see.
FAKE_BOAT = r'''#!/usr/bin/env python3
import json
import os
import sys

print(json.dumps({"args": sys.argv[1:], "key": os.environ.get("BOAT_API_KEY")}))
if sys.argv[1:2] in (["new"], ["fork"]) and os.environ.get("BOAT_CURRENT_ID_FILE"):
    with open(os.environ["BOAT_CURRENT_ID_FILE"], "w") as f:
        f.write(" sbx_new\n")
sys.exit(int(os.environ.get("BOAT_TEST_RC", "0")))
'''
FAKE_LEDGER = r'''#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["LEDGER_TEST_CALLS"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
sys.exit(int(os.environ.get("LEDGER_TEST_RC", "0")))
'''


class BoatWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="boat-wrapper-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.home = root / "home"
        self.real = self.home / ".ascii/bin/boat"
        self.real.parent.mkdir(parents=True)
        self.real.write_text(FAKE_BOAT)
        self.real.chmod(0o755)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "bao").write_text(FAKE_BAO)
        (bin_dir / "bao").chmod(0o755)
        (bin_dir / "ledger").write_text(FAKE_LEDGER)
        (bin_dir / "ledger").chmod(0o755)
        self.calls = root / "calls"
        self.ledger_calls = root / "ledger-calls"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("BOAT_", "LEDGER_", "T3CODE_"))}
        self.env.update(HOME=str(self.home), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                        BOAT_TEST_CALLS=str(self.calls), LEDGER_TEST_CALLS=str(self.ledger_calls))

    def run_wrapper(self, *args, settings=None):
        self.calls.write_text("")
        self.ledger_calls.write_text("")
        result = subprocess.run(
            ["bash", str(WRAPPER), *args], env={**self.env, **(settings or {})},
            text=True, capture_output=True, timeout=10,
        )
        return result, [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_passes_the_key_from_bao_and_the_arguments(self):
        result, calls = self.run_wrapper("list", "--name", "two words")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"args": ["list", "--name", "two words"], "key": "bk_from_bao"})
        self.assertEqual(calls, [["kv", "get", "-field=api_key", "kv/workspace/boat"]])

    def test_a_key_already_set_is_used_without_bao(self):
        result, calls = self.run_wrapper("list", settings={"BOAT_API_KEY": "bk_from_caller"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["key"], "bk_from_caller")
        self.assertEqual(calls, [])

    def test_denied_or_empty_key_fails_without_running_boat(self):
        for settings, message in (
            ({"BOAT_TEST_DENY": "1"}, "Cannot read api_key from kv/workspace/boat"),
            ({"BOAT_TEST_KEY": ""}, "kv/workspace/boat has an empty api_key"),
        ):
            with self.subTest(message=message):
                result, _ = self.run_wrapper("list", settings=settings)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn(message, result.stderr)

    def test_missing_binary_points_at_chezmoi_apply(self):
        self.real.unlink()
        result, calls = self.run_wrapper("list")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not installed; run chezmoi apply", result.stderr)
        self.assertEqual(calls, [])

    def ledger(self):
        return [json.loads(line) for line in self.ledger_calls.read_text().splitlines()]

    def test_other_commands_leave_the_ledger_alone(self):
        result, _ = self.run_wrapper("list", settings={"T3CODE_THREAD_ID": "thr"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ledger(), [])

    def test_new_and_fork_record_the_sandbox_in_the_thread_ledger(self):
        for command in ("new", "fork"):
            with self.subTest(command=command):
                result, _ = self.run_wrapper(command, "--org", "acme corp", settings={"T3CODE_THREAD_ID": "thr"})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.ledger(), [[
                    "--db", "thr", "acquire", "boat:sandbox/sbx_new", "--replace",
                    "--cleanup", "boat delete --yes --org acme\\ corp sbx_new",
                ]])

    def test_ledger_db_overrides_the_thread_and_the_callers_id_file_is_kept(self):
        id_file = Path(self.temp.name) / "caller-id"
        result, _ = self.run_wrapper("new", settings={
            "T3CODE_THREAD_ID": "thr", "LEDGER_DB": "task-9", "BOAT_CURRENT_ID_FILE": str(id_file)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ledger()[0][:4], ["--db", "task-9", "acquire", "boat:sandbox/sbx_new"])
        self.assertEqual(id_file.read_text().strip(), "sbx_new")

    def test_failed_new_records_nothing_and_keeps_the_status(self):
        result, _ = self.run_wrapper("new", settings={"T3CODE_THREAD_ID": "thr", "BOAT_TEST_RC": "3"})
        self.assertEqual(result.returncode, 3)
        self.assertEqual(self.ledger(), [])

    def test_no_thread_warns_and_still_succeeds(self):
        result, _ = self.run_wrapper("new")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("record the sandbox yourself", result.stderr)
        self.assertEqual(self.ledger(), [])

    def test_a_ledger_failure_does_not_fail_boat(self):
        result, _ = self.run_wrapper("new", settings={"T3CODE_THREAD_ID": "thr", "LEDGER_TEST_RC": "2"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("could not record boat:sandbox/sbx_new", result.stderr)

    def test_delete_releases_the_sandbox_from_any_ledger(self):
        for args, settings, released in (
            (["delete", "--yes", "sbx_1"], {}, "sbx_1"),
            (["delete", "--org", "acme", "sbx_2", "--yes"], {}, "sbx_2"),
            (["delete", "--yes"], {"BOAT_CURRENT_ID": "sbx_3"}, "sbx_3"),
            (["delete", "current"], {"BOAT_CURRENT_ID": "sbx_4"}, "sbx_4"),
        ):
            with self.subTest(args=args):
                result, _ = self.run_wrapper(*args, settings=settings)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.ledger(), [["release", "--missing-ok", "--all-dbs", f"boat:sandbox/{released}"]])

    def test_failed_or_self_delete_releases_nothing(self):
        for args, settings in ((["delete", "sbx_1"], {"BOAT_TEST_RC": "1"}), (["delete", "self"], {})):
            with self.subTest(args=args):
                result, _ = self.run_wrapper(*args, settings=settings)
                self.assertEqual(self.ledger(), [])


if __name__ == "__main__":
    unittest.main()
