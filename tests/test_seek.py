"""Render the Seek client config without OpenBao or the Seek server."""

import http.server
import json
import os
from pathlib import Path
import shutil
import socketserver
import subprocess
import tempfile
import threading
import unittest


REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "dot_config/seek/client.yml.tmpl"
IGNORE = REPO / ".chezmoiignore"
SOCKET = "unix:///run/wyrwood/vault.sock"
SYNTHETIC_TOKEN = "synthetic-workspace-token"


def seek_0_4():
    """seek 0.4 or later is on PATH: older releases ignore client.yml."""
    if not shutil.which("seek"):
        return False
    version = subprocess.run(["seek", "--version"], text=True, capture_output=True, timeout=30).stdout.strip()
    try:
        return tuple(int(part) for part in version.split(".")[:2]) >= (0, 4)
    except ValueError:
        return False


class Recorder(http.server.BaseHTTPRequestHandler):
    """Records each request's path and headers; answers a KV v2 read with the synthetic token, anything else 401."""

    def address_string(self):
        return "test"

    def handle_one(self):
        self.server.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
        if self.path.startswith("/v1/kv/"):
            body = json.dumps({"data": {"data": {"token": SYNTHETIC_TOKEN}, "metadata": {"version": 1}}}).encode()
            self.send_response(200)
        else:
            body = b'{"error":"test"}'
            self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = handle_one

    def log_message(self, *args):
        pass


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class TCPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is not installed")
class SeekConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="seek-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def render(self, template, url="https://seek.internal"):
        config = self.root / "chezmoi.yaml"
        config.write_text(f"data:\n  seek:\n    url: {url!r}\n")
        return subprocess.run(
            ["chezmoi", "--config", str(config), "--source", str(REPO), "execute-template"],
            input=template.read_text(),
            env={**os.environ, "HOME": str(self.root)},
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_reads_the_token_through_the_wyrwood_socket_without_a_login(self):
        result = self.render(TEMPLATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('url: "https://seek.internal"', result.stdout)
        self.assertRegex(
            result.stdout,
            r'  token:\n    vault:\n      address: unix:///run/wyrwood/vault.sock\n      namespace: ""\n      auth:\n        mode: none\n'
            r'      mount: "kv"\n      path: "workspace/seek"\n      key: "token"\n',
        )

    def test_no_config_until_a_server_is_named(self):
        ignored = self.render(IGNORE, url="")
        self.assertEqual(ignored.returncode, 0, ignored.stderr)
        self.assertIn(".config/seek", ignored.stdout.splitlines())
        kept = self.render(IGNORE)
        self.assertNotIn(".config/seek", kept.stdout.splitlines())

    def write_config(self, text):
        (self.root / "seek").mkdir(exist_ok=True)
        (self.root / "seek/client.yml").write_text(text)
        return {**os.environ, "XDG_CONFIG_HOME": str(self.root)}

    @unittest.skipUnless(seek_0_4(), "seek 0.4 or later is not installed")
    def test_seek_accepts_the_config(self):
        result = self.render(TEMPLATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        env = self.write_config(result.stdout)
        check = subprocess.run(["seek", "config", "validate"], text=True, capture_output=True, timeout=30, env=env)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    @unittest.skipUnless(seek_0_4(), "seek 0.4 or later is not installed")
    def test_reads_the_token_from_the_socket_with_no_login_or_namespace_whatever_the_shell_exports(self):
        """The socket must get no X-Vault-Token or X-Vault-Namespace, even with BAO_* exported for another server."""
        result = self.render(TEMPLATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        socket_path = self.root / "vault.sock"
        vault = UnixServer(str(socket_path), Recorder)
        vault.requests = []
        seek = TCPServer(("127.0.0.1", 0), Recorder)
        seek.requests = []
        for server in (vault, seek):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.assertIn(SOCKET, result.stdout)
        config = result.stdout.replace(SOCKET, f"unix://{socket_path}").replace(
            '"https://seek.internal"', f'"http://127.0.0.1:{seek.server_address[1]}"'
        )
        env = {
            **self.write_config(config),
            "BAO_ADDR": "https://elsewhere.invalid:8200",
            "BAO_TOKEN": "synthetic-exported-token",
            "BAO_NAMESPACE": "synthetic-exported-namespace",
        }
        call = subprocess.run(["seek", "web", "exa", "probe"], text=True, capture_output=True, timeout=60, env=env)
        self.assertIn("401", call.stdout + call.stderr)
        self.assertEqual([r["path"] for r in vault.requests], ["/v1/kv/data/workspace/seek"])
        headers = vault.requests[0]["headers"]
        self.assertNotIn("x-vault-token", headers)
        self.assertNotIn("x-vault-namespace", headers)
        self.assertEqual([r["headers"].get("authorization") for r in seek.requests], [f"Bearer {SYNTHETIC_TOKEN}"])


if __name__ == "__main__":
    unittest.main()
