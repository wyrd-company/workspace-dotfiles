"""Render the Seek client config without OpenBao or the Seek server."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "dot_config/seek/client.yml.tmpl"
IGNORE = REPO / ".chezmoiignore"


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class SeekConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="seek-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def render(self, template, url="https://seek.internal"):
        config = self.root / "chezmoi.yaml"
        config.write_text(f"data:\n  seek:\n    url: {url!r}\n")
        return subprocess.run(
            ["chezmoi", "--config", str(config), "--source", str(REPO), "execute-template"],
            input=template.read_text(),
            env={**os.environ, "HOME": str(self.root)},
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_reads_the_token_through_the_wyrwood_socket_without_a_login(self):
        result = self.render(TEMPLATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('url: "https://seek.internal"', result.stdout)
        self.assertRegex(
            result.stdout,
            r'  token:\n    vault:\n      address: unix:///run/wyrwood/vault.sock\n      auth:\n        mode: none\n'
            r'      mount: "kv"\n      path: "workspace/seek"\n      key: "token"\n',
        )

    def test_no_config_until_a_server_is_named(self):
        ignored = self.render(IGNORE, url="")
        self.assertEqual(ignored.returncode, 0, ignored.stderr)
        self.assertIn(".config/seek", ignored.stdout.splitlines())
        kept = self.render(IGNORE)
        self.assertNotIn(".config/seek", kept.stdout.splitlines())

    @unittest.skipUnless(shutil.which("seek"), "seek is not installed")
    def test_seek_accepts_the_config(self):
        result = self.render(TEMPLATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.root / "seek").mkdir()
        (self.root / "seek/client.yml").write_text(result.stdout)
        env = {**os.environ, "XDG_CONFIG_HOME": str(self.root)}
        version = subprocess.run(["seek", "--version"], text=True, capture_output=True, timeout=30, env=env)
        if tuple(int(part) for part in version.stdout.strip().split(".")[:2]) < (0, 4):
            self.skipTest(f"seek {version.stdout.strip()} predates client.yml")
        check = subprocess.run(["seek", "config", "validate"], text=True, capture_output=True, timeout=30, env=env)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == "__main__":
    unittest.main()
