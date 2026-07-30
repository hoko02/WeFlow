import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = ROOT / "scripts" / "scan_secrets.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("weflow_secret_scanner", SCANNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_secret_fixture_is_reported_without_value() -> None:
    scanner = _load_scanner()
    findings = scanner.scan_paths([ROOT / "tests/security/fixtures/secret-candidate.txt"], ROOT)

    assert findings == [
        {
            "path": "tests/security/fixtures/secret-candidate.txt",
            "line": 1,
            "rule": "key-value-assignment",
        }
    ]
    assert "abcdefghijklmnopqrstuvwxyz" not in str(findings)


def test_safe_fixture_is_not_reported() -> None:
    scanner = _load_scanner()
    findings = scanner.scan_paths([ROOT / "tests/security/fixtures/safe-configuration.txt"], ROOT)

    assert findings == []
