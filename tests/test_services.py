"""Tests for domain services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import DOMAIN
from custom_components.dimplex.services import (
    SERVICE_SET_BOOST,
    _appliance_id_from_unique_id,
    async_setup_services,
)

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def test_parse_unique_id():
    assert _appliance_id_from_unique_id("entry1", "entry1_app-1_climate") == "app-1"
    assert _appliance_id_from_unique_id("entry1", "entry1_app-1_boost") == "app-1"
    # Fallback path only (services prefer device registry when entity has a device).
    assert _appliance_id_from_unique_id("entry1", "entry1_app-1_room_temperature") == "app-1_room"


async def test_set_boost_service_by_device(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="svc-entry")
    entry.add_to_hass(hass)

    api = MagicMock()
    api.async_set_boost = AsyncMock()
    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(ApplianceId="app-1")
    status_coord = MagicMock()
    status_coord.data = {
        "appliances": [{"hub": hub, "zone": SimpleNamespace(ZoneName="Z"), "appliance": appliance, "status": None}]
    }
    runtime = SimpleNamespace(api=api, status=status_coord)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    await async_setup_services(hass)

    # Register a fake device in the device registry
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "app-1")},
        name="Heater",
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"device_id": device.id, "temperature": 24.0, "duration": 30},
        blocking=True,
    )
    api.async_set_boost.assert_awaited_once()
    kwargs = api.async_set_boost.await_args
    assert kwargs.args[0] == "hub-1"
    assert kwargs.args[1] == "app-1"
    assert kwargs.kwargs["temperature"] == 24.0
    assert kwargs.kwargs["duration_minutes"] == 30
    assert kwargs.kwargs["enable"] is True
