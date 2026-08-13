import importlib.util
import sys
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
        self.assertIn("Test-GitCheckout", powershell)
        self.assertIn("Move-BrokenConnector", powershell)
        self.assertNotIn("rev-parse --is-inside-work-tree *> $null", powershell)
        self.assertIn("plugin-backups", powershell)
        self.assertIn("plugin-backups", shell)
        self.assertNotIn("--force }", powershell)
        self.assertNotIn('plugins install "$repository" --enable --force', shell)

    def test_session_list_uses_browser_chat_identity_and_preserves_database_id(self):
        adapter = _load_adapter().BrowserAdapter.__new__(_load_adapter().BrowserAdapter)
        adapter._browser_session_rows = lambda limit=500: [
            {
                "id": "db-session-one",
                "chat_id": "browser-chat-one",
                "title": "First conversation",
                "source": "hermes_browser",
                "message_count": 3,
            },
            {
                "id": "db-session-two",
                "chat_id": "browser-chat-two",
                "title": "Second conversation",
                "source": "hermes_browser",
                "message_count": 5,
            },
        ]

        rows = adapter._list_sessions({"limit": 20})

        self.assertEqual([row["id"] for row in rows], ["browser-chat-one", "browser-chat-two"])
        self.assertEqual(
            [row["history_session_id"] for row in rows],
            ["db-session-one", "db-session-two"],
        )

    def test_session_history_resolves_each_browser_chat_to_its_database_session(self):
        module = _load_adapter()
        adapter = module.BrowserAdapter.__new__(module.BrowserAdapter)
        adapter._browser_session_rows = lambda limit=500: [
            {"id": "db-session-one", "chat_id": "browser-chat-one"},
            {"id": "db-session-two", "chat_id": "browser-chat-two"},
        ]

        class FakeSessionDB:
            def get_messages_as_conversation(self, session_id, include_ancestors=False):
                return [{"role": "assistant", "content": f"history:{session_id}"}]

        adapter._session_db = lambda: FakeSessionDB()

        first = adapter._session_history("browser-chat-one")
        second = adapter._session_history("browser-chat-two")

        self.assertEqual(first[0]["content"], "history:db-session-one")
        self.assertEqual(second[0]["content"], "history:db-session-two")
        self.assertNotEqual(first, second)


def _load_connect_module(name):
    path = Path(__file__).parent / "connect.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_adapter():
    name = "hermes_browser_connector_test_package"
    if f"{name}.adapter" in sys.modules:
        return sys.modules[f"{name}.adapter"]
    root = Path(__file__).parent
    package_spec = importlib.util.spec_from_file_location(
        name,
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    package = importlib.util.module_from_spec(package_spec)
    sys.modules[name] = package
    package_spec.loader.exec_module(package)
    adapter_spec = importlib.util.spec_from_file_location(f"{name}.adapter", root / "adapter.py")
    module = importlib.util.module_from_spec(adapter_spec)
    sys.modules[f"{name}.adapter"] = module
    adapter_spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
