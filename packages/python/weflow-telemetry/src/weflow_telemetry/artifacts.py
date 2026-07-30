"""Synthetic, content-addressed local artifacts for the Change 0 foundation."""

from __future__ import annotations

import hashlib
from pathlib import Path


class SyntheticArtifactError(ValueError):
    """Raised when code tries to use this local store for non-synthetic material."""


def store_synthetic_artifact(
    root: Path,
    content: bytes | str,
    *,
    tenant_id: str,
    media_type: str,
    created_at: str,
    producer: str,
    correlation_id: str,
    source: str = "synthetic-fixture",
) -> dict[str, object]:
    """Persist a synthetic fixture by SHA-256 and return safe metadata only.

    The returned shape contains neither the raw payload nor a filesystem path.  Required
    fixture metadata keeps this helper unsuitable for customer-data persistence.
    """

    if source != "synthetic-fixture":
        raise SyntheticArtifactError("synthetic_fixture_source_required")
    if not tenant_id or not media_type or not created_at or not producer or not correlation_id:
        raise SyntheticArtifactError("synthetic_artifact_metadata_required")
    payload = content.encode("utf-8") if isinstance(content, str) else content
    digest = hashlib.sha256(payload).hexdigest()
    location = root / "sha256" / digest
    location.parent.mkdir(parents=True, exist_ok=True)
    if not location.exists():
        location.write_bytes(payload)

    return {
        "artifact": {
            "schema_id": "https://weflow.local/contracts/v1/artifact.schema.json",
            "schema_version": "v1",
            "tenant_id": tenant_id,
            "artifact_id": f"synthetic-{digest[:16]}",
            "content_sha256": digest,
            "media_type": media_type,
            "redaction_classification": "synthetic",
            "created_at": created_at,
            "producer": producer,
        },
        "storage": {
            "source": "synthetic-fixture",
            "uri": f"local-artifact://sha256/{digest}",
            "correlation_id": correlation_id,
        },
    }
