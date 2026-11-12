"""Exercise the AWS CLI credential helper and R2 config without OpenBao credentials or network requests."""

import configparser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "dot_local/bin/executable_aws-bao-credentials"
TEMPLATE = REPO / "private_dot_aws/private_config.tmpl"
MOCK_BAO = r'''#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["AWS_TEST_CALLS"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
if os.environ.get("AWS_TEST_DENY"):
    print("permission denied", file=sys.stderr)
    sys.exit(2)
path = sys.argv[-1]
if path == "kv/workspace/r2/account":
    data = {"account_id": "0123456789abcdef"}
else:
    data = json.loads(os.environ.get("AWS_TEST_FIELDS", '{"access_key_id": "AKID", "secret_access_key": "SECRET"}'))
print(json.dumps({"data": {"data": data}}))
'''


class AwsCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aws-cli-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        bao = self.root / "bao"
        bao.write_text(MOCK_BAO)
        bao.chmod(0o755)
        self.log = self.root / "calls"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("AWS_")}
        self.env.update(PATH=str(self.root) + os.pathsep + os.environ["PATH"], AWS_TEST_CALLS=str(self.log))

    def run_helper(self, *args, settings=None):
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

    def test_prints_credential_process_json_from_one_read(self):
        result, calls = self.run_helper("kv/workspace/r2/buckets/assets-wyrd-foo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"Version": 1, "AccessKeyId": "AKID", "SecretAccessKey": "SECRET"},
        )
        self.assertEqual(calls, [["kv", "get", "-format=json", "kv/workspace/r2/buckets/assets-wyrd-foo"]])

    def test_denied_read_names_the_path_and_prints_no_credentials(self):
        result, _ = self.run_helper("kv/workspace/r2/buckets/workspace-archives", settings={"AWS_TEST_DENY": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("kv/workspace/r2/buckets/workspace-archives", result.stderr)
        self.assertIn("docs/aws-cli.md", result.stderr)

    def test_missing_or_empty_fields_fail(self):
        for fields in ({"access_key_id": "AKID"}, {"access_key_id": "", "secret_access_key": "S"}, {"access_key_id": 1, "secret_access_key": "S"}):
            with self.subTest(fields=fields):
                result, _ = self.run_helper("kv/x", settings={"AWS_TEST_FIELDS": json.dumps(fields)})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("access_key_id and secret_access_key", result.stderr)

    def test_requires_exactly_one_path_and_help_reads_nothing(self):
        for args in ((), ("a", "b")):
            with self.subTest(args=args):
                result, calls = self.run_helper(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("usage", result.stderr)
                self.assertEqual(calls, [])
        result, calls = self.run_helper("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("credential_process", result.stdout)
        self.assertEqual(calls, [])

    @unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
    def test_config_has_a_profile_per_bucket_on_the_account_endpoint(self):
        config = self.root / "chezmoi.yaml"
        config.write_text("vault:\n  command: bao\n")
        self.log.write_text("")
        result = subprocess.run(
            ["chezmoi", "--config", str(config), "--source", str(REPO), "execute-template"],
            input=TEMPLATE.read_text(),
            env={**self.env, "HOME": str(self.root)},
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = configparser.ConfigParser()
        parsed.read_string(result.stdout)
        self.assertEqual(parsed["services r2"]["s3"].strip(), "endpoint_url = https://0123456789abcdef.r2.cloudflarestorage.com")
        for bucket in ("assets-wyrd-foo", "workspace-archives"):
            with self.subTest(bucket=bucket):
                profile = parsed[f"profile {bucket}"]
                self.assertEqual(profile["services"], "r2")
                self.assertEqual(profile["region"], "auto")
                self.assertEqual(
                    profile["credential_process"],
                    f"{self.root}/.local/bin/aws-bao-credentials kv/workspace/r2/buckets/{bucket}",
                )
                self.assertEqual(profile["request_checksum_calculation"], "when_required")
                self.assertEqual(profile["response_checksum_validation"], "when_required")


if __name__ == "__main__":
    unittest.main()
