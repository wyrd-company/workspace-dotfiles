"""Test the Antigravity hook wrapper and the T3 profile linker in a temporary HOME."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
LINKER = REPO / "run_after_link-antigravity-t3-profile.sh"
HOOK = REPO / "dot_local/bin/executable_agy-git-operator-hook"
MCP_TEMPLATE = REPO / "dot_gemini/config/modify_mcp_config.json"


class LinkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="antigravity-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.gemini = self.home / ".gemini"
        (self.gemini / "config/skills").mkdir(parents=True)
        (self.gemini / "AGENTS.md").write_text("instructions\n")
        (self.gemini / "config/mcp_config.json").write_text("{}\n")
        (self.gemini / "config/hooks.json").write_text("{}\n")
        self.providers = self.home / ".t3/userdata/providers/antigravity"

    def profile(self, name):
        directory = self.providers / name
        (directory / "config").mkdir(parents=True)
        return directory

    def run_linker(self):
        return subprocess.run(["bash", str(LINKER)], env=dict(os.environ, HOME=str(self.home)),
                              capture_output=True, text=True, check=True)

    def test_no_provider_directory_is_a_no_op(self):
        self.run_linker()
        self.assertFalse(self.providers.exists())

    def test_links_the_shared_entries_and_is_idempotent(self):
        profile = self.profile("abc")
        (profile / "config/config.json").write_text('{"plugins": {}}\n')
        self.run_linker()
        self.run_linker()
        self.assertEqual((profile / "AGENTS.md").resolve(), (self.gemini / "AGENTS.md").resolve())
        for entry in ("mcp_config.json", "hooks.json", "skills"):
            self.assertTrue((profile / "config" / entry).is_symlink(), entry)
            self.assertEqual((profile / "config" / entry).resolve(), (self.gemini / "config" / entry).resolve())
        self.assertFalse((profile / "config/config.json").is_symlink())
        self.assertFalse((profile / "config/projects").exists())

    def test_replaces_an_empty_file_but_keeps_a_real_one(self):
        profile = self.profile("abc")
        (profile / "config/mcp_config.json").write_text("")
        (profile / "config/hooks.json").write_text('{"mine": true}\n')
        result = self.run_linker()
        self.assertTrue((profile / "config/mcp_config.json").is_symlink())
        self.assertFalse((profile / "config/hooks.json").is_symlink())
        self.assertEqual(json.loads((profile / "config/hooks.json").read_text()), {"mine": True})
        self.assertIn("hooks.json exists; leaving it", result.stderr)

    def test_skips_a_missing_source(self):
        (self.gemini / "AGENTS.md").unlink()
        profile = self.profile("abc")
        self.run_linker()
        self.assertFalse((profile / "AGENTS.md").exists() or (profile / "AGENTS.md").is_symlink())


@unittest.skipUnless(shutil.which("jq"), "jq is not installed")
class HookTests(unittest.TestCase):
    def test_prints_a_json_object_the_agent_can_inject(self):
        result = subprocess.run([str(HOOK)], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertIsInstance(data, dict)
        steps = data.get("injectSteps")
        if steps is not None:
            self.assertTrue(all(isinstance(step.get("userMessage"), str) for step in steps))


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class McpConfigTemplateTests(unittest.TestCase):
    def render(self, stdin_text):
        result = subprocess.run(
            ["chezmoi", "execute-template", "--with-stdin", "--file", str(MCP_TEMPLATE)],
            input=stdin_text,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def test_adds_mnemonic_and_xolotl_while_preserving_user_servers(self):
        existing = json.dumps({"mcpServers": {"custom": {"url": "https://example.test/mcp"}}})
        rendered = json.loads(self.render(existing))
        servers = rendered["mcpServers"]
        self.assertEqual(servers["custom"], {"url": "https://example.test/mcp"})
        self.assertEqual(servers["xolotl"], {"url": "http://127.0.0.1:18317/mcp"})
        self.assertEqual(servers["mnemonic"]["command"], "sh")

    def test_is_idempotent_when_unchanged(self):
        first = self.render("")
        second = self.render(first)
        self.assertEqual(second, first)


if __name__ == "__main__":
    unittest.main()
