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
        self.calls = root / "calls"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("BOAT_")}
        self.env.update(HOME=str(self.home), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                        BOAT_TEST_CALLS=str(self.calls))

    def run_wrapper(self, *args, settings=None):
        self.calls.write_text("")
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


if __name__ == "__main__":
    unittest.main()
