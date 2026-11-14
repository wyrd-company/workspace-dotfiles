"""Shell rc integration: the chezmoi modify scripts for rc files and the rc.d loader.

The modify scripts are rendered with chezmoi and fed example files on stdin; the loader runs in real bash and zsh.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
OURS = (
    "# BEGIN workspace-dotfiles shell\n"
    "# Managed by chezmoi (workspace-dotfiles): sources ~/.config/shell/rc.d/*.sh. See docs/shell.md.\n"
    'if [ -r "$HOME/.config/shell/rc.sh" ]; then . "$HOME/.config/shell/rc.sh"; fi\n'
    "# END workspace-dotfiles shell\n"
)
STOCK = "# ~/.bashrc: executed by bash(1) for non-login shells.\nalias ll='ls -l'\n"


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class RcModifyTests(unittest.TestCase):
    rendered = {}

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="shell-rc-test-")
        for name in ("bashrc", "zshrc"):
            result = subprocess.run(
                ["chezmoi", "--source", str(REPO), "execute-template"],
                input=(REPO / f"modify_dot_{name}.tmpl").read_text(), text=True, capture_output=True, timeout=30,
            )
            assert result.returncode == 0, result.stderr
            script = Path(cls.temp.name) / name
            script.write_text(result.stdout)
            cls.rendered[name] = script

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def modify(self, name, content):
        result = subprocess.run(
            ["bash", str(self.rendered[name])], input=content.encode(), capture_output=True, timeout=10
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.decode(), result.stderr.decode()

    def test_files_without_blocks_pass_through_byte_for_byte(self):
        for content in (STOCK, STOCK.rstrip("\n"), "", "a\n\n\n"):
            with self.subTest(content=content):
                with_ours = content + ("\n" if content and not content.endswith("\n") else "") + OURS
                self.assertEqual(self.modify("zshrc", with_ours)[0], with_ours)

    def test_ours_is_appended_once_and_updated_in_place(self):
        self.assertEqual(self.modify("zshrc", "")[0], OURS)
        self.assertEqual(self.modify("zshrc", "x=1")[0], "x=1\n\n" + OURS)
        old = "# BEGIN workspace-dotfiles shell\nold line\n# END workspace-dotfiles shell\n"
        self.assertEqual(self.modify("zshrc", "a\n" + old + "b\n")[0], "a\n" + OURS + "b\n")

    def test_unbalanced_markers_leave_the_file_unchanged(self):
        for content in (STOCK + "# BEGIN workspace-dotfiles shell\nalias keep=1\n",
                        STOCK + "# END workspace-dotfiles shell\n"):
            with self.subTest(content=content):
                after, err = self.modify("bashrc", content)
                self.assertEqual(after, content)
                self.assertIn("unbalanced", err)


class LoaderTests(unittest.TestCase):
    def test_sources_rc_d_files_and_is_quiet_without_any(self):
        with tempfile.TemporaryDirectory(prefix="shell-loader-test-") as temp:
            home = Path(temp)
            (home / ".config/shell/rc.d").mkdir(parents=True)
            shutil.copy(REPO / "dot_config/shell/rc.sh", home / ".config/shell/rc.sh")
            env = {**os.environ, "HOME": str(home)}
            for shell in [shell for shell in ("bash", "zsh") if shutil.which(shell)]:
                with self.subTest(shell=shell, files="none"):
                    result = subprocess.run([shell, "-c", '. "$HOME/.config/shell/rc.sh"; echo ok'],
                                            env=env, text=True, capture_output=True, timeout=10)
                    self.assertEqual((result.stdout, result.stderr), ("ok\n", ""))
                (home / ".config/shell/rc.d/a.sh").write_text("hello() { echo hi; }\n")
                (home / ".config/shell/rc.d/b.txt").write_text("echo not sourced\n")
                with self.subTest(shell=shell, files="some"):
                    result = subprocess.run([shell, "-c", '. "$HOME/.config/shell/rc.sh"; hello; echo "${_rc_d_file-unset}"'],
                                            env=env, text=True, capture_output=True, timeout=10)
                    self.assertEqual((result.stdout, result.stderr), ("hi\nunset\n", ""))
                (home / ".config/shell/rc.d/a.sh").unlink()
                (home / ".config/shell/rc.d/b.txt").unlink()


if __name__ == "__main__":
    unittest.main()
