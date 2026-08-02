import asyncio
from pathlib import Path

import pytest
from weflow_control_kernel.temporal_driver import (
    TemporalDriverUnavailable,
    TemporalServiceBoundaryDriver,
)


def test_temporal_driver_rejects_non_loopback_targets_before_loading_the_sdk(
    tmp_path: Path,
) -> None:
    driver = TemporalServiceBoundaryDriver(
        store_path=tmp_path / "case-ledger.sqlite3",
        contract_root=tmp_path,
        target="temporal.example.test:7233",
    )

    with pytest.raises(TemporalDriverUnavailable, match="temporal_target_not_loopback"):
        asyncio.run(driver.readiness())
