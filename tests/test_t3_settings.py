"""T3 Code settings: chezmoi merges the workspace keys into ~/.t3/userdata/settings.json.

The modify template is rendered with chezmoi and fed example files on stdin. A second apply is
checked against a temporary destination, not the running home.
"""

import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "dot_t3/userdata/modify_private_settings.json"

FAVORITES = [
    {"provider": "codex", "model": "gpt-6-luna"},
    {"provider": "claudeAgent", "model": "claude-opus-5-5"},
    {"provider": "grok", "model": "grok-4.7"},
    {"provider": "opencode", "model": "opencode-go/glm-5.3-flash"},
    {"provider": "claudeAgent", "model": "claude-fable-5-2"},
    {"provider": "codex", "model": "gpt-6.1-terra"},
    {"provider": "codex", "model": "gpt-6.2-sol"},
    {"provider": "codex", "model": "gpt-6.2-astra"},
    {"provider": "antigravity", "model": "gemini-4-neon"},
]
SCALARS = {
    "projectSettingsFolded": True,
    "compactIdleThreads": True,
    "idleCompaction": "beforeCacheExpires",
    "linkedEnvironmentsEnabled": True,
    "addProjectBaseDirectory": "/workspace",
}
INSTANCES = {
    "antigravity": {"driver": "antigravity", "displayName": "Antigravity", "enabled": True},
    "grok": {"driver": "grok", "displayName": "Grok", "enabled": True},
}


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class SettingsTemplateTests(unittest.TestCase):
    def render(self, stdin_text):
        result = subprocess.run(
            ["chezmoi", "execute-template", "--with-stdin", "--file", str(TEMPLATE)],
            input=stdin_text,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def assert_owned(self, data):
        self.assertEqual(data["favorites"], FAVORITES)
        for key, value in SCALARS.items():
            self.assertEqual(data[key], value, key)
        for name, entry in INSTANCES.items():
            for key, value in entry.items():
                self.assertEqual(data["providerInstances"][name][key], value, f"{name}.{key}")

    def test_empty_stdin_writes_only_the_owned_keys(self):
        data = json.loads(self.render(""))
        self.assert_owned(data)
        self.assertEqual(set(data), {"favorites", "providerInstances", *SCALARS})
        self.assertEqual(set(data["providerInstances"]), set(INSTANCES))
        for entry in data["providerInstances"].values():
            self.assertEqual(set(entry), {"driver", "displayName", "enabled"})

    def test_keeps_other_settings_instances_and_instance_keys(self):
        existing = {
            "favorites": FAVORITES[:2],
            "projectSettingsFolded": False,
            "providerModelPreferences": {"grok": {"hiddenModels": ["old"]}},
            "providerInstances": {
                "codex": {"driver": "codex", "displayName": "Codex", "enabled": True},
                "antigravity": {"driver": "wrong", "displayName": "Old", "enabled": False, "account": "kept"},
            },
            "theme": "system",
        }
        rendered = self.render(json.dumps(existing))
        data = json.loads(rendered)
        self.assert_owned(data)
        self.assertEqual(data["providerModelPreferences"], existing["providerModelPreferences"])
        self.assertEqual(data["theme"], "system")
        self.assertEqual(data["providerInstances"]["codex"], existing["providerInstances"]["codex"])
        self.assertEqual(data["providerInstances"]["antigravity"]["account"], "kept")
        again = self.render(rendered)
        self.assertEqual(again, rendered)

    def test_matching_values_pass_through_byte_for_byte(self):
        content = (
            "{\n"
            '    "addProjectBaseDirectory": "/workspace",\n'
            '    "compactIdleThreads": true,\n'
            '    "favorites": '
            + json.dumps(FAVORITES)
            + ",\n"
            '    "idleCompaction": "beforeCacheExpires",\n'
            '    "linkedEnvironmentsEnabled": true,\n'
            '    "note": "leave my spacing",\n'
            '    "projectSettingsFolded": true,\n'
            '    "providerInstances": {\n'
            '        "antigravity": {"displayName": "Antigravity", "driver": "antigravity", "enabled": true, "extra": 1},\n'
            '        "grok": {"driver": "grok", "displayName": "Grok", "enabled": true}\n'
            "    }\n"
            "}\n"
        )
        self.assertEqual(self.render(content), content)

    def test_favorites_list_is_replaced(self):
        existing = {
            "favorites": [
                {"provider": "codex", "model": "not-ours"},
                FAVORITES[2],
                FAVORITES[0],
            ],
            "theme": "system",
        }
        data = json.loads(self.render(json.dumps(existing)))
        self.assertEqual(data["favorites"], FAVORITES)
        self.assertEqual(data["theme"], "system")

    def test_whitespace_only_stdin_is_replaced(self):
        data = json.loads(self.render("\n\n"))
        self.assert_owned(data)


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class SettingsApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="t3-settings-apply-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.settings = self.home / ".t3/userdata/settings.json"
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{\n  "theme": "system"\n}\n')

    def apply(self):
        result = subprocess.run(
            ["chezmoi", "--source", str(REPO), "--destination", str(self.home),
             "apply", "--exclude=scripts", str(self.settings)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_apply_merges_and_a_second_apply_changes_nothing(self):
        self.apply()
        first = self.settings.read_bytes()
        data = json.loads(first)
        self.assertEqual(data["theme"], "system")
        self.assertEqual(data["favorites"], FAVORITES)
        self.assertEqual(data["providerInstances"]["grok"]["driver"], "grok")
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o600)
        self.apply()
        self.assertEqual(self.settings.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
