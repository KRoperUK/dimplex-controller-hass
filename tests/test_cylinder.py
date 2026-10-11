"""Hot-water cylinder (ASHW) support, using a live EDL200UK-630RF overview row."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from dimplex_controller.models import ApplianceStatus
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.dimplex.api  # noqa: F401  (applies the ApplianceStatus shim)
from custom_components.dimplex.capabilities import capabilities_for_row
from custom_components.dimplex.const import DOMAIN, hot_water_mode

from .const import MOCK_ENTRY_DATA

# GetApplianceOverview row from a live cylinder the Dimplex app showed as
# "Timer", 45°, 336 L hot water, green energy active, hygiene every 7 days.
CYLINDER_OVERVIEW = {
    "HubId": "hub-1",
    "ApplianceId": "cyl-1",
    "ZoneId": "zone-hw",
    "StatusTwo": 0,
    "ApplianceModes": 8192,
    "RoomTemperature": None,
    "ActiveSetPointTemperature": 45,
    "NormalTemperature": None,
    "BoostDuration": 0,
    "AvailableHotWater": 336,
    "HygieneTemperature": None,
    "HygieneFrequency": 7,
    "HolidayNumOfDays": 0,
    "Capacity": 200,
    "ErrorCode": 0,
    "WarningCode": 0,
    "IsGreenEnergyActive": True,
    "HeatingUp": False,
}

PANEL_OVERVIEW = {
    "HubId": "hub-1",
    "ApplianceId": "panel-1",
    "ZoneId": "zone-hall",
    "ApplianceModes": 32,
    "RoomTemperature": 18,
    "ActiveSetPointTemperature": 7,
    "OpenWindowEnabled": True,
    "EcoStartEnabled": False,
    "SetbackEnabled": False,
    "ComfortStatus": False,
    "ErrorCode": None,
    "WarningCode": None,
}


def _cylinder_appliance():
    return SimpleNamespace(
        ApplianceId="cyl-1",
        ApplianceType="ASHW Cylinder",
        ApplianceModel="EDL200UK-630RF",
        FriendlyName="Hot Water",
        FirmwareVersion="44.0",
        SeriesIdentifier="A",
        LastTelemDate=None,
        ProductModelExtensions={},
    )


def _payload():
    hub = SimpleNamespace(HubId="hub-1", FriendlyName="Hub", HubType="Gateway", ConnectionState=1)
    panel = SimpleNamespace(
        ApplianceId="panel-1",
        ApplianceType="PLXE",
        ApplianceModel="PLX100E",
        FriendlyName="Hall",
        LastTelemDate=None,
        ProductModelExtensions={},
    )
    return {
        "appliances": [
            {
                "hub": hub,
                "zone": SimpleNamespace(ZoneId="zone-hw", ZoneName="Hot water"),
                "appliance": _cylinder_appliance(),
                "status": ApplianceStatus.model_validate(CYLINDER_OVERVIEW),
            },
            {
                "hub": hub,
                "zone": SimpleNamespace(ZoneId="zone-hall", ZoneName="Hall"),
                "appliance": panel,
                "status": ApplianceStatus.model_validate(PANEL_OVERVIEW),
            },
        ],
        "hubs": [hub],
    }


def test_shim_keeps_cylinder_only_fields():
    status = ApplianceStatus.model_validate(CYLINDER_OVERVIEW)
    assert status.Capacity == 200
    assert status.IsGreenEnergyActive is True
    assert status.HygieneFrequency == 7
    assert status.ErrorCode == "0"


def test_cylinder_is_not_room_climate():
    caps = capabilities_for_row(_cylinder_appliance(), ApplianceStatus.model_validate(CYLINDER_OVERVIEW))
    assert caps.hot_water and caps.heat_pump and caps.hygiene
    assert not caps.climate
    for flag in ("boost", "away", "advance", "open_window", "eco_start", "setback_read", "frost", "setpoint_write"):
        assert not getattr(caps, flag), flag


def test_cylinder_with_room_temperature_keeps_climate():
    status = ApplianceStatus.model_validate({**CYLINDER_OVERVIEW, "RoomTemperature": 19})
    caps = capabilities_for_row(_cylinder_appliance(), status)
    assert caps.climate and caps.open_window


def test_fallback_derivation_also_strips_room_features():
    with patch("custom_components.dimplex.capabilities._lib_capabilities_for", None):
        caps = capabilities_for_row(_cylinder_appliance(), ApplianceStatus.model_validate(CYLINDER_OVERVIEW))
    assert caps.hot_water and not caps.climate and not caps.eco_start


@pytest.mark.parametrize(
    ("modes", "expected"),
    [
        (8192, "timer"),
        (1, "timer"),
        (16384, "standby"),
        (8 | 8192, "holiday"),
        (2 | 8192, "boost"),
        (256 | 8192, "hygiene"),
        (0, None),
        (None, None),
    ],
)
def test_hot_water_mode(modes, expected):
    assert hot_water_mode(SimpleNamespace(ApplianceModes=modes)) == expected


@pytest.mark.asyncio
async def test_cylinder_entities(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    entry.add_to_hass(hass)
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch("custom_components.dimplex.DimplexApiClient.async_get_status_data", return_value=_payload()),
        patch("custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs", return_value={"energy": {}}),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    ids = {state.entity_id for state in hass.states.async_all()}

    heater = hass.states.get("water_heater.hot_water_hot_water")
    assert heater is not None
    assert heater.state == "timer"
    assert heater.attributes["temperature"] == 45
    assert heater.attributes["hot_water_available"] == 336
    assert heater.attributes["capacity"] == 200
    assert heater.attributes["green_energy_active"] is True

    assert hass.states.get("sensor.hot_water_hot_water_hot_water_available").state == "336.0"
    assert hass.states.get("sensor.hot_water_hot_water_hot_water_capacity").state == "200"
    assert hass.states.get("sensor.hot_water_hot_water_hot_water_mode").state == "timer"
    assert hass.states.get("sensor.hot_water_hot_water_hygiene_recurrence").state == "weekly"
    assert hass.states.get("sensor.hot_water_hot_water_holiday_days").state == "0"
    assert hass.states.get("sensor.hot_water_hot_water_target_temperature").state == "45.0"
    assert hass.states.get("binary_sensor.hot_water_hot_water_green_energy").state == "on"
    assert hass.states.get("binary_sensor.hot_water_hot_water_heating_water").state == "off"
    assert hass.states.get("binary_sensor.hot_water_hot_water_holiday").state == "off"

    # No room-heater entities for the cylinder…
    cylinder_ids = {i for i in ids if ".hot_water_hot_water" in i}
    for unwanted in ("climate.", "room_temperature", "open_window", "ecostart", "setback", "comfort", "boost_duration"):
        assert not any(unwanted in i for i in cylinder_ids), unwanted

    # …while the panel heater keeps its climate entity and has no hot-water ones.
    assert "climate.hall_hall" in ids
    assert "switch.hall_hall_ecostart" in ids
    assert not any(i.startswith("water_heater.hall") for i in ids)
    assert not any(i.startswith("sensor.hall_hot_water") for i in ids)
