import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from protocol import authenticated_subprotocol, token_subprotocol


class ConnectorTests(unittest.TestCase):
    def test_manifest_and_pairing_script_exist(self):
        root = Path(__file__).parent
        self.assertTrue((root / "plugin.yaml").is_file())
        self.assertTrue((root / "connect.py").is_file())

    def test_connect_module_loads(self):
        module = _load_connect_module("browser_connect")
        self.assertTrue(callable(module._write_env))

    def test_windows_default_home_uses_local_appdata(self):
        module = _load_connect_module("browser_connect_windows_home")
        env = {"LOCALAPPDATA": r"C:\Users\test\AppData\Local"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                module._hermes_home(platform="nt"),
                Path(r"C:\Users\test\AppData\Local") / "hermes",
            )

    def test_explicit_hermes_home_wins(self):
        module = _load_connect_module("browser_connect_custom_home")
        with mock.patch.dict(os.environ, {"HERMES_HOME": "/custom/hermes"}, clear=True):
            self.assertEqual(module._hermes_home(), Path("/custom/hermes"))

    def test_pairing_token_uses_authenticated_websocket_subprotocol(self):
        token = "a" * 64
        protocol = token_subprotocol(token)
        self.assertEqual(protocol, f"hermes-browser-token.{token}")
        self.assertEqual(authenticated_subprotocol(f"chat, {protocol}", token), protocol)
        self.assertEqual(authenticated_subprotocol("hermes-browser-token.wrong", token), "")

    def test_env_file_is_replaced_without_leaking_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".env"
            path.write_text("KEEP=yes\nHERMES_BROWSER_CONNECTOR_TOKEN=old\n", encoding="utf-8")
            module = _load_connect_module("browser_connect_env")
            with mock.patch.dict(os.environ, {"HERMES_HOME": str(root)}):
                module._write_env({"HERMES_BROWSER_CONNECTOR_TOKEN": "new"})
            self.assertEqual(path.read_text(encoding="utf-8"), "KEEP=yes\nHERMES_BROWSER_CONNECTOR_TOKEN=new\n")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_installers_update_without_force_reinstall(self):
        root = Path(__file__).parent
        powershell = (root / "install.ps1").read_text(encoding="utf-8")
        shell = (root / "install.sh").read_text(encoding="utf-8")
        self.assertIn("git -C $pluginDir fetch", powershell)
        self.assertIn('git -C "$plugin_dir" fetch', shell)
        self.assertNotIn("--force }", powershell)
        self.assertNotIn('plugins install "$repository" --enable --force', shell)


def _load_connect_module(name):
    path = Path(__file__).parent / "connect.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
