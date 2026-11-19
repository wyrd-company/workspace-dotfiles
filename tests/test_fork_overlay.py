"""Render the harness instructions and data with and without the fork overlay.

Each test copies the source to a temporary directory, renders into a separate destination under a temporary HOME
and never touches the running home directory.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CORE = (REPO / ".includes/CORE-INSTRUCTIONS.md").read_text()
# Harness file in the source, its target in the destination, and whether `chezmoi apply` can write it.
HARNESSES = {
    "claude": ("dot_claude/CLAUDE.md.tmpl", ".claude/CLAUDE.md", True),
    "codex": ("dot_codex/AGENTS.md.tmpl", ".codex/AGENTS.md", True),
    "pi": ("dot_pi/agent/AGENTS.md.tmpl", ".pi/agent/AGENTS.md", True),
    # .chezmoiignore skips .grok until there is access, so render its template directly.
    "grok": ("dot_grok/AGENTS.md.tmpl", None, False),
}
OPERATORS = "operators:\n  - handle: forkop\n    name: Fork Operator\n    github_pubkey: ssh-ed25519 AAAA forkop\n"


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class ForkOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fork-overlay-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        shutil.copytree(REPO, self.source, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        self.home = self.root / "home"
        self.home.mkdir()
        self.dest = self.root / "dest"
        self.dest.mkdir()
        self.env = {**os.environ, "HOME": str(self.home)}
        self.fork_includes = self.source / ".includes/fork"
        self.fork_data = self.source / ".chezmoidata/zz-fork"

    def chezmoi(self, *args, stdin=None):
        result = subprocess.run(
            ["chezmoi", "--source", str(self.source), "--destination", str(self.dest), *args],
            input=stdin, env=self.env, text=True, capture_output=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def render(self, harness):
        template, target, applies = HARNESSES[harness]
        if not applies:
            return self.chezmoi("execute-template", stdin=(self.source / template).read_text())
        path = self.dest / target
        self.chezmoi("apply", "--parent-dirs", str(path))
        return path.read_text()

    def unchanged(self, harness):
        """What the harness file rendered before the overlay: core, a blank line, then the harness text."""
        template = (REPO / HARNESSES[harness][0]).read_text().split("\n", 1)[1]
        return CORE + "\n" + template

    def write_notes(self):
        self.fork_includes.mkdir(parents=True)
        (self.fork_includes / "20-second.md").write_text("Second note.\n\n")
        (self.fork_includes / "10-first.md").write_text("First note.\nBob prefers short answers.\n")

    def test_without_fork_files_the_harness_files_are_unchanged(self):
        for harness in HARNESSES:
            with self.subTest(harness=harness):
                self.assertEqual(self.render(harness), self.unchanged(harness))

    def test_an_empty_fork_directory_changes_nothing(self):
        self.fork_includes.mkdir(parents=True)
        (self.fork_includes / "README.txt").write_text("not markdown")
        for harness in HARNESSES:
            with self.subTest(harness=harness):
                self.assertEqual(self.render(harness), self.unchanged(harness))

    def test_fork_instructions_follow_the_core_in_sorted_order_in_all_harnesses(self):
        self.write_notes()
        block = "</core-instructions>\n\n<fork-instructions>\nFirst note.\nBob prefers short answers.\nSecond note.\n</fork-instructions>\n\n"
        for harness in HARNESSES:
            with self.subTest(harness=harness):
                output = self.render(harness)
                self.assertTrue(output.startswith(CORE), "core instructions come first")
                self.assertIn(block, output)
                self.assertEqual(output.count("<fork-instructions>"), 1)
                rest = (REPO / HARNESSES[harness][0]).read_text().split("\n", 1)[1]
                self.assertTrue(output.endswith(rest), "harness text still follows")

    def test_fork_notes_are_not_managed_files(self):
        self.write_notes()
        self.fork_data.mkdir(parents=True)
        (self.fork_data / "operators.yml").write_text(OPERATORS)
        managed = self.chezmoi("managed")
        self.assertNotIn("fork", managed)
        self.assertNotIn(".includes", managed)

    def operators(self):
        return json.loads(self.chezmoi("data", "--format", "json"))["operators"]

    def test_an_operators_override_replaces_the_list(self):
        upstream = self.operators()
        self.assertGreater(len(upstream), 1)
        self.fork_data.mkdir(parents=True)
        (self.fork_data / "operators.yml").write_text(OPERATORS)
        self.assertEqual(
            self.operators(),
            [{"handle": "forkop", "name": "Fork Operator", "github_pubkey": "ssh-ed25519 AAAA forkop"}],
        )

    def test_a_map_override_merges_with_upstream(self):
        self.fork_data.mkdir(parents=True)
        (self.fork_data / "deck.yml").write_text("deck:\n  default_channel: forks/1\n")
        data = json.loads(self.chezmoi("data", "--format", "json"))
        self.assertEqual(data["deck"]["default_channel"], "forks/1")
        self.assertIn("host_key", data["deck"])


if __name__ == "__main__":
    unittest.main()
