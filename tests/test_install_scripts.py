"""Run the rendered install-scripts runner against a fake curl and local install scripts, without network access."""

import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "run_after_install-scripts.sh.tmpl"
# Serves https://example.test/<file> from INSTALL_TEST_SERVE/<file> and logs each URL.
FAKE_CURL = r'''#!/bin/bash
out= url=
while [ $# -gt 0 ]; do
  case $1 in
    -o) out=$2; shift ;;
    -*) ;;
    *) url=$1 ;;
  esac
  shift
done
echo "$url" >> "$INSTALL_TEST_CALLS"
src="$INSTALL_TEST_SERVE/${url#https://example.test/}"
[ -f "$src" ] || exit 22
cp "$src" "$out"
'''
# Records how it was run, then installs the binary named by the first argument.
INSTALLER = r'''#!/bin/sh
printf '%s\n' "$@" > "$HOME/args"
printf '%s\n' "$PWD" > "$HOME/cwd"
cat > "$HOME/stdin"
env > "$HOME/env"
mkdir -p "$(dirname "$1")"
printf '#!/bin/sh\n' > "$1"
chmod +x "$1"
echo run >> "$HOME/runs"
'''


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class InstallScriptsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="install-scripts-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.bin = root / "bin"
        self.bin.mkdir()
        (self.bin / "curl").write_text(FAKE_CURL)
        (self.bin / "curl").chmod(0o755)
        self.serve = root / "serve"
        self.serve.mkdir()
        (self.serve / "install.sh").write_text(INSTALLER)
        (self.serve / "fail.sh").write_text("#!/bin/sh\necho broken >&2\nexit 3\n")
        (self.serve / "noop.sh").write_text("#!/bin/sh\nexit 0\n")
        self.calls = root / "calls"
        self.data = root / "data.json"
        self.script = root / "rendered.sh"
        self.env = {key: value for key, value in os.environ.items() if key != "XDG_STATE_HOME"}
        self.env.update(
            HOME=str(self.home),
            PATH=f"{self.bin}{os.pathsep}{self.home / '.local/bin'}{os.pathsep}{os.environ['PATH']}",
            INSTALL_TEST_SERVE=str(self.serve),
            INSTALL_TEST_CALLS=str(self.calls),
        )

    def render(self, entries=None):
        command = ["chezmoi", "--source", str(REPO), "execute-template"]
        if entries is not None:
            self.data.write_text(json.dumps({"install_scripts": entries}))
            command += ["--override-data-file", str(self.data)]
        result = subprocess.run(
            command, input=TEMPLATE.read_text(), env=self.env, text=True, capture_output=True, timeout=30
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.script.write_text(result.stdout)

    def run_script(self):
        self.calls.write_text("")
        # chezmoi apply may run from a terminal: install scripts must not read its input.
        result = subprocess.run(
            ["bash", str(self.script)], input="typed at the terminal\n",
            env=self.env, text=True, capture_output=True, timeout=30,
        )
        return result, self.calls.read_text().splitlines()

    def runs(self):
        path = self.home / "runs"
        return len(path.read_text().splitlines()) if path.exists() else 0

    @staticmethod
    def entry(**fields):
        return {"name": "demo", "url": "https://example.test/install.sh", "bin": "~/.local/bin/demo",
                "args": ["~/.local/bin/demo"], **fields}

    def test_repository_data_renders_and_installs_nothing(self):
        self.render()
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])

    def test_installs_with_args_env_and_no_terminal_then_skips(self):
        self.render([self.entry(args=["~/.local/bin/demo", "it's $HOME"], env={"DEMO_DIR": "~/opt", "N": 3})])
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["https://example.test/install.sh"])
        self.assertTrue(os.access(self.home / ".local/bin/demo", os.X_OK))
        self.assertEqual((self.home / "args").read_text().splitlines(), [f"{self.home}/.local/bin/demo", "it's $HOME"])
        env = dict(line.split("=", 1) for line in (self.home / "env").read_text().splitlines() if "=" in line)
        self.assertEqual(env["DEMO_DIR"], f"{self.home}/opt")
        self.assertEqual(env["N"], "3")
        self.assertEqual((self.home / "stdin").read_text(), "")
        cwd = (self.home / "cwd").read_text().strip()
        self.assertFalse(Path(cwd).exists(), "the download directory is removed")

        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [], "an installed, unchanged entry is not downloaded again")
        self.assertEqual(self.runs(), 1)

    def test_changed_entry_reinstalls(self):
        self.render([self.entry()])
        self.run_script()
        self.render([self.entry(env={"VERSION": "2"})])
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["https://example.test/install.sh"])
        self.assertEqual(self.runs(), 2)

    def test_missing_binary_reinstalls(self):
        self.render([self.entry()])
        self.run_script()
        (self.home / ".local/bin/demo").unlink()
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), 2)

    def test_bare_command_is_found_on_path(self):
        self.render([self.entry(bin="demo")])
        result, _ = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        result, calls = self.run_script()
        self.assertEqual(calls, [])

    def test_sha256_mismatch_does_not_run_the_script(self):
        self.render([self.entry(sha256="0" * 64)])
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match sha256", result.stderr)
        self.assertEqual(self.runs(), 0)

        good = hashlib.sha256(INSTALLER.encode()).hexdigest()
        self.render([self.entry(sha256=good)])
        result, _ = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), 1)

    def test_failures_do_not_stop_other_entries_and_are_retried(self):
        self.render([
            self.entry(name="broken", url="https://example.test/fail.sh", bin="~/.local/bin/broken"),
            self.entry(name="silent", url="https://example.test/noop.sh", bin="~/.local/bin/silent"),
            self.entry(name="gone", url="https://example.test/missing.sh", bin="~/.local/bin/gone"),
            self.entry(),
        ])
        result, _ = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("failed: broken silent gone", result.stderr)
        self.assertIn("broken: https://example.test/fail.sh exited with an error", result.stderr)
        self.assertIn("silent: https://example.test/noop.sh finished but ~/.local/bin/silent is not there", result.stderr)
        self.assertIn("gone: could not download", result.stderr)
        self.assertEqual(self.runs(), 1)

        result, calls = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(calls), 3, "failed entries are retried; the installed one is not")

    def test_rejects_bad_entries_without_downloading(self):
        self.render([
            self.entry(url="http://example.test/install.sh"),
            self.entry(name="../escape"),
            self.entry(name="nobin", bin=""),
        ])
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, [])
        self.assertIn("url must start with https://", result.stderr)
        self.assertIn("invalid name '../escape'", result.stderr)
        self.assertIn("nobin: bin is required", result.stderr)

    @unittest.skipUnless(shutil.which("openssl"), "openssl is not installed")
    def test_https_redirect_to_http_is_not_followed_or_run(self):
        """Real curl against loopback servers: https://.../redirect.sh answers 302 to http://.../install.sh."""
        (self.bin / "curl").unlink()
        http_hits = []

        class Plain(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                http_hits.append(self.path)

        class Secure(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect.sh":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{plain.server_port}/install.sh")
                    self.end_headers()
                else:
                    super().do_GET()

            def log_message(self, *args):
                pass

        cert = Path(self.temp.name) / "cert.pem"
        key = Path(self.temp.name) / "key.pem"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=127.0.0.1",
             "-addext", "subjectAltName=IP:127.0.0.1", "-keyout", str(key), "-out", str(cert)],
            check=True, capture_output=True, timeout=30,
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        plain = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Plain, directory=str(self.serve)))
        secure = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Secure, directory=str(self.serve)))
        secure.socket = context.wrap_socket(secure.socket, server_side=True)
        for server in (plain, secure):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

        base = f"https://127.0.0.1:{secure.server_port}"
        for key_ in [k for k in self.env if k.lower().endswith("_proxy")]:
            del self.env[key_]
        self.env.update(CURL_CA_BUNDLE=str(cert), SSL_CERT_FILE=str(cert))
        self.render([
            self.entry(name="downgraded", url=f"{base}/redirect.sh", bin="~/.local/bin/downgraded",
                       args=["~/.local/bin/downgraded"]),
            self.entry(url=f"{base}/install.sh"),
        ])
        result, _ = self.run_script()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("failed: downgraded", result.stderr)
        self.assertIn("downgraded: could not download", result.stderr)
        self.assertEqual(http_hits, [], "curl must not request the http:// redirect target")
        self.assertFalse((self.home / ".local/bin/downgraded").exists())
        self.assertTrue(os.access(self.home / ".local/bin/demo", os.X_OK), "later entries still install")
        self.assertEqual(self.runs(), 1)


if __name__ == "__main__":
    unittest.main()
