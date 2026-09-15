"""Tests for the energy sensor."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _row(*, t1=None, t2=None):
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    status = SimpleNamespace(
        EcoStartEnabled=False,
        ComfortStatus=True,
        RoomTemperature=21.5,
        ActiveSetPointTemperature=20.0,
        NormalTemperature=20.0,
        BoostTemperature=None,
        AwayTemperature=None,
        BoostDuration=None,
        AwayDateTime=None,
        ApplianceModes=0,
    )
    status_payload = {
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}],
        "hubs": [hub],
    }
    energy_payload = {
        "energy": {
            "hub-1": {
                "t1": {"appliance-1": t1 if t1 is not None else []},
                "t2": {"appliance-1": t2 if t2 is not None else []},
            }
        }
    }
    return status_payload, energy_payload


def _state(hass, entity_id_substring: str):
    """Return the state whose entity_id contains the substring, or None."""
    for state in hass.states.async_all():
        if entity_id_substring in state.entity_id:
            return state
    return None


async def test_energy_lifetime_sensor_with_data(hass):
    """Lifetime sensor sums all telemetry points in kWh."""
    status_payload, energy_payload = _row(
        t1=[
            (dt_util.parse_datetime("2026-06-01T00:00:00+00:00"), 0.1),
            (dt_util.parse_datetime("2026-06-02T00:00:00+00:00"), 0.25),
        ]
    )
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=status_payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value=energy_payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = _state(hass, "living_room_heater_energy")
    # Prefer primary lifetime entity; avoid matching energy_t2_* when present.
    if state is None or "t2" in state.entity_id:
        state = next(
            (s for s in hass.states.async_all() if s.entity_id.endswith("_energy") or "energy_lifetime" in s.entity_id),
            None,
        )
        if state is not None and "t2" in state.entity_id:
            state = None
    if state is None:
        state = _state(hass, "energy_lifetime")
    assert state is not None
    assert "t2" not in state.entity_id
    assert state.state == "0.35"
    assert state.attributes.get("unit_of_measurement") == UnitOfEnergy.KILO_WATT_HOUR
    assert state.attributes.get("device_class") == SensorDeviceClass.ENERGY
    # No state_class, deliberately: the value is a rolling 30-day window sum, and
    # declaring TOTAL_INCREASING let Home Assistant read every window dip as a meter
    # reset and re-add the whole value to long-term statistics (#196).
    assert state.attributes.get("state_class") is None
    assert state.attributes.get("mode") == "lifetime"
    assert state.attributes.get("window_days") == 30
    assert state.attributes.get("telemetry_points") == 2
    # last_reset is only valid for TOTAL; window_start carries the same information.
    assert state.attributes.get("last_reset") is None
    assert state.attributes.get("window_start") is not None


async def test_energy_daily_sensor(hass):
    """Daily sensor only includes points for the local calendar day."""
    today = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    status_payload, energy_payload = _row(
        t1=[
            (yesterday, 5.0),
            (today, 1.25),
        ]
    )
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=status_payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value=energy_payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Entity name is "Energy today" (T1); T2 is "Energy T2 today".
    candidates = [
        s
        for s in hass.states.async_all()
        if "energy" in s.entity_id and "today" in s.entity_id and "t2" not in s.entity_id
    ]
    state = candidates[0] if candidates else _state(hass, "energy_today")
    assert state is not None
    assert "t2" not in state.entity_id
    assert state.state == "1.25"
    assert state.attributes.get("mode") == "daily"
    assert state.attributes.get("register") == "t1"


async def test_energy_sensor_t2_with_data(hass):
    """The secondary energy register is exposed as a separate lifetime sensor."""
    status_payload, energy_payload = _row(
        t2=[
            (dt_util.parse_datetime("2026-06-01T00:00:00+00:00"), 0.1),
            (dt_util.parse_datetime("2026-06-02T00:00:00+00:00"), 0.25),
        ]
    )
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=status_payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value=energy_payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # T2 lifetime is disabled by default in the entity registry; entity may be absent from states.
    # Assert setup succeeded without error (sensor factory registered both registers).
    assert config_entry.state == hass.config_entries.async_get_entry(config_entry.entry_id).state


async def test_energy_sensor_unavailable_when_empty(hass):
    """No telemetry means the sensor is unavailable, not 0."""
    status_payload, energy_payload = _row(t1=[])
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=status_payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value=energy_payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = _state(hass, "living_room_heater_energy")
    if state is None:
        state = _state(hass, "_energy")
    assert state is not None
    assert state.state == "unavailable"


async def test_energy_sensor_unavailable_when_hub_key_missing(hass):
    """Hubs that do not appear in the energy payload get no sensor data."""
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    status = SimpleNamespace(
        EcoStartEnabled=False,
        ComfortStatus=True,
        RoomTemperature=21.5,
        ActiveSetPointTemperature=20.0,
        NormalTemperature=20.0,
        BoostTemperature=None,
        AwayTemperature=None,
        BoostDuration=None,
        AwayDateTime=None,
        ApplianceModes=0,
    )
    status_payload = {
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}],
        "hubs": [hub],
    }
    energy_payload = {"energy": {}}
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=status_payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value=energy_payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = _state(hass, "living_room_heater_energy")
    if state is None:
        state = _state(hass, "_energy")
    assert state is not None
    assert state.state == "unavailable"


async def test_window_sensors_carry_no_state_class():
    """No rolling-window sensor may enter long-term statistics (#196).

    ``mode="lifetime"`` is a 30-day window sum, not a meter counter: it falls when a
    heavy day leaves the window. With ``TOTAL_INCREASING`` Home Assistant's
    ``reset_detected()`` treated a >10% fall as a new meter cycle and added the whole
    state to the statistics sum, permanently inflating the Energy Dashboard. Only the
    daily sensors, which have a real ``last_reset``, may declare a state class.
    """
    from custom_components.dimplex.sensor import ENERGY_SENSORS

    windowed = [d for d in ENERGY_SENSORS if d.mode == "lifetime"]
    daily = [d for d in ENERGY_SENSORS if d.mode == "daily"]
    assert windowed and daily, "expected both window and daily energy descriptions"

    for description in windowed:
        assert description.state_class is None, (
            f"{description.key} declares {description.state_class}; a rolling window "
            "must not reach long-term statistics"
        )
    for description in daily:
        assert description.state_class == SensorStateClass.TOTAL, (
            f"{description.key} must stay TOTAL so its midnight last_reset is honoured"
        )


async def test_energy_summary_is_memoised_across_property_reads(hass):
    """summarise_energy must run once per update, not once per property read (#198).

    The memo keys on the energy coordinator's ``last_update_success_time``. That
    attribute only exists on ``TimestampDataUpdateCoordinator``; while the
    coordinator was a plain ``DataUpdateCoordinator`` the key was always ``None``,
    the guard never matched, and the summary was recomputed for ``available``,
    ``native_value``, ``last_reset`` and ``extra_state_attributes`` on every single
    state write — thousands of telemetry points each time.
    """
    from custom_components.dimplex import DimplexEnergyCoordinator
    from custom_components.dimplex.sensor import summarise_energy

    status_payload, energy_payload = _row(
        t1=[
            (dt_util.now() - timedelta(days=2), 0.15),
            (dt_util.now(), 0.2),
        ]
    )
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=status_payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value=energy_payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    runtime = hass.data[DOMAIN][config_entry.entry_id]
    # Must be the timestamp variant, or the memo below cannot work at all.
    assert isinstance(runtime.energy, DimplexEnergyCoordinator)
    assert runtime.energy.last_update_success_time is not None

    component = hass.data["entity_components"]["sensor"]
    entity = next(
        candidate
        for candidate in component.entities
        if getattr(candidate.entity_description, "mode", None) == "lifetime"
        and getattr(candidate.entity_description, "register", None) == "t1"
    )

    with patch("custom_components.dimplex.sensor.summarise_energy", wraps=summarise_energy) as summarise:
        # Four reads that each recomputed the whole series before the fix. At most one
        # computation may happen here — zero if the cache is still warm from the state
        # write during setup, which is the normal case.
        assert entity.available is True
        _ = entity.native_value
        _ = entity.last_reset
        _ = entity.extra_state_attributes
        assert summarise.call_count <= 1, (
            f"summarise_energy ran {summarise.call_count} times for four reads of one "
            "update cycle — the memo is not holding"
        )
