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


async def _setup(hass, payload):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    entry.add_to_hass(hass)
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch("custom_components.dimplex.DimplexApiClient.async_get_status_data", return_value=payload),
        patch("custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs", return_value={"energy": {}}),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_holiday_switch_and_end_time(hass):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    payload = _payload()
    cylinder_status = payload["appliances"][0]["status"]

    async def fake_holiday(_self, hub_id, appliance_id, *, enable, until=None, heat_pump=False):
        calls.append((hub_id, appliance_id, enable, until, heat_pump))
        cylinder_status.ApplianceModes = 8200 if enable else 8192

    calls: list = []
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_get_status_data", return_value=payload),
        patch("custom_components.dimplex.DimplexApiClient.async_set_hot_water_holiday", fake_holiday),
    ):
        await _setup(hass, payload)
        switch_id = "switch.hot_water_hot_water_holiday"
        end_id = "datetime.hot_water_hot_water_holiday_ends"
        assert hass.states.get(switch_id).state == "off"
        assert hass.states.get(end_id).state == "unknown"
        # Panel heaters get neither.
        assert hass.states.get("switch.hall_hall_holiday") is None

        end = (dt_util.utcnow() + timedelta(hours=30)).replace(microsecond=0)
        await hass.services.async_call("datetime", "set_value", {"entity_id": end_id, "datetime": end}, blocking=True)
        assert dt_util.parse_datetime(hass.states.get(end_id).state) == end
        assert calls == []  # choosing an end alone sends nothing

        await hass.services.async_call("switch", "turn_on", {"entity_id": switch_id}, blocking=True)
        await hass.async_block_till_done()
        assert calls[-1] == ("hub-1", "cyl-1", True, end, True)
        assert hass.states.get(switch_id).state == "on"
        assert hass.states.get("binary_sensor.hot_water_hot_water_holiday").state == "on"

        # Home Assistant clears Holiday at the exact end time.
        async_fire_time_changed(hass, end + timedelta(seconds=1))
        await hass.async_block_till_done()
        assert calls[-1][2] is False
        assert hass.states.get(switch_id).state == "off"


@pytest.mark.asyncio
async def test_holiday_without_end_defaults_to_a_week_and_off_cancels(hass):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    payload = _payload()
    cylinder_status = payload["appliances"][0]["status"]
    calls: list = []

    async def fake_holiday(_self, hub_id, appliance_id, *, enable, until=None, heat_pump=False):
        calls.append((enable, until))
        cylinder_status.ApplianceModes = 8200 if enable else 8192

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_get_status_data", return_value=payload),
        patch("custom_components.dimplex.DimplexApiClient.async_set_hot_water_holiday", fake_holiday),
    ):
        entry = await _setup(hass, payload)
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": "switch.hot_water_hot_water_holiday"}, blocking=True
        )
        enable, until = calls[-1]
        assert enable is True
        assert timedelta(days=6, hours=23) < until - dt_util.utcnow() <= timedelta(days=7)
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": "switch.hot_water_hot_water_holiday"}, blocking=True
        )
        assert calls[-1] == (False, None)
        assert not entry.runtime_data.holiday._timers


@pytest.mark.asyncio
async def test_holiday_end_in_the_past_is_rejected(hass):
    from datetime import timedelta

    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.util import dt as dt_util

    await _setup(hass, _payload())
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": "datetime.hot_water_hot_water_holiday_ends",
                "datetime": dt_util.utcnow() - timedelta(hours=1),
            },
            blocking=True,
        )


@pytest.mark.asyncio
async def test_restored_end_that_passed_while_down_clears_holiday(hass):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    payload = _payload()
    payload["appliances"][0]["status"].ApplianceModes = 8200
    entry = await _setup(hass, payload)
    manager = entry.runtime_data.holiday
    stops: list = []

    async def fake_stop(appliance_id):
        stops.append(appliance_id)

    manager.async_stop = fake_stop
    manager.restore_end("cyl-1", dt_util.utcnow() - timedelta(minutes=5))
    await hass.async_block_till_done()
    assert stops == ["cyl-1"]

    manager.restore_end("cyl-1", dt_util.utcnow() + timedelta(hours=2))
    assert "cyl-1" in manager._timers
    manager.async_shutdown()
    assert not manager._timers


async def test_api_holiday_sends_rounded_up_days(hass):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock

    from dimplex_controller import ApplianceModeFlag

    from custom_components.dimplex.api import DimplexApiClient

    api = DimplexApiClient.__new__(DimplexApiClient)
    api._client = SimpleNamespace(set_mode_flag=AsyncMock())
    until = datetime.now(UTC) + timedelta(days=2, hours=3)
    await api.async_set_hot_water_holiday("hub", "cyl", enable=True, until=until, heat_pump=True)
    args, kwargs = api._client.set_mode_flag.call_args
    assert args == ("hub", ["cyl"], ApplianceModeFlag.HOLIDAY)
    assert kwargs["enable"] is True and kwargs["number_of_days"] == 3 and kwargs["until"] == until
    assert kwargs["endpoint"] == "/RemoteControl/SetApplianceModeHeatPumpHwc"

    await api.async_set_hot_water_holiday("hub", "cyl", enable=False)
    _, kwargs = api._client.set_mode_flag.call_args
    assert kwargs["enable"] is False and kwargs["number_of_days"] == 0
    assert kwargs["endpoint"] == "/RemoteControl/SetApplianceModeHwc"

    with pytest.raises(ValueError):
        await api.async_set_hot_water_holiday("hub", "cyl", enable=True)


@pytest.mark.asyncio
async def test_holiday_end_survives_a_restart(hass):
    from datetime import timedelta

    from homeassistant.core import State
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import mock_restore_cache

    end = (dt_util.utcnow() + timedelta(days=2)).replace(microsecond=0)
    mock_restore_cache(hass, [State("datetime.hot_water_hot_water_holiday_ends", end.isoformat())])
    payload = _payload()
    payload["appliances"][0]["status"].ApplianceModes = 8200  # on holiday
    entry = await _setup(hass, payload)

    assert dt_util.parse_datetime(hass.states.get("datetime.hot_water_hot_water_holiday_ends").state) == end
    assert entry.runtime_data.holiday.ends["cyl-1"] == end
    assert "cyl-1" in entry.runtime_data.holiday._timers


LIVE_SCHEDULE = {
    "HubId": "hub-1",
    "ApplianceId": "cyl-1",
    "TimerPeriods": [{"DayOfWeek": d, "StartTime": 0, "Mode": 2} for d in (1, 2, 3, 4, 5, 6, 0)],
}


@pytest.mark.asyncio
async def test_hot_water_schedule_sensor(hass):
    with patch(
        "custom_components.dimplex.DimplexApiClient.async_get_hot_water_schedule",
        return_value=LIVE_SCHEDULE,
    ) as fetch:
        await _setup(hass, _payload())
    fetch.assert_awaited_once_with("hub-1", "cyl-1")

    state = hass.states.get("sensor.hot_water_hot_water_hot_water_schedule")
    assert state.state == "Mon–Sun 00:00 mode 2"
    assert state.attributes["monday"] == [{"start": "00:00", "start_raw": 0, "mode": 2}]
    assert state.attributes["current_mode"] == 2
    assert state.attributes["period_count"] == 7
    # The panel heater keeps the room-heater schedule sensor.
    assert hass.states.get("sensor.hall_hall_schedule") is not None


@pytest.mark.asyncio
async def test_hot_water_schedule_summary_groups_days(hass):
    schedule = {
        "TimerPeriods": [
            {"DayOfWeek": d, "StartTime": s, "Mode": m}
            for d in (1, 2, 3, 4, 5)
            for s, m in ((0, 0), (390, 2), (1320, 0))
        ]
        + [{"DayOfWeek": 6, "StartTime": 0, "Mode": 2}, {"DayOfWeek": 0, "StartTime": 0, "Mode": 2}]
    }
    with patch("custom_components.dimplex.DimplexApiClient.async_get_hot_water_schedule", return_value=schedule):
        await _setup(hass, _payload())
    state = hass.states.get("sensor.hot_water_hot_water_hot_water_schedule")
    assert state.state == "Mon–Fri 00:00 mode 0, 06:30 mode 2, 22:00 mode 0; Sat–Sun 00:00 mode 2"


async def test_api_reads_cylinder_schedule_raw(hass):
    from unittest.mock import AsyncMock

    from custom_components.dimplex.api import DimplexApiClient

    api = DimplexApiClient.__new__(DimplexApiClient)
    api._client = SimpleNamespace(_request=AsyncMock(return_value=LIVE_SCHEDULE))
    assert await api.async_get_hot_water_schedule("hub-1", "cyl-1") == LIVE_SCHEDULE
    api._client._request.assert_awaited_once_with(
        "POST",
        "/RemoteControl/ApiGetTimerModeDetailsForHeatPumpHwcAppliance",
        json={"HubId": "hub-1", "ApplianceId": "cyl-1"},
    )
    api._client._request.return_value = None
    assert await api.async_get_hot_water_schedule("hub-1", "cyl-1") == {}
