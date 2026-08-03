import importlib.util
from pathlib import Path


def test_manifest_and_pairing_script_exist():
    root = Path(__file__).parent
    assert (root / "plugin.yaml").is_file()
    assert (root / "connect.py").is_file()


def test_connect_module_loads():
    path = Path(__file__).parent / "connect.py"
    spec = importlib.util.spec_from_file_location("browser_connect", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module._write_env)

