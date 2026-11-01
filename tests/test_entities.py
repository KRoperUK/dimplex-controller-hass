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
    # The detection setting, not a physical event: no window device class (#295).
    assert open_window_state.attributes.get("device_class") != "window"

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


def _hot_water_keys(hass) -> set[str]:
    from homeassistant.helpers import entity_registry as er

    return {
        str(entry.unique_id)
        for entry in er.async_get(hass).entities.values()
        if str(entry.unique_id).endswith("_hot_water_available")
    }


async def _setup_payload(hass, payload) -> None:
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch("custom_components.dimplex.DimplexApiClient.async_get_status_data", return_value=payload),
        patch("custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs", return_value={"energy": {}}),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_setback_prefers_the_live_frame_bit():
    """SetbackEnabledInStatusFrame wins over the SetbackEnabled setting (#295)."""
    from types import SimpleNamespace

    from custom_components.dimplex.binary_sensor import _setback_active

    assert _setback_active(None) is False
    # Frame bit present: it decides, even against the setting.
    assert _setback_active(SimpleNamespace(SetbackEnabled=True, SetbackEnabledInStatusFrame=False)) is False
    assert _setback_active(SimpleNamespace(SetbackEnabled=False, SetbackEnabledInStatusFrame=True)) is True
    # No frame bit: fall back to the setting.
    assert _setback_active(SimpleNamespace(SetbackEnabled=True)) is True
    assert _setback_active(SimpleNamespace(SetbackEnabled=False)) is False


async def test_open_window_sensor_has_no_window_device_class():
    """Detection setting must not present as a physical open/closed state (#295)."""
    from custom_components.dimplex.binary_sensor import APPLIANCE_BINARY_SENSORS

    description = next(d for d in APPLIANCE_BINARY_SENSORS if d.key == "open_window")
    assert description.device_class is None


async def test_a_panel_heater_gets_no_hot_water_sensor(hass):
    """Capability-gated, so a room heater gets no permanently unknown hot-water sensor."""
    await _setup_payload(hass, _mock_coordinator_payload())

    assert _hot_water_keys(hass) == set()


async def test_a_cylinder_gets_a_diagnostic_hot_water_sensor(hass):
    """A reported hot-water value is the only read the cloud gives for a cylinder.

    It is registered as a diagnostic sensor and disabled by default, so this checks the
    entity registry rather than live states.
    """
    from custom_components.dimplex.capabilities import capabilities_for_row

    payload = _mock_coordinator_payload()
    row = payload["appliances"][0]
    row["appliance"].ApplianceType = "Hot Water Cylinder"
    row["appliance"].FriendlyName = "Cylinder"
    row["status"].AvailableHotWater = 45.0
    assert capabilities_for_row(row["appliance"], row["status"]).hot_water is True

    await _setup_payload(hass, payload)

    assert _hot_water_keys(hass) == {"test_appliance-1_hot_water_available"}


def _status_row(*, modes=None, status_two=None, last_telem=None, prov=None, status_extra=None):
    """Build a status-backed row for direct sensor unit tests."""
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Heater",
        ApplianceModel="QRAD200E",
        ApplianceType="QRad",
        LastTelemDate=last_telem,
        automatic_provisioning=prov,
    )
    status_kwargs = {
        "ApplianceModes": modes,
        "StatusTwo": status_two,
        "RoomTemperature": 20.0,
        "ComfortStatus": False,
        "BoostDuration": 0,
    }
    if status_extra:
        status_kwargs.update(status_extra)
    status = SimpleNamespace(**status_kwargs)
    coordinator = SimpleNamespace(
        data={"appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}]}
    )
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace(boost_starts={}))
    return coordinator, config_entry, {"hub": hub, "zone": zone, "appliance": appliance, "status": status}


async def test_operating_mode_sensor_reports_flag_name_and_raw():
    """A known mode bit reports its flag name plus the raw integer (#298)."""
    from custom_components.dimplex.sensor import DimplexOperatingModeSensor

    coordinator, config_entry, row = _status_row(modes=128)
    sensor = DimplexOperatingModeSensor(coordinator, config_entry, row)

    assert sensor.native_value == "MANUAL"
    assert sensor.extra_state_attributes == {
        "active_modes": ["MANUAL"],
        "raw_modes": 128,
        "appliance_modes_known": True,
    }


async def test_operating_mode_sensor_exposes_unknown_bits_raw():
    """An unknown bit reports the raw value without inventing a name (#298)."""
    from custom_components.dimplex.sensor import DimplexOperatingModeSensor

    coordinator, config_entry, row = _status_row(modes=1 << 20)
    sensor = DimplexOperatingModeSensor(coordinator, config_entry, row)

    assert sensor.native_value == str(1 << 20)
    assert sensor.extra_state_attributes["active_modes"] == []
    assert sensor.extra_state_attributes["raw_modes"] == 1 << 20
    assert sensor.extra_state_attributes["appliance_modes_known"] is True


async def test_operating_mode_sensor_unknown_when_modes_absent():
    """None modes report unknown rather than a fabricated state (#298)."""
    from custom_components.dimplex.sensor import DimplexOperatingModeSensor

    coordinator, config_entry, row = _status_row(modes=None)
    sensor = DimplexOperatingModeSensor(coordinator, config_entry, row)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes["appliance_modes_known"] is False


async def test_operating_mode_does_not_special_case_bit_64():
    """Firmware-28 Manual-as-64 decodes as ECO, exactly like the library (#298)."""
    from custom_components.dimplex.sensor import DimplexOperatingModeSensor

    coordinator, config_entry, row = _status_row(modes=64)
    sensor = DimplexOperatingModeSensor(coordinator, config_entry, row)

    assert sensor.native_value == "ECO"
    assert sensor.extra_state_attributes["raw_modes"] == 64


async def test_last_telem_reads_the_appliance_field_and_filters_year_one():
    """The appliance LastTelemDate renders; the .NET unset date reads unknown (#301)."""
    from datetime import datetime

    from custom_components.dimplex.sensor import STATUS_SENSORS

    description = next(d for d in STATUS_SENSORS if d.key == "last_telem")
    real = datetime(2026, 10, 20, 12, 0, 0)
    _, _, row = _status_row(last_telem=real)
    assert description.value_fn(row["status"], row["appliance"]) == real

    _, _, row = _status_row(last_telem=datetime(1, 1, 1))
    assert description.value_fn(row["status"], row["appliance"]) is None


async def test_element_power_sensors_read_provisioning(hass):
    """Top/bottom element ratings appear next to rated_power (#300)."""
    from custom_components.dimplex.sensor import STATUS_SENSORS

    prov = SimpleNamespace(rated_power=2.0, top_element_power_rating=1.66, bottom_element_power_rating=0.34)
    _, _, row = _status_row(prov=prov)
    by_key = {d.key: d for d in STATUS_SENSORS}
    assert by_key["rated_power"].value_fn(None, row["appliance"]) == 2.0
    assert by_key["top_element_power"].value_fn(None, row["appliance"]) == 1.66
    assert by_key["bottom_element_power"].value_fn(None, row["appliance"]) == 0.34


async def test_boost_remaining_unknown_without_a_recorded_start():
    """A boost begun outside Home Assistant reads unknown, by design (#302)."""
    from custom_components.dimplex.sensor import DimplexBoostRemainingSensor

    coordinator, config_entry, row = _status_row(modes=2)
    sensor = DimplexBoostRemainingSensor(coordinator, config_entry, row)

    assert sensor.native_value is None


async def test_boost_remaining_counts_down_and_reaches_zero():
    """A boost started by Home Assistant counts down, then reports zero (#302)."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    from custom_components.dimplex.sensor import DimplexBoostRemainingSensor

    coordinator, config_entry, row = _status_row(modes=2)
    started = dt_util.utcnow() - timedelta(minutes=50)
    config_entry.runtime_data.boost_starts["appliance-1"] = {
        "started_at": started.isoformat(),
        "duration_minutes": 60,
    }
    sensor = DimplexBoostRemainingSensor(coordinator, config_entry, row)

    remaining = sensor.native_value
    assert remaining is not None and 9.0 < remaining < 11.0

    # Past the duration with the boost bit still set: reached zero.
    config_entry.runtime_data.boost_starts["appliance-1"] = {
        "started_at": (dt_util.utcnow() - timedelta(minutes=70)).isoformat(),
        "duration_minutes": 60,
    }
    assert sensor.native_value == 0.0


async def test_boost_remaining_retires_once_the_cloud_confirms_the_end():
    """After the boost bit clears, a spent countdown reads unknown (#302)."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    from custom_components.dimplex.sensor import DimplexBoostRemainingSensor

    coordinator, config_entry, row = _status_row(modes=1)
    config_entry.runtime_data.boost_starts["appliance-1"] = {
        "started_at": (dt_util.utcnow() - timedelta(minutes=70)).isoformat(),
        "duration_minutes": 60,
    }
    sensor = DimplexBoostRemainingSensor(coordinator, config_entry, row)

    assert sensor.native_value is None
    assert "appliance-1" not in config_entry.runtime_data.boost_starts


async def test_new_state_sensors_are_registered(hass):
    """Operating mode, StatusTwo, element powers and boost countdown all exist."""
    from homeassistant.helpers import entity_registry as er

    payload = _mock_coordinator_payload(appliance_modes=1)
    row = payload["appliances"][0]
    row["appliance"].ApplianceType = "QRad"
    row["status"].StatusTwo = 0
    row["appliance"].automatic_provisioning = SimpleNamespace(
        rated_power=2.0, top_element_power_rating=1.66, bottom_element_power_rating=0.34
    )
    await _setup_payload(hass, payload)

    registry = er.async_get(hass)
    for key in (
        "operating_mode",
        "status_two",
        "top_element_power",
        "bottom_element_power",
        "boost_remaining",
    ):
        assert registry.async_get_entity_id("sensor", DOMAIN, f"test_appliance-1_{key}") is not None, key


# ---------------------------------------------------------------------------
# Remaining helper and entity branches
# ---------------------------------------------------------------------------


async def test_extra_stored_data_serialises_the_held_values():
    """Both restore payloads carry their extra field alongside the state."""
    from custom_components.dimplex.sensor import _BoostExtraStoredData, _PeakExtraStoredData

    peak = _PeakExtraStoredData(12.5, "kWh", 42.0)
    assert peak.as_dict()["peak_total"] == 42.0

    boost = _BoostExtraStoredData(30.0, "min", "2026-01-01T00:00:00+00:00", 60)
    saved = boost.as_dict()
    assert saved["started_at"] == "2026-01-01T00:00:00+00:00"
    assert saved["duration_minutes"] == 60


async def test_restored_peak_ignores_unusable_shapes():
    """Only a finite number in ``peak_total`` is restored."""
    from custom_components.dimplex.sensor import _restored_peak

    class NotADict:
        def as_dict(self):
            return []

    class BooleanPeak:
        def as_dict(self):
            return {"peak_total": True}

    assert _restored_peak(None) is None
    assert _restored_peak(NotADict()) is None
    assert _restored_peak(BooleanPeak()) is None
    assert _restored_peak(SimpleNamespace(as_dict=lambda: {"peak_total": 3})) == 3.0


async def test_value_helpers_handle_missing_status():
    """The status readers answer None rather than raising without a status frame."""
    from custom_components.dimplex.sensor import (
        _operating_mode_names,
        _status_attr,
        _status_temp,
    )

    assert _status_attr("RoomTemperature")(None, None) is None
    assert _status_temp("RoomTemperature")(None, None) is None
    assert _operating_mode_names(None) is None
    assert _operating_mode_names("not-a-bitfield") is None
    assert _operating_mode_names(1 << 20) == []


async def test_provisioning_helper_reads_a_property_and_tolerates_missing_values():
    """Provisioning values come from a property or attribute, or read None."""
    from custom_components.dimplex.sensor import _provisioning_attr

    class WithProperty:
        @property
        def automatic_provisioning(self):
            return SimpleNamespace(rated_power=2.5)

    assert _provisioning_attr("rated_power")(None, WithProperty()) == 2.5
    assert _provisioning_attr("rated_power")(None, SimpleNamespace(automatic_provisioning=None)) is None
    assert (
        _provisioning_attr("rated_power")(
            None, SimpleNamespace(automatic_provisioning=SimpleNamespace(rated_power=None))
        )
        is None
    )


async def test_estimated_power_covers_each_heating_signal():
    """The estimate returns the rated power only while a heating signal is set."""
    from custom_components.dimplex.const import BOOST_FLAG
    from custom_components.dimplex.sensor import _estimated_power_kw

    no_rating = SimpleNamespace(automatic_provisioning=SimpleNamespace(rated_power=None))
    rated = SimpleNamespace(automatic_provisioning=SimpleNamespace(rated_power=2.0))

    assert _estimated_power_kw(None, no_rating) is None
    assert _estimated_power_kw(None, rated) == 0.0
    assert _estimated_power_kw(SimpleNamespace(ComfortStatus=True, ApplianceModes=0), rated) == 2.0
    assert _estimated_power_kw(SimpleNamespace(ComfortStatus=False, ApplianceModes=BOOST_FLAG), rated) == 2.0
    assert _estimated_power_kw(SimpleNamespace(ComfortStatus=False, ApplianceModes=0, BoostDuration=15), rated) == 2.0


async def test_operating_mode_sensor_tolerates_a_missing_or_unparseable_mode():
    """An absent or non-numeric mode reads unknown instead of raising."""
    from custom_components.dimplex.sensor import DimplexOperatingModeSensor

    coordinator, config_entry, row = _status_row(modes="not-a-number")
    sensor = DimplexOperatingModeSensor(coordinator, config_entry, row)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["raw_modes"] is None

    row["status"] = None
    assert sensor.native_value is None


async def test_schedule_sensor_handles_missing_schedule_and_timer_mode():
    """The schedule sensor is unavailable without a schedule and reads unknown without a mode."""
    from custom_components.dimplex.sensor import DimplexScheduleSensor

    coordinator, config_entry, row = _status_row()
    coordinator.last_update_success = True
    sensor = DimplexScheduleSensor(coordinator, config_entry, row)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    coordinator.data["schedules"] = {"appliance-1": SimpleNamespace(TimerMode=None)}
    assert sensor.native_value is None

    coordinator.last_update_success = False
    assert sensor.available is False


async def test_hot_water_schedule_sensor_handles_missing_and_malformed_schedules():
    """A cylinder schedule that is absent, empty or malformed never raises."""
    from custom_components.dimplex.sensor import DimplexHotWaterScheduleSensor, _clock

    coordinator, config_entry, row = _status_row()
    coordinator.last_update_success = True
    sensor = DimplexHotWaterScheduleSensor(coordinator, config_entry, row)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    coordinator.data["schedules"] = {"appliance-1": {"TimerPeriods": []}}
    assert sensor.native_value == "no periods"

    coordinator.data["schedules"] = {"appliance-1": {"TimerPeriods": [{"DayOfWeek": "bad", "StartTime": 0}]}}
    assert sensor.native_value == "no periods"

    coordinator.last_update_success = False
    assert sensor.available is False
    assert _clock("noon") is None


async def test_boost_remaining_handles_missing_and_malformed_records():
    """A missing, malformed or expired boost record reads unknown or zero."""
    from custom_components.dimplex.sensor import DimplexBoostRemainingSensor

    coordinator, config_entry, row = _status_row()
    sensor = DimplexBoostRemainingSensor(coordinator, config_entry, row)

    config_entry.runtime_data.boost_starts = None
    assert sensor.native_value is None

    config_entry.runtime_data.boost_starts = {"appliance-1": {"duration_minutes": "x"}}
    assert sensor.native_value is None

    config_entry.runtime_data.boost_starts = {"appliance-1": {"duration_minutes": 30, "started_at": "not-a-date"}}
    assert sensor.native_value is None

    config_entry.runtime_data.boost_starts = {
        "appliance-1": {"duration_minutes": 1, "started_at": "2020-01-01T00:00:00+00:00"}
    }
    row["status"] = None
    assert sensor.native_value == 0.0


async def test_boost_remaining_restores_a_recorded_start():
    """A stored engage record is restored unless one is already in runtime data."""
    from unittest.mock import AsyncMock

    from custom_components.dimplex.sensor import DimplexBoostRemainingSensor

    sensor = object.__new__(DimplexBoostRemainingSensor)
    sensor._appliance = SimpleNamespace(ApplianceId="appliance-1")
    sensor.coordinator = SimpleNamespace(async_add_listener=lambda *a, **k: lambda: None)
    sensor.coordinator_context = None
    sensor.async_on_remove = lambda func: None
    sensor.async_get_last_extra_data = AsyncMock(
        return_value=SimpleNamespace(
            as_dict=lambda: {
                "started_at": "2026-01-01T00:00:00+00:00",
                "duration_minutes": "60",
            }
        )
    )

    # No runtime data at all: nothing to restore into.
    sensor.config_entry = SimpleNamespace(runtime_data=None)
    await sensor.async_added_to_hass()

    # A record already present wins over the stored one.
    runtime = SimpleNamespace(boost_starts={"appliance-1": {"duration_minutes": 30}})
    sensor.config_entry = SimpleNamespace(runtime_data=runtime)
    await sensor.async_added_to_hass()
    assert runtime.boost_starts["appliance-1"]["duration_minutes"] == 30

    # Otherwise the stored record is adopted.
    runtime.boost_starts = {}
    await sensor.async_added_to_hass()
    assert runtime.boost_starts["appliance-1"]["duration_minutes"] == 60


async def test_energy_sensor_falls_back_to_utc_without_a_configured_time_zone():
    """A missing default time zone must not break the summary."""
    from unittest.mock import patch

    from custom_components.dimplex.sensor import DimplexEnergySensor

    sensor = object.__new__(DimplexEnergySensor)
    with patch(
        "custom_components.dimplex.sensor.dt_util.get_default_time_zone",
        side_effect=RuntimeError("no tz"),
    ):
        assert str(sensor._local_tz()) == "UTC"


async def test_lifetime_sensor_restores_the_peak_from_the_previous_state():
    """The held peak comes from the state's ``peak_total`` attribute as a fallback."""
    from unittest.mock import AsyncMock

    from homeassistant.components.sensor import SensorStateClass
    from homeassistant.core import State

    from custom_components.dimplex.sensor import DimplexEnergySensor

    sensor = object.__new__(DimplexEnergySensor)
    sensor.entity_description = SimpleNamespace(mode="lifetime", state_class=SensorStateClass.TOTAL)
    sensor._peak_total = 0.0
    sensor.coordinator = SimpleNamespace(async_add_listener=lambda *a, **k: lambda: None)
    sensor.coordinator_context = None
    sensor.async_on_remove = lambda func: None
    sensor.async_get_last_extra_data = AsyncMock(return_value=None)
    sensor.async_get_last_state = AsyncMock(return_value=State("sensor.energy", "12.5", {"peak_total": 12.5}))
    sensor.async_get_last_sensor_data = AsyncMock(return_value=None)

    await sensor.async_added_to_hass()

    assert sensor._peak_total == 12.5


async def test_energy_sensor_without_a_summary_has_no_window_metadata():
    """An unavailable series reports no reset point and no attributes."""
    from homeassistant.components.sensor import SensorStateClass

    from custom_components.dimplex.sensor import DimplexEnergySensor

    sensor = object.__new__(DimplexEnergySensor)
    sensor.entity_description = SimpleNamespace(mode="daily", state_class=SensorStateClass.TOTAL, register="t1")
    sensor._summary = lambda: None

    assert sensor.last_reset is None
    assert sensor.extra_state_attributes == {}
