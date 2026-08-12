import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = ROOT / "scripts" / "scan_secrets.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("weflow_secret_scanner_ast", SCANNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_scanner_ignores_variable_flow_but_not_hardcoded_literals() -> None:
    scanner = _load_scanner()

    assert scanner.find_python_candidates("self._access_token = access_token\n") == []
    assert scanner.find_python_candidates("client_secret = config.client_secret\n") == []
    assert scanner.find_python_candidates('client_secret = "not-a-real-secret"\n') == []
    assert scanner.find_python_candidates('client_secret = "abcdefghijklmnop"\n') == [
        (1, "key-value-assignment")
    ]
    assert (
        scanner.find_python_candidates(
            'credential_environment_variable="WEFLOW_LIVE_MODEL_API_KEY"\n'
        )
        == []
    )
    assert scanner.find_python_candidates('call(client_secret="abcdefghijklmnop")\n') == [
        (1, "key-value-assignment")
    ]
    assert scanner.find_python_candidates('{"WEFLOW_QQ_CLIENT_SECRET": "abcdefghijklmnop"}\n') == [
        (1, "key-value-assignment")
    ]
