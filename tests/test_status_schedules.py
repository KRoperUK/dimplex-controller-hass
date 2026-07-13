"""Status coordinator schedule caching and concurrent fetch behaviour."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex import DimplexStatusCoordinator
from custom_components.dimplex.const import DEFAULT_SCHEDULE_INTERVAL, DEFAULT_STATUS_INTERVAL, DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _status_payload():
    hub = SimpleNamespace(HubId="h1", HubName="Hub")
    appliance_a = SimpleNamespace(ApplianceId="a1")
    appliance_b = SimpleNamespace(ApplianceId="a2")
    return {
        "hubs": [hub],
        "appliances": [
            {"hub": hub, "appliance": appliance_a, "status": None, "zone": None},
            {"hub": hub, "appliance": appliance_b, "status": None, "zone": None},
        ],
    }


def _make_coordinator(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    entry.add_to_hass(hass)
    return DimplexStatusCoordinator(hass, entry, api, DEFAULT_STATUS_INTERVAL)


async def test_schedules_fetched_on_first_poll(hass):
    """First poll populates the schedule cache for every appliance concurrently."""
    api = AsyncMock()
    api.async_get_status_data.return_value = _status_payload()
    api.async_get_schedule.side_effect = lambda hub_id, appliance_id: SimpleNamespace(
        TimerMode=1, TimerPeriods=[], ApplianceId=appliance_id
    )
    api.token_data = {}

    coordinator = _make_coordinator(hass, api)
    data = await coordinator._async_update_data()  # noqa: SLF001

    assert set(data["schedules"]) == {"a1", "a2"}
    assert api.async_get_schedule.await_count == 2


async def test_schedules_cached_between_polls(hass):
    """A second poll within the refresh interval reuses the cache (no new calls)."""
    api = AsyncMock()
    api.async_get_status_data.return_value = _status_payload()
    api.async_get_schedule.return_value = SimpleNamespace(TimerMode=1, TimerPeriods=[])
    api.token_data = {}

    coordinator = _make_coordinator(hass, api)
    first = await coordinator._async_update_data()  # noqa: SLF001
    assert api.async_get_schedule.await_count == 2

    second = await coordinator._async_update_data()  # noqa: SLF001
    # No additional schedule calls, and the cached data is carried forward.
    assert api.async_get_schedule.await_count == 2
    assert second["schedules"] is first["schedules"]


async def test_schedules_refetched_after_interval(hass):
    """Once the refresh interval elapses, schedules are fetched again."""
    api = AsyncMock()
    api.async_get_status_data.return_value = _status_payload()
    api.async_get_schedule.return_value = SimpleNamespace(TimerMode=1, TimerPeriods=[])
    api.token_data = {}

    coordinator = _make_coordinator(hass, api)
    await coordinator._async_update_data()  # noqa: SLF001
    assert api.async_get_schedule.await_count == 2

    # Simulate the cache having been fetched longer ago than the interval.
    coordinator._schedules_fetched_at -= DEFAULT_SCHEDULE_INTERVAL.total_seconds() + 1  # noqa: SLF001

    await coordinator._async_update_data()  # noqa: SLF001
    assert api.async_get_schedule.await_count == 4


async def test_schedule_fetch_failure_is_tolerated(hass):
    """A failing schedule fetch yields None for that appliance, not an error."""
    api = AsyncMock()
    api.async_get_status_data.return_value = _status_payload()

    async def _sched(hub_id, appliance_id):
        if appliance_id == "a2":
            raise RuntimeError("boom")
        return SimpleNamespace(TimerMode=1, TimerPeriods=[])

    api.async_get_schedule.side_effect = _sched
    api.token_data = {}

    coordinator = _make_coordinator(hass, api)
    data = await coordinator._async_update_data()  # noqa: SLF001

    assert data["schedules"]["a1"] is not None
    assert data["schedules"]["a2"] is None
