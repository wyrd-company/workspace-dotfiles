"""Exercise the real Git shim in isolated homes and local repositories; no network or keys."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
# Resolve before placing the shim on the test PATH.
REAL_GIT = subprocess.check_output(["git", "--exec-path"], text=True).strip() + "/git"


class GitOperatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="git-operator-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("git", "git-as", "git-operator", "git-ssh-guard"):
            target = self.bin / name
            shutil.copyfile(ROOT / "dot_local/bin" / ("executable_" + name), target)
            target.chmod(0o755)
        (self.bin / "git-person").symlink_to("git-as")
        self.home = self.root / "home"
        home_bin = self.home / ".local/bin"
        home_bin.mkdir(parents=True)
        (home_bin / "git").symlink_to(self.bin / "git")
        operators = self.home / ".config/git/operators"
        operators.mkdir(parents=True)
        (operators / "person").write_text(
            'OP_NAME="Selected Person"\nOP_EMAIL_DEFAULT="selected@example.test"\n'
            'OP_EMAIL_WYRD_COMPANY="company@example.test"\n'
            'OP_PUBKEY="$HOME/.ssh/person.pub"\n'
        )
        # Reproduce the bug: a global identity exists, but nobody selected its owner.
        (self.home / ".gitconfig").write_text(
            '[user]\nname = Stale Person\nemail = stale@example.test\nuseConfigOnly = true\n'
            f'[core]\nsshCommand = {self.bin / "git-ssh-guard"}\n'
        )
        self.env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("GIT_", "T3CODE_", "WYRD_", "XDG_"))
        }
        self.env.update(
            HOME=str(self.home),
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            WYRD_REAL_GIT=REAL_GIT,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_EDITOR="true",
            GIT_SEQUENCE_EDITOR="true",
        )
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.run_git("init", "-q", "-b", "main", check=True)
        self.run_git("commit", "--allow-empty", "-qm", "initial", operator=True, check=True)
        self.remote = self.root / "remote.git"
        self.run_git("clone", "--bare", str(self.repo), str(self.remote), check=True)
        self.run_git("remote", "add", "origin", str(self.remote), check=True)

    def run_git(self, *args, operator=False, thread=False, settings=None, check=False):
        env = {**self.env, **(settings or {})}
        if thread:
            env["T3CODE_THREAD_ID"] = "test-thread"
        if operator:
            env["GIT_OPERATOR"] = "person"
        return subprocess.run(
            [str(self.bin / "git"), *args], cwd=self.repo, env=env,
            text=True, capture_output=True, check=check, timeout=10,
        )

    def assert_requires_operator(self, *args, **kwargs):
        result = self.run_git(*args, **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("operator", result.stderr.lower())
        return result

    def test_terminal_and_thread_commits_cannot_use_global_or_environment_identity(self):
        before = self.run_git("rev-parse", "HEAD", check=True).stdout
        for thread in (False, True):
            with self.subTest(thread=thread):
                self.assert_requires_operator(
                    "-c", "user.name=Override", "commit", "--allow-empty", "-m", "blocked",
                    thread=thread,
                    settings={"GIT_COMMITTER_NAME": "Override", "GIT_COMMITTER_EMAIL": "override@example.test"},
                )
        self.assertEqual(self.run_git("rev-parse", "HEAD").stdout, before)

    def test_indirect_commit_creation_requires_operator(self):
        commands = (
            ("commit-tree", "HEAD^{tree}"), ("merge", "main"), ("pull",), ("rebase", "main"),
            ("cherry-pick", "HEAD"), ("revert", "HEAD"), ("am",), ("am", "--skip"),
            ("stash",), ("stash", "push"), ("stash", "create"), ("stash", "export", "--print"),
            ("notes", "add", "-m", "note"), ("notes", "remove", "HEAD"),
            ("fast-import",), ("filter-branch",), ("replay",),
            ("replace", "--graft", "HEAD"), ("submodule", "update", "--merge"),
            ("hash-object", "-w", "-t", "commit", "--stdin"),
            ("pull", "--no-commit"),
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_requires_operator(*command)

    def test_pushes_require_operator_for_every_transport_and_plumbing(self):
        for command in ("push", "send-pack"):
            for destination in (str(self.remote), "https://example.test/repo", "git@example.test:repo"):
                with self.subTest(command=command, destination=destination):
                    self.assert_requires_operator(command, "--dry-run", destination, "HEAD")

    def test_reads_and_workspace_operations_need_no_operator(self):
        commands = (
            ("status", "--short"), ("log", "-1", "--oneline"), ("diff",),
            ("fetch", "origin"), ("ls-remote", "origin"), ("remote", "update"),
            ("branch", "other"), ("switch", "other"), ("tag", "lightweight"),
            ("tag", "-a", "annotated", "-m", "tag"), ("stash", "list"),
            ("stash", "clear"), ("notes", "list"), ("notes", "get-ref"),
            ("notes", "--ref", "other-notes", "list"),
            ("submodule", "update", "--init"), ("merge", "--ff-only", "main"),
            ("pull", "--ff-only", "origin", "main"),
            ("clone", str(self.remote), str(self.root / "clone")),
        )
        for command in commands:
            with self.subTest(command=command):
                result = self.run_git(*command, thread=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_recovery_and_inspection_modes_do_not_require_operator(self):
        for command in (
            ("merge", "--abort"), ("rebase", "--abort"), ("rebase", "--quit"),
            ("cherry-pick", "--abort"), ("revert", "--abort"), ("am", "--abort"),
            ("rebase", "--edit-todo"), ("am", "--show-current-patch"),
            ("commit", "--dry-run"), ("commit", "-h"),
        ):
            with self.subTest(command=command):
                result = self.run_git(*command, thread=True)
                self.assertNotIn("operator", result.stderr)

    def test_no_commit_modes_preserve_head(self):
        (self.repo / "file").write_text("change\n")
        self.run_git("add", "file", check=True)
        self.run_git("commit", "-qm", "change", operator=True, check=True)
        before = self.run_git("rev-parse", "HEAD").stdout
        result = self.run_git("revert", "--no-commit", "HEAD", thread=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_git("rev-parse", "HEAD").stdout, before)

    def test_aliases_cannot_hide_commit_creation_or_pushes(self):
        for alias in (
            "commit --allow-empty -m 'quoted message'", "push --dry-run origin HEAD",
            "-c color.ui=false commit --allow-empty -m blocked", "stash push",
            "-c alias.inner=commit inner --allow-empty -m blocked",
        ):
            with self.subTest(alias=alias):
                self.assert_requires_operator("-c", "alias.test=" + alias, "test")
        self.run_git("config", "alias.first", "second", check=True)
        self.run_git("config", "alias.second", "commit --allow-empty -m blocked", check=True)
        self.assert_requires_operator("first")
        self.assert_requires_operator("-c", "alias.new.command=commit --allow-empty -m blocked", "new")
        # New and legacy spellings use config order, rather than one always taking precedence.
        self.assert_requires_operator(
            "-c", "alias.new=status", "-c", "alias.new.command=commit --allow-empty -m blocked", "new",
        )
        self.assert_requires_operator(
            "-c", "alias.new.command=status", "-c", "alias.new=commit --allow-empty -m blocked", "new",
        )

    def test_alias_quoting_and_read_aliases_keep_git_semantics(self):
        self.run_git("config", "alias.make", "commit --allow-empty -m 'quoted message'", check=True)
        result = self.run_git("make", operator=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_git("log", "-1", "--format=%s").stdout.strip(), "quoted message")
        result = self.run_git("-c", "alias.read=-c color.ui=false status --short", "read", thread=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shell_aliases_reenter_the_shim(self):
        for body in (
            "!git commit --allow-empty -m blocked",
            "!f() { git push --dry-run origin HEAD; }; f",
        ):
            with self.subTest(body=body):
                self.assert_requires_operator("-c", "alias.test=" + body, "test")
        self.assert_requires_operator(
            "-c", 'alias.outer=-c "alias.inner=!git commit --allow-empty -m blocked" inner', "outer",
        )
        result = self.run_git("-c", "alias.read=!git status --short", "read", thread=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_option_values_and_overrides_cannot_hide_commit_creation(self):
        commands = (
            ("commit", "--allow-empty", "-m", "--dry-run"),
            ("commit", "--allow-empty", "-m", "--help"),
            ("commit", "--allow-empty", "--mess", "--dry-run"),
            ("commit", "--allow-empty", "--dry-run", "--no-dry-run", "-m", "blocked"),
            ("commit", "--allow-empty", "--dry-run=false", "-m", "blocked"),
            ("merge", "--no-commit", "--squash", "--commit", "main"),
            ("merge", "--no-commit", "--comm", "main"),
            ("merge", "--no-commit=false", "main"),
            ("merge", "--ff-only", "--no-ff", "main"),
            ("merge", "--ff-only", "--no-ff-only", "main"),
            ("merge", "--abort", "--no-abort", "main"),
            ("pull", "--ff-only", "--rebase=true"),
            ("hash-object", "-tcommit", "-w", "--stdin"),
            ("hash-object", "-wtcommit", "--stdin"),
            ("commit-tree", "HEAD^{tree}", "-m", "--help"),
            ("commit-tree", "HEAD^{tree}", "-F", "--help"),
            ("am", "--resolvemsg", "--help"),
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_requires_operator(*command)

    def test_for_each_repo_cannot_commit_with_inherited_global_identity(self):
        self.run_git("config", "test.repos", str(self.repo), check=True)
        before = self.run_git("rev-parse", "HEAD").stdout
        result = self.run_git(
            "for-each-repo", "--config=test.repos", "commit", "--allow-empty", "-m", "blocked",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("operator", result.stderr)
        self.assertEqual(self.run_git("rev-parse", "HEAD").stdout, before)
        self.run_git("for-each-repo", "--config=test.repos", "status", "--short", check=True)
        for command in (("fast-import",), ("send-pack", str(self.remote), "HEAD")):
            self.assert_requires_operator("for-each-repo", "--config=test.repos", *command)
        self.run_git(
            "for-each-repo", "--config=test.repos", "commit", "--allow-empty", "-qm", "selected",
            operator=True, check=True,
        )

    def test_submodule_foreach_checks_nested_git_and_preserves_shell_arguments(self):
        self.run_git("-c", "protocol.file.allow=always", "submodule", "add", str(self.remote), "child", check=True)
        self.run_git("commit", "-qm", "add child", operator=True, check=True)
        for command in (
            ("git commit --allow-empty -m blocked",),
            ("git", "commit", "--allow-empty", "-m", "blocked"),
            ("git fast-import",),
            ("git push --dry-run origin HEAD",),
        ):
            with self.subTest(command=command):
                self.assert_requires_operator("submodule", "foreach", *command)
        self.run_git("submodule", "foreach", "--recursive", "git", "status", "--short", check=True)
        self.run_git("submodule", "foreach", "git tag -a allowed -m 'tag message'", check=True)
        self.run_git("submodule", "--quiet", "foreach", "git tag -a also-allowed -m 'tag message'", check=True)
        self.run_git(
            "submodule", "foreach", "git", "commit", "--allow-empty", "-qm", "selected",
            operator=True, check=True,
        )

    def test_global_options_and_config_env_do_not_hide_commits(self):
        for prefix, settings in (
            (["-C", str(self.repo)], {}), (["-C" + str(self.repo)], {}),
            (["-cuser.name=Override"], {}),
            (["--config-env", "user.name=TEST_NAME"], {"TEST_NAME": "Override"}),
        ):
            with self.subTest(prefix=prefix):
                self.assert_requires_operator(*prefix, "commit", "--allow-empty", "-m", "blocked", settings=settings)

    def test_registered_thread_and_terminal_wrapper_apply_selected_identity(self):
        self.run_git("operator", "set", "person", thread=True, check=True)
        stale_env = {
            "GIT_COMMITTER_NAME": "Wrong", "GIT_COMMITTER_EMAIL": "wrong@example.test",
            "GIT_AUTHOR_NAME": "Wrong", "GIT_AUTHOR_EMAIL": "wrong@example.test",
        }
        result = self.run_git(
            "-c", "user.name=Wrong", "-c", "user.email=wrong@example.test",
            "commit", "--allow-empty", "-qm", "registered", thread=True, settings=stale_env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_git("log", "-1", "--format=%an|%ae|%cn|%ce")
        self.assertEqual(result.stdout.strip(), "Selected Person|selected@example.test|Selected Person|selected@example.test")
        self.run_git("person", "commit", "--allow-empty", "-qm", "terminal", check=True)

    def test_original_author_is_preserved_but_committer_is_selected(self):
        self.run_git(
            "commit", "--allow-empty", "--author=Original Author <original@example.test>",
            "-qm", "authored", operator=True, check=True,
        )
        result = self.run_git("log", "-1", "--format=%an|%ae|%cn|%ce")
        self.assertEqual(result.stdout.strip(), "Original Author|original@example.test|Selected Person|selected@example.test")

    def test_operator_push_and_owner_email(self):
        self.run_git("push", "origin", "HEAD", operator=True, check=True)
        self.run_git("remote", "set-url", "origin", "git@github.com:wyrd-company/example.git", check=True)
        self.run_git("commit", "--allow-empty", "-qm", "owner", operator=True, check=True)
        self.assertEqual(self.run_git("log", "-1", "--format=%ce").stdout.strip(), "company@example.test")

    def test_selected_ssh_key_overrides_stale_environment_and_config(self):
        ssh = self.bin / "ssh"
        ssh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$SSH_TEST_LOG"\nexit 1\n')
        ssh.chmod(0o755)
        log = self.root / "ssh-arguments"
        result = self.run_git(
            "-c", "core.sshCommand=false", "ls-remote", "git@example.test:repo",
            operator=True, settings={"GIT_SSH_COMMAND": "false", "SSH_TEST_LOG": str(log)},
        )
        self.assertNotEqual(result.returncode, 0)  # fake SSH never connects
        arguments = log.read_text().splitlines()
        self.assertIn(str(self.home / ".ssh/person.pub"), arguments)
        self.assertIn("IdentitiesOnly=yes", arguments)

    def test_unregistered_explicit_operator_and_automation_are_refused_in_threads(self):
        self.assert_requires_operator("commit", "--allow-empty", "-m", "blocked", operator=True, thread=True)
        self.assert_requires_operator("status", thread=True, settings={"GIT_OPERATOR": "automation"})
        self.run_git("operator", "set", "person", thread=True, check=True)
        result = self.assert_requires_operator("commit", thread=True, settings={"GIT_OPERATOR": "someone-else"})
        self.assertIn("not 'someone-else'", result.stderr)

    def test_ssh_guard_allows_reads_and_blocks_publication(self):
        ssh = self.bin / "ssh"
        ssh.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        ssh.chmod(0o755)
        for remote_command in ("git-upload-pack 'repo'", "git-upload-archive 'repo'", None):
            args = ["git@example.test"] if remote_command else ["-G", "git@example.test"]
            if remote_command:
                args.append(remote_command)
            result = subprocess.run(
                [str(self.bin / "git-ssh-guard"), *args], env=self.env, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        for remote_command in ("git-receive-pack 'repo'", "/usr/bin/git-receive-pack 'repo'", "git receive-pack 'repo'"):
            result = subprocess.run(
                [str(self.bin / "git-ssh-guard"), "git@example.test", remote_command],
                env=self.env, text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("operator", result.stderr)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
