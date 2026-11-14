"""Shell rc integration: the chezmoi modify scripts for rc files, the rc.d loader and the boat() function.

The modify scripts are rendered with chezmoi and fed example files on stdin. The function runs in real bash and
zsh against a fake ~/.local/bin/boat, without OpenBao or network access.
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
VENDOR_PATH = (
    "# ASCII BOAT SHELL INTEGRATION START boat\n"
    'case ":$PATH:" in\n  *":/home/u/.ascii/bin:"*) ;;\n  *) PATH="/home/u/.ascii/bin:$PATH" ;;\nesac\nexport PATH\n'
    "# ASCII BOAT SHELL INTEGRATION END boat\n"
)
VENDOR_FUNCTION = (
    "# ASCII BOAT SHELL INTEGRATION START boat\n"
    'boat() {\n  command "/home/u/.ascii/bin/boat" "$@"\n}\n'
    "# ASCII BOAT SHELL INTEGRATION END boat\n"
)
STOCK = "# ~/.bashrc: executed by bash(1) for non-login shells.\nalias ll='ls -l'\n"
# Writes what boat would write for the shell function to pick up, then exits with BOAT_TEST_RC.
FAKE_BOAT = r'''#!/bin/sh
echo "$@" >> "$HOME/calls"
case $1 in
  new) printf ' sbx_new\n' > "$BOAT_CURRENT_ID_FILE" ;;
  prompt) printf 'convo 1' > "$BOAT_CURRENT_CONVO_FILE" ;;
esac
exit "${BOAT_TEST_RC:-0}"
'''


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class RcModifyTests(unittest.TestCase):
    rendered = {}

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="shell-rc-test-")
        for name in ("bashrc", "zshrc", "profile", "zshenv"):
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

    def test_vendor_blocks_are_replaced_by_ours_and_the_rest_is_kept(self):
        before = VENDOR_PATH + "\n" + STOCK + "\n" + VENDOR_FUNCTION
        after, _ = self.modify("bashrc", before)
        self.assertEqual(after, STOCK + "\n" + OURS)
        again, _ = self.modify("bashrc", after)
        self.assertEqual(again, after, "a second apply changes nothing")

    def test_profile_and_zshenv_only_lose_the_vendor_blocks(self):
        for name in ("profile", "zshenv"):
            with self.subTest(name=name):
                after, _ = self.modify(name, STOCK + "\n" + VENDOR_PATH)
                self.assertEqual(after, STOCK + "\n")
                self.assertNotIn("workspace-dotfiles", after)

    def test_files_without_blocks_pass_through_byte_for_byte(self):
        for content in (STOCK, STOCK.rstrip("\n"), "", "a\n\n\n"):
            with self.subTest(content=content):
                self.assertEqual(self.modify("profile", content)[0], content)
                with_ours = content + ("\n" if content and not content.endswith("\n") else "") + OURS
                self.assertEqual(self.modify("zshrc", with_ours)[0], with_ours)

    def test_ours_is_appended_once_and_updated_in_place(self):
        self.assertEqual(self.modify("zshrc", "")[0], OURS)
        self.assertEqual(self.modify("zshrc", "x=1")[0], "x=1\n\n" + OURS)
        old = "# BEGIN workspace-dotfiles shell\nold line\n# END workspace-dotfiles shell\n"
        self.assertEqual(self.modify("zshrc", "a\n" + old + "b\n")[0], "a\n" + OURS + "b\n")

    def test_other_boat_modes_are_kept(self):
        dev = VENDOR_PATH.replace("END boat", "END boat-dev").replace("START boat", "START boat-dev")
        self.assertEqual(self.modify("profile", STOCK + dev)[0], STOCK + dev)

    def test_crossed_or_nested_markers_leave_the_file_unchanged(self):
        begin, end = "# BEGIN workspace-dotfiles shell\n", "# END workspace-dotfiles shell\n"
        start, stop = "# ASCII BOAT SHELL INTEGRATION START boat\n", "# ASCII BOAT SHELL INTEGRATION END boat\n"
        for layout in (begin + start + end + stop, start + begin + stop + end,
                       begin + start + stop + end, start + begin + end + stop,
                       begin + start + stop, start + begin + end):
            content = STOCK + layout + "alias keep=1\n"
            with self.subTest(layout=layout):
                for name in ("bashrc", "profile"):
                    after, err = self.modify(name, content)
                    self.assertEqual(after, content)
                    self.assertIn("unbalanced", err)

    def test_duplicate_blocks_become_one_and_stay_one(self):
        after, _ = self.modify("zshrc", OURS + "alias keep=1\n" + OURS + "alias also=1\n")
        self.assertEqual(after, OURS + "alias keep=1\nalias also=1\n")
        self.assertEqual(self.modify("zshrc", after)[0], after)
        stripped, _ = self.modify("profile", "a\n" + OURS + "b\n")
        self.assertEqual(stripped, "a\nb\n", "the block belongs only in ~/.bashrc and ~/.zshrc")

    def test_unbalanced_markers_leave_the_file_unchanged(self):
        for content in (STOCK + VENDOR_PATH.rsplit("# ASCII", 1)[0] + "alias keep=1\n",
                        STOCK + "# END workspace-dotfiles shell\n",
                        STOCK + "# ASCII BOAT SHELL INTEGRATION END boat\n"):
            with self.subTest(content=content):
                after, err = self.modify("bashrc", content)
                self.assertEqual(after, content)
                self.assertIn("unbalanced", err)


class BoatFunctionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="boat-function-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        shell_dir = self.home / ".config/shell"
        (shell_dir / "rc.d").mkdir(parents=True)
        shutil.copy(REPO / "dot_config/shell/rc.sh", shell_dir / "rc.sh")
        shutil.copy(REPO / "dot_config/shell/rc.d/boat.sh", shell_dir / "rc.d/boat.sh")
        wrapper = self.home / ".local/bin/boat"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text(FAKE_BOAT)
        wrapper.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("BOAT_")}
        self.env.update(HOME=str(self.home), TMPDIR=str(self.home / "tmp"))
        (self.home / "tmp").mkdir()

    def shell(self, shell, script, settings=None):
        result = subprocess.run(
            [shell, "-c", '. "$HOME/.config/shell/rc.sh"\n' + script],
            env={**self.env, **(settings or {})}, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.stderr, "")
        return result

    def shells(self):
        found = [shell for shell in ("bash", "zsh") if shutil.which(shell)]
        self.assertIn("bash", found)
        return found

    def test_new_and_prompt_set_the_current_ids_in_the_shell(self):
        for shell in self.shells():
            with self.subTest(shell=shell):
                result = self.shell(shell, 'set -u\nboat new --name "a b"\nboat prompt hi\n'
                                    'echo "id=$BOAT_CURRENT_ID convo=$BOAT_CURRENT_CONVO file=${BOAT_CURRENT_ID_FILE-unset}"')
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout.strip(), "id=sbx_new convo=convo 1 file=unset")
                self.assertEqual(list((self.home / "tmp").iterdir()), [], "temporary files are removed")
                self.assertEqual((self.home / "calls").read_text().splitlines()[-2:], ["new --name a b", "prompt hi"])

    def test_failure_keeps_the_exit_code_and_sets_nothing(self):
        for shell in self.shells():
            with self.subTest(shell=shell):
                result = self.shell(shell, 'boat new; echo "rc=$? id=${BOAT_CURRENT_ID-unset}"', {"BOAT_TEST_RC": "3"})
                self.assertEqual(result.stdout.strip(), "rc=3 id=unset")



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
