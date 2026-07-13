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
    status_coord.async_request_refresh = AsyncMock()
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
    # State change is reflected promptly via a coordinator refresh.
    status_coord.async_request_refresh.assert_awaited_once()


def _make_runtime():
    """Build a runtime whose api records calls and whose status refresh is awaitable."""
    api = MagicMock()
    api.async_set_boost = AsyncMock()
    api.async_set_away = AsyncMock()
    api.async_set_eco_start = AsyncMock()
    api.async_set_open_window_detection = AsyncMock()
    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(ApplianceId="app-1")
    status_coord = MagicMock()
    status_coord.async_request_refresh = AsyncMock()
    status_coord.data = {
        "appliances": [{"hub": hub, "zone": SimpleNamespace(ZoneName="Z"), "appliance": appliance, "status": None}]
    }
    return SimpleNamespace(api=api, status=status_coord)


async def _register_entry(hass: HomeAssistant, runtime, entry_id: str = "svc-entry"):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id=entry_id)
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await async_setup_services(hass)
    return entry


async def _device_id(hass: HomeAssistant, entry, appliance_id: str = "app-1") -> str:
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, appliance_id)},
        name="Heater",
    )
    return device.id


@pytest.mark.parametrize(
    ("service", "api_attr", "extra_data"),
    [
        ("clear_boost", "async_set_boost", {}),
        ("set_away", "async_set_away", {"temperature": 12.0}),
        ("clear_away", "async_set_away", {}),
        ("set_eco_start", "async_set_eco_start", {"enable": True}),
        ("set_open_window_detection", "async_set_open_window_detection", {"enable": False}),
    ],
)
async def test_control_services_call_api_and_refresh(hass: HomeAssistant, service, api_attr, extra_data) -> None:
    """Each control service invokes the API and requests a status refresh."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        service,
        {"device_id": device_id, **extra_data},
        blocking=True,
    )

    getattr(runtime.api, api_attr).assert_awaited_once()
    runtime.status.async_request_refresh.assert_awaited_once()


async def test_set_away_disable_flag(hass: HomeAssistant) -> None:
    """clear_away disables Away mode."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(DOMAIN, "clear_away", {"device_id": device_id}, blocking=True)
    assert runtime.api.async_set_away.await_args.kwargs["enable"] is False


async def test_service_resolves_by_entity_id(hass: HomeAssistant) -> None:
    """A service target given as entity_id resolves through the entity registry."""
    from homeassistant.helpers import entity_registry as er

    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "climate",
        DOMAIN,
        f"{entry.entry_id}_app-1_climate",
        config_entry=entry,
        device_id=device_id,
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"entity_id": "climate.heater"},
        blocking=True,
    )
    # entity_id may differ; assert the resolution reached the API regardless.
    runtime.api.async_set_boost.assert_awaited_once()


async def test_service_unknown_appliance_is_noop(hass: HomeAssistant) -> None:
    """A device not present in coordinator data resolves to no API call."""
    runtime = _make_runtime()
    runtime.status.data = {"appliances": []}  # appliance not known to the coordinator
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"device_id": device_id},
        blocking=True,
    )
    runtime.api.async_set_boost.assert_not_awaited()
    runtime.status.async_request_refresh.assert_not_awaited()
