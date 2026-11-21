"""The gh shim mints an App token for Grok and Antigravity, and leaves other calls alone.

A fake gh records the calls. Nothing here reaches GitHub or OpenBao.
"""

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SHIM = REPO / "dot_local/bin/executable_gh"
CONFIG = REPO / "dot_config/gh-vault-agent-app-token/config.yml"
MARKERS = (
    "GH_LOGIN", "CLAUDECODE", "CODEX_THREAD_ID", "CURSOR_AGENT", "PI_CODING_AGENT",
    "COPILOT_CLI", "ANTIGRAVITY_AGENT", "GROK_AGENT",
)
TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")

FAKE_GH = r"""#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_GH_LOG"
if [ "${1:-}" = vault-agent-app-token ]; then
  printf 'fake-token'
  exit 0
fi
if [ -n "${GH_TOKEN:-}" ]; then
  printf 'token-set\n' >> "$FAKE_GH_LOG"
else
  printf 'token-unset\n' >> "$FAKE_GH_LOG"
fi
exit 0
"""


class GhShimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gh-shim-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        bindir = root / "bin"
        bindir.mkdir()
        fake = bindir / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = root / "log"
        self.env = {key: value for key, value in os.environ.items() if key not in MARKERS + TOKEN_VARS}
        self.env.update(PATH=f"{bindir}:{os.environ['PATH']}", FAKE_GH_LOG=str(self.log))

    def run_shim(self, *args, **markers):
        env = dict(self.env)
        for name, value in markers.items():
            if value is None:
                env.pop(name, None)
            else:
                env[name] = value
        result = subprocess.run(["bash", str(SHIM), *args], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_config_maps_grok_and_antigravity(self):
        text = CONFIG.read_text()
        self.assertIn("grok: wyrd-grok[bot]", text)
        self.assertIn("antigravity: wyrd-gemini[bot]", text)

    def test_grok_and_antigravity_mint_and_a_plain_call_does_not(self):
        for marker in ("GROK_AGENT", "ANTIGRAVITY_AGENT"):
            with self.subTest(marker=marker):
                self.log.unlink(missing_ok=True)
                lines = self.run_shim("api", "user", **{marker: "1"})
                self.assertEqual(lines, ["vault-agent-app-token", "api user", "token-set"])
        self.log.unlink(missing_ok=True)
        lines = self.run_shim("api", "user")
        self.assertEqual(lines, ["api user", "token-unset"])

    def test_an_empty_marker_does_not_mint(self):
        lines = self.run_shim("api", "user", GROK_AGENT="")
        self.assertEqual(lines, ["api user", "token-unset"])


if __name__ == "__main__":
    unittest.main()
