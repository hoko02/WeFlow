import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "reconcile_archive_evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("weflow_reconcile_evidence", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _acceptance_report(change: str) -> dict[str, object]:
    report_type = (
        "weflow-change-4-policy-approval-acceptance.v1"
        if change == "add-policy-and-approval-gates"
        else "weflow-change-5-evidence-trajectory-acceptance.v1"
    )
    return {
        "report_type": report_type,
        "accepted": True,
        "offline": True,
        "docker_required": False,
        "network_required": False,
        "model_credentials_required": False,
        "fixture_outcomes": {},
        "determinism": {"repeated_baseline_equal": True, "intentional_nondeterministic_fields": []},
        "environment_limits": {"docker_available": False, "node_available": True},
        "capabilities": {"external_writes_enabled": False},
    }


def _strict_report(change: str) -> dict[str, object]:
    return {
        "report_type": "weflow-openspec-validation.v1",
        "change": change,
        "command": "openspec validate archived-change --type change --strict",
        "strict": True,
        "valid": True,
        "issues": [],
        "outcome": "passed",
        "elapsed_seconds": 1.0,
        "exit_code": 0,
    }


def _aggregate_report() -> dict[str, object]:
    return {
        "report_type": "weflow-change-4-5-reconciliation-verification.v1",
        "command": "python scripts/dev.py test",
        "outcome": "passed",
        "elapsed_seconds": 12.5,
        "exit_code": 0,
        "outer_timeout_seconds": 900,
        "cleanup": {"required": False, "completed": True},
        "environment": {
            "node_available": True,
            "node_version": "v24.16.0",
            "docker_available": False,
        },
        "limitations": ["docker_unavailable", "offline_only"],
    }


def _manifest(module, root: Path, change: str) -> dict[str, object]:
    config = module.CHANGE_CONFIG[change]
    artifacts = []
    for kind, relative_path in (
        ("acceptance", config["acceptance"]),
        ("strict_validation", config["strict_validation"]),
        ("aggregate_verification", module.AGGREGATE_VERIFICATION),
    ):
        artifacts.append(
            {
                "kind": kind,
                "path": relative_path,
                "sha256": module.sha256_file(root / relative_path),
                "outcome": "passed",
            }
        )
    return {
        "report_type": "weflow-archive-evidence-manifest.v1",
        "change": change,
        "archive_path": config["archive_path"],
        "source_commit": "a" * 40,
        "reconciled_on": "2026-08-04",
        "artifacts": artifacts,
        "commands": [
            {
                "kind": item["kind"],
                "command": f"offline-{item['kind']}",
                "outcome": "passed",
                "elapsed_seconds": 1.0,
                "exit_code": 0,
            }
            for item in artifacts
        ],
        "environment": {
            "node_available": True,
            "node_version": "v24.16.0",
            "docker_available": False,
        },
        "limitations": ["docker_unavailable", "offline_only"],
    }


def _prepare_root(module, tmp_path: Path) -> Path:
    for config in module.CHANGE_CONFIG.values():
        (tmp_path / config["archive_path"]).mkdir(parents=True)
    for documentation_path in module.DOCUMENTATION_PATHS:
        path = tmp_path / documentation_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    for change, config in module.CHANGE_CONFIG.items():
        _write_json(tmp_path / config["acceptance"], _acceptance_report(change))
        _write_json(tmp_path / config["strict_validation"], _strict_report(change))
    _write_json(tmp_path / module.AGGREGATE_VERIFICATION, _aggregate_report())
    for change, config in module.CHANGE_CONFIG.items():
        _write_json(tmp_path / config["manifest"], _manifest(module, tmp_path, change))
    return tmp_path


def test_manifest_accepts_canonical_redacted_evidence(tmp_path: Path) -> None:
    module = _load_module()
    root = _prepare_root(module, tmp_path)

    manifest = module.validate_manifest(
        root, root / module.CHANGE_CONFIG["add-policy-and-approval-gates"]["manifest"]
    )

    assert manifest["change"] == "add-policy-and-approval-gates"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (
            lambda manifest: manifest["artifacts"][0].update({"sha256": "not-a-hash"}),
            "manifest_artifact_hash_invalid",
        ),
        (
            lambda manifest: manifest["commands"][0].update({"outcome": "skipped"}),
            "manifest_command_outcome_invalid",
        ),
    ],
)
def test_manifest_rejects_invalid_hash_and_unknown_outcome(
    tmp_path: Path, mutation, reason_code: str
) -> None:
    module = _load_module()
    root = _prepare_root(module, tmp_path)
    manifest_path = root / module.CHANGE_CONFIG["add-policy-and-approval-gates"]["manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutation(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(module.EvidenceValidationError, match=reason_code):
        module.validate_manifest(root, manifest_path)


def test_manifest_rejects_missing_evidence_and_raw_field(tmp_path: Path) -> None:
    module = _load_module()
    root = _prepare_root(module, tmp_path)
    config = module.CHANGE_CONFIG["add-evidence-and-trajectory-replay"]
    acceptance_path = root / config["acceptance"]
    report = json.loads(acceptance_path.read_text(encoding="utf-8"))
    report["raw_message"] = "must-not-be-retained"
    _write_json(acceptance_path, report)

    with pytest.raises(module.EvidenceValidationError, match="evidence_unsafe_field"):
        module.validate_manifest(root, root / config["manifest"])

    acceptance_path.unlink()
    with pytest.raises(
        module.EvidenceValidationError, match="manifest_referenced_evidence_missing"
    ):
        module.validate_manifest(root, root / config["manifest"])


def test_documentation_references_reject_unknown_or_missing_report_paths(tmp_path: Path) -> None:
    module = _load_module()
    root = _prepare_root(module, tmp_path)
    guide = root / module.CHANGE_CONFIG["add-policy-and-approval-gates"]["guide"]
    guide.write_text("Evidence: reports/change-4-untracked.json\n", encoding="utf-8")

    with pytest.raises(module.EvidenceValidationError, match="documentation_report_path_untracked"):
        module.validate_documentation_references(root)

    guide.write_text("Evidence: reports/change-4-acceptance.json\n", encoding="utf-8")
    (root / "reports/change-4-acceptance.json").unlink()
    with pytest.raises(module.EvidenceValidationError, match="documentation_report_missing"):
        module.validate_documentation_references(root)


def test_updated_guides_retain_archive_status_and_safe_scope_language() -> None:
    module = _load_module()

    module.validate_scope_language(ROOT)


def test_timed_out_aggregate_requires_owned_process_cleanup() -> None:
    module = _load_module()
    report = _aggregate_report()
    report["outcome"] = "timed_out"
    report["exit_code"] = None
    report["cleanup"] = {"required": True, "completed": False}

    with pytest.raises(module.EvidenceValidationError, match="timeout_cleanup_incomplete"):
        module._validate_aggregate_report(report)


def test_strict_validation_cannot_mark_a_nonzero_issue_as_passed() -> None:
    module = _load_module()
    report = _strict_report("add-policy-and-approval-gates")
    report["valid"] = False
    report["issues"] = ["archived_change_has_no_delta"]
    report["exit_code"] = 1

    with pytest.raises(module.EvidenceValidationError, match="strict_report_pass_not_valid"):
        module._validate_strict_report(report, "add-policy-and-approval-gates")
