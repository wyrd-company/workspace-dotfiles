"""Render the Deck client config without OpenBao, the Deck service or the real workspace options."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "dot_config/deck/config.yml.tmpl"
IGNORE = REPO / ".chezmoiignore"
HOST_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOpOs2okPTF0d06WZveRMcp0ceUWeO2jllkuCtP2YhX6 deck.internal"


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class DeckConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="deck-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.options = self.root / "workspace.yml"
        self.options.write_text("workspace: test-ws\n")

    def render(self, template, host_key=HOST_KEY, default_channel="", options=None):
        config = self.root / "chezmoi.yaml"
        config.write_text(
            "data:\n  deck:\n"
            f"    host_key: {host_key!r}\n"
            f"    default_channel: {default_channel!r}\n"
            f"    workspace_config: {str(options or self.options)!r}\n"
        )
        return subprocess.run(
            ["chezmoi", "--config", str(config), "--source", str(REPO), "execute-template"],
            input=template.read_text(),
            env={**os.environ, "HOME": str(self.root)},
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_names_the_workspace_key_and_keeps_the_store_in_state(self):
        result = self.render(TEMPLATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('address: "deck.internal:2222"', result.stdout)
        self.assertIn(f'host_key: "{HOST_KEY}"', result.stdout)
        self.assertIn('name: "deck-test-ws"', result.stdout)
        self.assertIn(f'path: "{self.root}/.local/share/deck/deck.db"', result.stdout)
        self.assertNotIn("channels:", result.stdout)

    def test_default_channel_only_when_set(self):
        result = self.render(TEMPLATE, default_channel="wyrdbot/1287000000000000002")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('default: "wyrdbot/1287000000000000002"', result.stdout)

    def test_mention_aliases_render_as_quoted_ids(self):
        result = self.render(TEMPLATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r'\naliases:\n  users:\n(    [a-z][a-z0-9-]*: "[0-9]+"\n)+  roles:\n')

    def test_a_workspace_without_a_name_fails(self):
        options = self.root / "unnamed.yml"
        options.write_text("org: example\n")
        result = self.render(TEMPLATE, options=options)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workspace is required", result.stderr)

    def test_no_config_until_the_host_key_is_known(self):
        ignored = self.render(IGNORE, host_key="")
        self.assertEqual(ignored.returncode, 0, ignored.stderr)
        self.assertIn(".config/deck", ignored.stdout.splitlines())
        kept = self.render(IGNORE)
        self.assertNotIn(".config/deck", kept.stdout.splitlines())

    @unittest.skipUnless(shutil.which("deck"), "deck is not installed")
    def test_deck_accepts_the_config(self):
        result = self.render(TEMPLATE, default_channel="wyrdbot/1287000000000000002")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.root / "config.yml"
        path.write_text(result.stdout)
        check = subprocess.run(["deck", "config", "validate", "--config", str(path)], text=True, capture_output=True, timeout=30)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == "__main__":
    unittest.main()
