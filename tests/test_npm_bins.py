"""Run run_after_npm-bins.sh against a fake npm global prefix in a temporary HOME."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "run_after_npm-bins.sh"


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class NpmBinsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="npm-bins-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.home = root / "home"
        self.local_bin = self.home / ".local/bin"
        self.prefix = root / "npm-global"
        self.npm_bin = self.prefix / "bin"
        self.npm_bin.mkdir(parents=True)
        self.env = dict(os.environ, HOME=str(self.home), NPM_CONFIG_PREFIX=str(self.prefix))

    def package(self, name, bin_field):
        directory = self.prefix / "lib/node_modules" / name
        directory.mkdir(parents=True)
        (directory / "package.json").write_text(json.dumps({"name": name, "bin": bin_field}))
        commands = [name.split("/")[-1]] if isinstance(bin_field, str) else list(bin_field)
        for command in commands:
            (self.npm_bin / command).symlink_to(directory / "package.json")

    def run_script(self, *packages):
        self.home.mkdir(exist_ok=True)
        (self.home / ".npm-packages").write_text("".join(f"{p}\n" for p in packages))
        return subprocess.run(["bash", str(SCRIPT)], env=self.env, capture_output=True, text=True)

    def links(self):
        return {p.name: os.readlink(p) for p in self.local_bin.iterdir() if p.is_symlink()}

    def test_links_string_and_object_bins(self):
        self.package("plain", "cli.js")
        self.package("@scope/tool", "bin/tool.js")
        self.package("multi", {"one": "a.js", "two": "b.js"})
        result = self.run_script("plain", "@scope/tool@latest", "multi@1.2.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.links(),
            {name: str(self.npm_bin / name) for name in ("plain", "tool", "one", "two")},
        )

    def test_does_not_link_unlisted_packages(self):
        self.package("listed", "cli.js")
        self.package("other", "cli.js")
        self.run_script("listed")
        self.assertEqual(set(self.links()), {"listed"})

    def test_removes_links_for_packages_no_longer_listed(self):
        self.package("kept", "cli.js")
        self.package("dropped", "cli.js")
        self.run_script("kept", "dropped")
        result = self.run_script("kept")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(self.links()), {"kept"})

    def test_leaves_existing_files_and_foreign_links(self):
        self.package("gh", "cli.js")
        self.package("boat", "cli.js")
        self.local_bin.mkdir(parents=True)
        (self.local_bin / "gh").write_text("#!/bin/sh\n")
        (self.local_bin / "boat").symlink_to("/elsewhere/boat")
        result = self.run_script("gh", "boat")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.local_bin / "gh").is_symlink())
        self.assertEqual(os.readlink(self.local_bin / "boat"), "/elsewhere/boat")
        self.assertIn("already exists", result.stderr)

    def test_missing_package_fails_after_linking_the_rest(self):
        self.package("present", "cli.js")
        result = self.run_script("absent", "present")
        self.assertEqual(result.returncode, 1)
        self.assertIn("absent is not installed", result.stderr)
        self.assertEqual(set(self.links()), {"present"})

    def test_is_idempotent(self):
        self.package("plain", "cli.js")
        self.run_script("plain")
        result = self.run_script("plain")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.links(), {"plain": str(self.npm_bin / "plain")})


if __name__ == "__main__":
    unittest.main()
