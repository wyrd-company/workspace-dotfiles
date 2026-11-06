"""Exercise recipient routing without OpenBao credentials or network requests."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "dot_local/bin/executable_pushover"
MOCK_COMMAND = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

command = Path(sys.argv[0]).name
with open(os.environ["PUSHOVER_TEST_CALLS"], "a") as log:
    log.write(json.dumps([command, *sys.argv[1:]]) + "\n")
if command == "bao":
    operation = sys.argv[2]
    if os.environ.get("PUSHOVER_TEST_DENY") == operation:
        print("permission denied", file=sys.stderr)
        sys.exit(2)
    if operation == "list":
        print(os.environ.get("PUSHOVER_TEST_NAMES", '["boblangley", "iradesa"]'))
    else:
        recipient = sys.argv[-1].rsplit("/", 1)[-1]
        credentials = {"user_key": recipient + "-user", "app_token": recipient + "-token"}
        print(os.environ.get("PUSHOVER_TEST_SECRET", json.dumps({"data": {"data": credentials}})))
else:
    if os.environ.get("PUSHOVER_TEST_CURL_FAIL"):
        sys.exit(28)
    print(os.environ.get("PUSHOVER_TEST_RESPONSE", '{"status":1}'))
'''


class PushoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pushover-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for command in ("bao", "curl"):
            mock = self.root / command
            mock.write_text(MOCK_COMMAND)
            mock.chmod(0o755)
        self.log = self.root / "calls"
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith("PUSHOVER_"):
                del self.env[key]
        self.env.update(
            PATH=str(self.root) + os.pathsep + os.environ["PATH"],
            PUSHOVER_TEST_CALLS=str(self.log),
        )

    def run_cli(self, *args, settings=None):
        self.log.write_text("")
        result = subprocess.run(
            ["bash", str(SCRIPT), *args],
            env={**self.env, **(settings or {})},
            text=True,
            capture_output=True,
            timeout=5,
        )
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, calls

    def test_missing_recipient_lists_names_without_reading_credentials(self):
        for args in ((), ("--message", "hello"), ("--recipient", ""), ("--recipient",), ("--recipient", "--message", "hello")):
            with self.subTest(args=args):
                result, calls = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("boblangley", result.stdout)
                self.assertIn("iradesa", result.stdout)
                self.assertIn("--recipient is required", result.stderr)
                self.assertEqual(calls, [["bao", "kv", "list", "-format=json", "kv/workspace/pushover"]])

    def test_list_only_does_not_send_even_with_message(self):
        result, calls = self.run_cli("--list-recipients", "--message", "never send")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("iradesa", result.stdout)

    def test_routes_each_recipient_to_their_own_credentials(self):
        for recipient in ("boblangley", "iradesa"):
            with self.subTest(recipient=recipient):
                result, calls = self.run_cli("--recipient", recipient, "--message", "hello")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls[1], ["bao", "kv", "get", "-format=json", "kv/workspace/pushover/" + recipient])
                self.assertEqual(len(calls), 3)
                self.assertIn("user=" + recipient + "-user", calls[2])
                self.assertIn("token=" + recipient + "-token", calls[2])

    def test_unprovisioned_and_unsafe_recipients_never_read_or_send(self):
        for recipient in ("unknown", "../boblangley", "boblangley/other"):
            with self.subTest(recipient=recipient):
                result, calls = self.run_cli("--recipient", recipient, "--message", "hello")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Unsupported recipient", result.stderr)
                self.assertIn("boblangley", result.stderr)
                self.assertEqual(len(calls), 1)

    def test_names_are_discovered_and_directories_are_excluded(self):
        result, calls = self.run_cli(
            "--list-recipients",
            settings={"PUSHOVER_TEST_NAMES": '["new-person", "folder/", "../escape", null, 1]'},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("new-person", result.stdout)
        self.assertNotIn("folder", result.stdout)
        self.assertNotIn("escape", result.stdout)
        self.assertEqual(len(calls), 1)

    def test_list_denial_stops_without_fallback(self):
        result, calls = self.run_cli(
            "--recipient", "boblangley", "--message", "hello",
            settings={"PUSHOVER_TEST_DENY": "list"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("permission denied", result.stderr)
        self.assertEqual(len(calls), 1)

    def test_credential_denial_stops_without_parent_secret_fallback(self):
        result, calls = self.run_cli(
            "--recipient", "iradesa", "--message", "hello",
            settings={"PUSHOVER_TEST_DENY": "get"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1][-1], "kv/workspace/pushover/iradesa")

    def test_invalid_recipient_lists_fail_without_sending(self):
        for names in ("[]", "{}", "not-json", '["directory/"]'):
            with self.subTest(names=names):
                result, calls = self.run_cli("--list-recipients", settings={"PUSHOVER_TEST_NAMES": names})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 1)

    def test_missing_or_invalid_credentials_never_send(self):
        for secret in ("{}", "not-json", '{"data":{"data":{"user_key":"user"}}}'):
            with self.subTest(secret=secret):
                result, calls = self.run_cli(
                    "--recipient", "boblangley", "--message", "hello",
                    settings={"PUSHOVER_TEST_SECRET": secret},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 2)

    def test_overrides_still_require_supported_recipient(self):
        result, calls = self.run_cli("--message", "hello", "--user", "override", "--token", "override")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        result, calls = self.run_cli(
            "--recipient", "boblangley", "--message", "hello", "--user", "override", "--token", "override",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0], "curl")
        self.assertIn("user=override", calls[1])

    def test_custom_root_preserves_recipient_layout(self):
        result, calls = self.run_cli(
            "--recipient", "iradesa", "--message", "hello",
            settings={"PUSHOVER_SECRET_ROOT": "kv/custom/recipients/"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[0][-1], "kv/custom/recipients")
        self.assertEqual(calls[1][-1], "kv/custom/recipients/iradesa")

    def test_legacy_path_override_cannot_redirect_delivery(self):
        result, calls = self.run_cli(
            "--recipient", "iradesa", "--message", "hello",
            settings={"PUSHOVER_SECRET_PATH": "kv/workspace/pushover"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[1][-1], "kv/workspace/pushover/iradesa")

    def test_message_is_preserved_literally(self):
        message = '@literal <tag> * "quoted"\nsecond line'
        result, calls = self.run_cli("--recipient", "boblangley", "--message", message)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("message=" + message, calls[-1])

    def test_api_and_transport_failures_return_nonzero(self):
        for settings in ({"PUSHOVER_TEST_RESPONSE": '{"status":0}'}, {"PUSHOVER_TEST_CURL_FAIL": "1"}):
            with self.subTest(settings=settings):
                result, calls = self.run_cli("--recipient", "boblangley", "--message", "hello", settings=settings)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 3)

    def test_quiet_suppresses_lists_and_errors(self):
        for args, settings in (
            ((), {}),
            (("--list-recipients",), {}),
            (("--list-recipients",), {"PUSHOVER_TEST_DENY": "list"}),
            (("--recipient", "iradesa", "--message", "hello"), {"PUSHOVER_TEST_SECRET": "not-json"}),
        ):
            with self.subTest(args=args, settings=settings):
                result, _ = self.run_cli("--quiet", *args, settings=settings)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_help_version_and_invalid_arguments_do_not_access_bao(self):
        for args, status in ((("--help",), 0), (("--version",), 0), (("--message",), 1), (("--unknown",), 1)):
            with self.subTest(args=args):
                result, calls = self.run_cli(*args)
                self.assertEqual(result.returncode, status)
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
