import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from weflow_agent_runtime.live_runtime import DraftArtifactStore, LiveRuntimeError

NOW = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)


def test_draft_store_is_access_restricted_and_content_addressed(tmp_path: Path) -> None:
    store = DraftArtifactStore(tmp_path / "artifacts", retain_diagnostics=True)
    path = store.put("draft-artifact:bounded", b'{"summary":"redacted synthetic"}')

    assert path.parent == store.root
    assert path.name.endswith(".json")
    assert "draft-artifact" not in path.name
    if os.name != "nt":
        assert stat.S_IMODE(store.root.stat().st_mode) & 0o077 == 0
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0

    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(LiveRuntimeError, match="artifact_path_invalid"):
        store.remove(outside)
    assert outside.exists()


def test_later_store_cleans_expired_drafts_recursively_but_keeps_fresh(
    tmp_path: Path,
) -> None:
    root = tmp_path / "retained"
    old_store = DraftArtifactStore(root / "old-session" / "task-1", retain_diagnostics=True)
    old = old_store.put("old", b'{"summary":"old redacted synthetic"}')
    fresh_store = DraftArtifactStore(root / "new-session" / "task-1", retain_diagnostics=True)
    fresh = fresh_store.put("fresh", b'{"summary":"fresh redacted synthetic"}')
    old_time = (NOW - timedelta(hours=2)).timestamp()
    fresh_time = NOW.timestamp()
    os.utime(old, (old_time, old_time))
    os.utime(fresh, (fresh_time, fresh_time))

    removed = DraftArtifactStore(root, retain_diagnostics=True).cleanup_expired(now=NOW)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
