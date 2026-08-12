#!/usr/bin/env python
"""Scan tracked working-tree content for candidate secrets without echoing values."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".env",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "dist", "__pycache__"}
TEST_FIXTURE_DIRECTORY = Path("tests/security/fixtures")
_SAFE_VALUES = {"", "example", "placeholder", "changeme", "[redacted]", "not-a-real-secret"}
_KEY_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|credential)\b\s*[:=]\s*[\"']?(?P<value>[A-Za-z0-9_./+=-]{12,})"
)
_PROVIDER_TOKEN = re.compile(r"\b(?:sk|rk|pk|xoxb)-[A-Za-z0-9_-]{16,}\b", re.I)
_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_SECRET_KEY = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|credential)")
_ENVIRONMENT_KEY_VALUE = re.compile(r"^WEFLOW_[A-Z0-9_]+$")


def _is_text_candidate(path: Path) -> bool:
    return path.name == ".env" or path.suffix.lower() in TEXT_SUFFIXES


def _is_excluded(path: Path, root: Path) -> bool:
    relative = path.resolve().relative_to(root.resolve())
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def find_candidates(text: str) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _KEY_VALUE.search(line)
        if match and match.group("value").lower() not in _SAFE_VALUES:
            findings.append((number, "key-value-assignment"))
        if _PROVIDER_TOKEN.search(line):
            findings.append((number, "provider-token-pattern"))
        if _AWS_KEY.search(line):
            findings.append((number, "aws-access-key-pattern"))
    return findings


def _python_key(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _hardcoded_python_value(key: object, value: ast.expr) -> bool:
    return (
        isinstance(key, str)
        and _SECRET_KEY.search(key) is not None
        and isinstance(value, ast.Constant)
        and isinstance(value.value, str)
        and _ENVIRONMENT_KEY_VALUE.fullmatch(value.value) is None
        and len(value.value) >= 12
        and value.value.lower() not in _SAFE_VALUES
    )


def find_python_candidates(text: str) -> list[tuple[int, str]]:
    """Find hardcoded Python credential literals without flagging variable flow."""

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return find_candidates(text)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(
                _hardcoded_python_value(_python_key(target), node.value) for target in node.targets
            ):
                findings.append((node.lineno, "key-value-assignment"))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if _hardcoded_python_value(_python_key(node.target), node.value):
                findings.append((node.lineno, "key-value-assignment"))
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if _hardcoded_python_value(keyword.arg, keyword.value):
                    findings.append((keyword.value.lineno, "key-value-assignment"))
        elif isinstance(node, ast.Dict):
            for key_node, value_node in zip(node.keys, node.values, strict=True):
                key = key_node.value if isinstance(key_node, ast.Constant) else None
                if _hardcoded_python_value(key, value_node):
                    findings.append((value_node.lineno, "key-value-assignment"))
    for number, line in enumerate(text.splitlines(), start=1):
        if _PROVIDER_TOKEN.search(line):
            findings.append((number, "provider-token-pattern"))
        if _AWS_KEY.search(line):
            findings.append((number, "aws-access-key-pattern"))
    return sorted(set(findings))


def scan_paths(paths: Iterable[Path], root: Path = ROOT) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in paths:
        if not path.is_file() or not _is_text_candidate(path) or _is_excluded(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        candidates = (
            find_python_candidates(text) if path.suffix.lower() == ".py" else find_candidates(text)
        )
        for line, rule in candidates:
            findings.append({"path": path.relative_to(root).as_posix(), "line": line, "rule": rule})
    return findings


def tracked_worktree_paths(root: Path = ROOT) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(root / line for line in result.stdout.splitlines() if line)


def scan_repository(root: Path = ROOT) -> list[dict[str, object]]:
    paths = [
        path
        for path in tracked_worktree_paths(root)
        if not path.is_relative_to(root / TEST_FIXTURE_DIRECTORY)
    ]
    return scan_paths(paths, root)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    findings = scan_repository()
    report = {
        "report_type": "weflow-secret-hygiene.v1",
        "passed": not findings,
        "findings": findings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
