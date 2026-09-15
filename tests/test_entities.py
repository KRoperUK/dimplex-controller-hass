"""Test dimplex entity platforms."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import BOOST_FLAG, DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _mock_coordinator_payload(*, appliance_modes=None):
    hub = SimpleNamespace(
        HubId="hub-1",
        FriendlyName="My Hub",
        HubType="GatewayOther",
        ConnectionState=1,
        FirmwareVersion="129.12.5",
        BluetoothName="GW3042<Dimplex>",
    )
    zone = SimpleNamespace(ZoneName="Living Room")
    prov = SimpleNamespace(rated_power=2.22, charge_capacity=15.5)
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
        FirmwareVersion="6",
        SeriesIdentifier="G12",
        LastTelemDate=None,
        automatic_provisioning=prov,
    )
    status = SimpleNamespace(
        EcoStartEnabled=False,
        ComfortStatus=True,
        RoomTemperature=21.5,
        ActiveSetPointTemperature=20,
        BoostTemperature=25.0,
        AwayTemperature=15.0,
        SetbackTemperature=18.0,
        OpenWindowEnabled=True,
        SetbackEnabled=True,
        ErrorCode="E1",
        WarningCode="W2",
        ApplianceModes=appliance_modes,
    )
    return {"appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}]}


async def test_sensor_and_binary_sensor_entities(hass):
    """Test sensor and binary sensor state mapping."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=_mock_coordinator_payload(),
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    def _find(prefix: str, *needles: str):
        for state in hass.states.async_all():
            if not state.entity_id.startswith(prefix):
                continue
            if all(n in state.entity_id for n in needles):
                return state
        return None

    sensor_state = _find("sensor.", "room_temperature")
    assert sensor_state is not None
    assert sensor_state.state == "21.5"

    binary_state = _find("binary_sensor.", "comfort")
    assert binary_state is not None
    assert binary_state.state == "on"
    # Comfort active -> sofa icon (matches HA climate "comfort" preset).
    assert binary_state.attributes.get("icon") == "mdi:sofa"

    # EcoStart is disabled in the mock payload -> leaf-off icon.
    switch_state = _find("switch.", "ecostart")
    assert switch_state is not None
    assert switch_state.attributes.get("icon") == "mdi:leaf-off"

    target_state = _find("sensor.", "target_temperature")
    assert target_state is not None
    assert target_state.state == "20.0"

    open_window_state = _find("binary_sensor.", "open_window")
    assert open_window_state is not None
    assert open_window_state.state == "on"

    setback_state = _find("binary_sensor.", "setback")
    assert setback_state is not None
    assert setback_state.state == "on"

    hub_connected_state = _find("binary_sensor.", "connected")
    assert hub_connected_state is not None
    assert hub_connected_state.state == "on"

    climate_state = _find("climate.")
    assert climate_state is not None
    assert climate_state.state in ("heat", "off")
    assert climate_state.attributes.get("current_temperature") == 21.5
    assert climate_state.attributes.get("temperature") == 20

    # Device registry should expose serial/firmware metadata from the cloud.
    from homeassistant.helpers import device_registry as dr

    device_registry = dr.async_get(hass)
    appliance_device = device_registry.async_get_device_by_identifier((DOMAIN, "appliance-1"), "test")
    assert appliance_device is not None
    assert appliance_device.serial_number == "appliance-1"
    assert appliance_device.sw_version == "6"
    assert appliance_device.hw_version == "G12"
    assert appliance_device.model == "Quantum QM100RF"
    assert appliance_device.manufacturer == "Dimplex"

    hub_device = device_registry.async_get_device_by_identifier((DOMAIN, "hub-1"), "test")
    assert hub_device is not None
    assert hub_device.serial_number == "hub-1"
    assert hub_device.sw_version == "129.12.5"
    assert hub_device.hw_version == "GW3042<Dimplex>"
    assert hub_device.model == "GatewayOther"

    # Parent linkage is expressed via registry via_device_id (not the deprecated
    # via_device identifier tuple). This mock zone has no ZoneId, so the appliance
    # links directly to the hub device.
    assert appliance_device.via_device_id == hub_device.id


async def test_mode_binary_sensors_reflect_the_engaged_modes(hass):
    """Per-mode diagnostics make a wrong mode mapping visible (#163)."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            # Timer + Boost engaged; Away / Frost / Advance are not.
            return_value=_mock_coordinator_payload(appliance_modes=BOOST_FLAG | 1),
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    def _state(needle: str):
        for state in hass.states.async_all():
            if state.entity_id.startswith("binary_sensor.") and needle in state.entity_id:
                return state
        return None

    # The payload has Timer + Boost engaged.
    assert _state("boost_active").state == "on"
    assert _state("away_active").state == "off"
    assert _state("frost_protection").state == "off"
    assert _state("advance_active").state == "off"


async def test_zone_devices_link_to_the_hub_without_deprecated_via_device(hass, caplog):
    """Zones must link to their hub by registry id, with no deprecation warning.

    Home Assistant deprecated the ``via_device`` identifier-tuple form in 2026.8 and
    removes it in 2027.8. ``_ensure_parent_devices`` used to pass it — and passing it
    even as ``None`` trips the warning, because the registry only skips the parameter
    when it is ``UNDEFINED``. So this asserts both the linkage and the silence.
    """
    from homeassistant.helpers import device_registry as dr

    payload = _mock_coordinator_payload()
    payload["appliances"][0]["zone"] = SimpleNamespace(ZoneId="zone-1", ZoneName="Living Room", ZoneType="Heating")

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    registry = dr.async_get(hass)
    hub_device = registry.async_get_device_by_identifier((DOMAIN, "hub-1"), "test")
    zone_device = registry.async_get_device_by_identifier((DOMAIN, "zone_zone-1"), "test")
    appliance_device = registry.async_get_device_by_identifier((DOMAIN, "appliance-1"), "test")

    assert hub_device is not None
    assert zone_device is not None
    assert appliance_device is not None

    # Hub → Zone → Appliance, each link by registry id.
    assert zone_device.via_device_id == hub_device.id
    assert appliance_device.via_device_id == zone_device.id
    assert hub_device.via_device_id is None

    assert "via_device" not in caplog.text, "deprecated via_device parameter is back"
