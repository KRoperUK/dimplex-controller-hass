"""Tests for the energy sensor."""

import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _metered_appliance(**overrides):
    """An appliance the capability matrix calls metered.

    ``energy_meter`` is derived by the library from the automatic-provisioning row
    (a rated power) or a storage family token, which is why the payload carries one:
    the energy entities are gated on it (#280). The rated power and charge capacity
    sit behind diagnostic sensors that are disabled by default, so adding it does not
    add states to these tests.
    """
    fields = {
        "ApplianceId": "appliance-1",
        "FriendlyName": "Living Room Heater",
        "ApplianceModel": "Model X",
        "automatic_provisioning": SimpleNamespace(rated_power=2.0, charge_capacity=None),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _appliance_status():
    """A live-overview status with the fields the capability matrix reads.

    Every field the library's ``capabilities_for`` reads has to be present, even
    when it is ``None``: an attribute it cannot read makes the derivation raise, and
    the adapter then falls back to name-only tokens — which is not what a real
    payload would do.
    """
    return SimpleNamespace(
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
        AvailableHotWater=None,
        OpenWindowEnabled=None,
        SetbackEnabled=None,
        SetbackTemperature=None,
    )


def _row(*, t1=None, t2=None, appliance=None):
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = appliance if appliance is not None else _metered_appliance()
    status = _appliance_status()
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
    # The cumulative sensors are rising meters over everything the cloud returns, so
    # they declare TOTAL_INCREASING and the Energy Dashboard can use them (#227).
    assert state.attributes.get("state_class") == SensorStateClass.TOTAL_INCREASING
    assert state.attributes.get("mode") == "lifetime"
    assert state.attributes.get("telemetry_points") == 2
    # last_reset is only set for TOTAL; window_start carries the span instead.
    assert state.attributes.get("last_reset") is None
    assert state.attributes.get("window_start") is not None
    # No window_days: it used to assert a fixed 30 days that the data never matched.
    assert "window_days" not in state.attributes


async def test_a_day_with_no_samples_yet_reads_zero_rather_than_unavailable(hass):
    """An empty day window is 0 kWh when the series itself has points (#281).

    ``available`` required the *current day's* summary to have points, so
    ``energy_today`` was unavailable from local midnight until the cloud published
    today's first sample — every night, for every metered appliance. The series is
    what availability follows: a day with nothing on it is a real reading of zero.
    """
    today = dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    status_payload, energy_payload = _row(t1=[(yesterday, 5.0)])

    registry = await _setup_row(hass, status_payload, energy_payload)

    daily_id = registry.async_get_entity_id("sensor", DOMAIN, "test_appliance-1_energy_daily")
    assert daily_id is not None
    state = hass.states.get(daily_id)
    assert state is not None
    assert state.state == "0.0", "an empty day is zero kWh, not unknown"
    assert state.attributes.get("telemetry_points") == 0
    # TOTAL with a last_reset at local midnight is what makes the zero legible to
    # statistics as "this day started", rather than a gap.
    assert state.attributes.get("last_reset") is not None

    # The cumulative sensor still reports the history it does have.
    lifetime_id = registry.async_get_entity_id("sensor", DOMAIN, "test_appliance-1_energy")
    assert lifetime_id is not None
    lifetime = hass.states.get(lifetime_id)
    assert lifetime is not None and float(lifetime.state) == 5.0


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
    """The secondary energy register is exposed as a separate lifetime sensor.

    T1 is left empty here, so the two registers cannot be confused: a sensor that
    read the wrong register, or fell back to T1, would be unavailable instead of
    reporting the sum of the T2 series. The old assertion compared the config
    entry's state with itself, so a T2 sensor built from T1 passed (#290).
    """
    status_payload, energy_payload = _row(
        t2=[
            (dt_util.parse_datetime("2026-06-01T00:00:00+00:00"), 0.1),
            (dt_util.parse_datetime("2026-06-02T00:00:00+00:00"), 0.25),
        ]
    )
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    # The T2 lifetime entity is disabled by default: setup registers it and then
    # skips it, so it never reaches the state machine. Pre-creating the registry
    # entry enabled, which is what enabling it in the UI leaves behind, makes it
    # addable while keeping the real setup path under test.
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "test_appliance-1_energy_t2",
        suggested_object_id="living_room_heater_energy_t2",
        config_entry=config_entry,
    )

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

    entity_id = registry.async_get_entity_id("sensor", DOMAIN, "test_appliance-1_energy_t2")
    assert entity_id is not None, "setup did not register the T2 lifetime sensor"
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == pytest.approx(0.35), "0.1 + 0.25 from the T2 series"
    assert state.attributes.get("register") == "t2"

    # The control: T1 has no points in this payload, so the T1 lifetime entity is
    # unavailable. A T2 sensor reading the wrong register could not do both.
    t1_id = registry.async_get_entity_id("sensor", DOMAIN, "test_appliance-1_energy")
    assert t1_id is not None
    t1_state = hass.states.get(t1_id)
    assert t1_state is not None
    assert t1_state.state == "unavailable"


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
    appliance = _metered_appliance()
    status = _appliance_status()
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


async def _setup_row(hass, status_payload, energy_payload):
    """Set up the entry over the given payloads and return the entity registry."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch("custom_components.dimplex.DimplexApiClient.async_get_status_data", return_value=status_payload),
        patch("custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs", return_value=energy_payload),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return er.async_get(hass)


async def test_an_unmetered_appliance_gets_no_energy_entities(hass):
    """No ``energy_meter`` capability means no energy entities at all (#280).

    Every appliance used to get the four energy sensors whether or not the cloud
    ever returns telemetry for it, so an unmetered heater carried four permanently
    unavailable entities — two of them enabled by default — recreated on each
    reload. They are gated on the same capability the rest of the platform uses.
    """
    from custom_components.dimplex.sensor import ENERGY_SENSORS

    unmetered = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    status_payload, energy_payload = _row(t1=[(dt_util.now(), 0.5)], appliance=unmetered)

    from custom_components.dimplex.capabilities import capabilities_for_row

    row = status_payload["appliances"][0]
    assert capabilities_for_row(row["appliance"], row["status"], row.get("product")).energy_meter is False

    registry = await _setup_row(hass, status_payload, energy_payload)

    for description in ENERGY_SENSORS:
        assert registry.async_get_entity_id("sensor", DOMAIN, f"test_appliance-1_{description.key}") is None, (
            f"{description.key} was created for an appliance without the energy_meter capability"
        )
    # The rest of the appliance's entities are still there, so this is the gate and
    # not a setup that quietly did nothing.
    assert registry.async_get_entity_id("sensor", DOMAIN, "test_appliance-1_room_temperature") is not None


async def test_a_metered_appliance_gets_all_four_energy_entities(hass):
    """A metered appliance keeps every energy entity, including the disabled two (#280)."""
    from homeassistant.config_entries import ConfigEntryState

    from custom_components.dimplex.sensor import ENERGY_SENSORS

    status_payload, energy_payload = _row(t1=[(dt_util.now(), 0.5)])

    from custom_components.dimplex.capabilities import capabilities_for_row

    row = status_payload["appliances"][0]
    assert capabilities_for_row(row["appliance"], row["status"], row.get("product")).energy_meter is True

    registry = await _setup_row(hass, status_payload, energy_payload)

    for description in ENERGY_SENSORS:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"test_appliance-1_{description.key}")
        assert entity_id is not None, f"the metered appliance lost {description.key}"
        entry = registry.async_get(entity_id)
        assert entry is not None
        # Two are enabled by default; the T2 pair is opt-in and stays registered but
        # disabled, which is what makes this an assertion about all four.
        assert (entry.disabled_by is None) is description.entity_registry_enabled_default

    config_entry = hass.config_entries.async_get_entry("test")
    assert config_entry is not None and config_entry.state is ConfigEntryState.LOADED

    """The cumulative sensors are meters, so they must declare a state class (#227).

    4.1.0 removed it on the belief that ``mode="lifetime"`` was a rolling 30-day
    window. It is not: ``summarise_energy(mode="lifetime")`` sums every point it is
    handed, and the cloud returns the appliance's full available history — the
    library's own docstring warns callers to filter client-side, and a real
    installation's diagnostics span 12-17 months. Without a state class the Energy
    Dashboard cannot use them and Home Assistant raises a repair per sensor.
    """
    from custom_components.dimplex.sensor import ENERGY_SENSORS

    cumulative = [d for d in ENERGY_SENSORS if d.mode == "lifetime"]
    daily = [d for d in ENERGY_SENSORS if d.mode == "daily"]
    assert cumulative and daily, "expected both cumulative and daily energy descriptions"

    for description in cumulative:
        assert description.state_class == SensorStateClass.TOTAL_INCREASING, (
            f"{description.key} must declare TOTAL_INCREASING so it is a usable "
            "energy source and enters long-term statistics"
        )
    for description in daily:
        assert description.state_class == SensorStateClass.TOTAL, (
            f"{description.key} must stay TOTAL so its midnight last_reset is honoured"
        )


def _energy_sensor(mode: str):
    """Build an energy sensor over a stub coordinator, for unit-level checks."""
    from custom_components.dimplex.sensor import ENERGY_SENSORS, DimplexEnergySensor

    description = next(d for d in ENERGY_SENSORS if d.mode == mode)
    coordinator = SimpleNamespace(data={}, last_update_success_time=None, last_update_success=True)
    config_entry = SimpleNamespace(entry_id="test")
    row = {
        "appliance": SimpleNamespace(ApplianceId="app-1", FriendlyName="Heater", ApplianceModel="QM100RF"),
        "hub": SimpleNamespace(HubId="hub-1"),
        "zone": SimpleNamespace(ZoneName="Living Room", ZoneId="z1"),
    }
    sensor = DimplexEnergySensor(coordinator, config_entry, row, description)
    sensor.entity_id = f"sensor.heater_{description.key}"
    return sensor


async def test_a_truncated_history_never_lowers_the_cumulative_total():
    """A short cloud read must not look like a meter reset.

    Home Assistant's ``reset_detected()`` treats a fall of more than 10% as a new
    meter cycle and adds the whole state to the statistics sum again — the inflation
    behind #196. Holding the highest total seen means the short read is ignored and
    the meter only moves forward, which is what makes TOTAL_INCREASING safe here.
    """
    sensor = _energy_sensor("lifetime")

    def summary(total: float):
        return SimpleNamespace(total_kwh=total, point_count=3)

    with patch.object(sensor, "_summary", return_value=summary(100.0)):
        assert sensor.native_value == 100.0

    # A truncated response: the sum falls, and the reported value must not follow.
    with patch.object(sensor, "_summary", return_value=summary(5.0)):
        assert sensor.native_value == 100.0

    # A genuine increase is still reported.
    with patch.object(sensor, "_summary", return_value=summary(104.5)):
        assert sensor.native_value == 104.5


async def test_a_daily_total_is_not_clamped():
    """Daily totals are expected to fall to zero at midnight, so they must not clamp."""
    sensor = _energy_sensor("daily")

    def summary(total: float):
        return SimpleNamespace(total_kwh=total, point_count=3)

    with patch.object(sensor, "_summary", return_value=summary(4.0)):
        assert sensor.native_value == 4.0
    with patch.object(sensor, "_summary", return_value=summary(0.25)):
        assert sensor.native_value == 0.25


async def test_the_cumulative_peak_survives_a_restart():
    """The peak is restored, because Home Assistant compares against its recorder.

    It holds the last *recorded* value, not anything in our memory — so without
    restoring the peak, a dip on the first poll after a restart would still read as
    a meter reset and inflate the statistics.
    """
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    from custom_components.dimplex.sensor import DimplexEnergyRestoreData

    sensor = _energy_sensor("lifetime")
    restored = DimplexEnergyRestoreData(987.5, UnitOfEnergy.KILO_WATT_HOUR, 987.5)

    with (
        patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()),
        patch.object(sensor, "async_get_last_extra_data", new=AsyncMock(return_value=restored)),
    ):
        await sensor.async_added_to_hass()

    assert sensor._peak_total == 987.5


async def test_a_restart_with_no_saved_state_still_restores_the_peak():
    """A saved ``None`` state must not cost the peak (#281).

    The state is ``None`` whenever the series was empty at shutdown — the hub
    returned nothing, or the appliance had just been re-onboarded. Restoring from
    ``native_value`` skipped the peak in exactly that case, so the first truncated
    cloud total after the restart was accepted as the new peak and Home Assistant's
    statistics added it on top of the old total instead of seeing one meter.
    """
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    from custom_components.dimplex.sensor import DimplexEnergyRestoreData

    sensor = _energy_sensor("lifetime")
    # The state has no value, but the peak was persisted with it.
    restored = DimplexEnergyRestoreData(None, UnitOfEnergy.KILO_WATT_HOUR, 987.5)

    with (
        patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()),
        patch.object(sensor, "async_get_last_extra_data", new=AsyncMock(return_value=restored)),
    ):
        await sensor.async_added_to_hass()

    assert sensor._peak_total == 987.5

    # The truncated total the cloud returns on the first poll after that restart is
    # held at the restored peak: no drop, so no statistics reset.
    with patch.object(
        sensor,
        "_summary",
        return_value=SimpleNamespace(total_kwh=12.0, point_count=2, mode="lifetime", start=None, end=None),
    ):
        assert sensor.native_value == 987.5


async def test_the_persisted_payload_carries_the_peak():
    """The peak is written to restore data in its own field, whatever the state is."""
    sensor = _energy_sensor("lifetime")

    with patch.object(
        sensor,
        "_summary",
        return_value=SimpleNamespace(total_kwh=321.5, point_count=4, mode="lifetime", start=None, end=None),
    ):
        assert sensor.native_value == 321.5
        payload = sensor.extra_restore_state_data.as_dict()

    assert payload["peak_total"] == 321.5
    # Home Assistant's own sensor payload is preserved, so nothing that reads the
    # stored state loses it.
    assert payload["native_value"] == 321.5


async def test_a_payload_written_before_the_peak_had_its_own_field_still_restores():
    """Entries stored by an earlier version hold only the state, which was the peak.

    Restore data is not migrated: it is read once, on the first start after the
    upgrade, and the state written by the old code *was* the held peak.
    """
    from homeassistant.helpers.restore_state import RestoredExtraData
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    sensor = _energy_sensor("lifetime")
    legacy = RestoredExtraData({"native_value": 654.25, "native_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR})

    with (
        patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()),
        patch.object(sensor, "async_get_last_extra_data", new=AsyncMock(return_value=legacy)),
    ):
        await sensor.async_added_to_hass()

    assert sensor._peak_total == 654.25


async def test_unusable_restore_data_leaves_the_peak_unset():
    """Anything we did not write is ignored rather than trusted as a peak."""
    from homeassistant.helpers.restore_state import RestoredExtraData
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    sensor = _energy_sensor("lifetime")
    stranger = RestoredExtraData({"peak_total": "not a number", "native_value": None})

    with (
        patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()),
        patch.object(sensor, "async_get_last_extra_data", new=AsyncMock(return_value=stranger)),
    ):
        await sensor.async_added_to_hass()

    assert sensor._peak_total is None


async def test_a_suppressed_drop_publishes_the_raw_total():
    """The unheld total is exposed, so a suppression is inspectable (#234).

    The reported state is the held peak, so on its own it cannot answer "is the
    cloud still sending what we think it is?" — the one question that matters when a
    permanently reduced history would make the entity over-report forever.
    """
    sensor = _energy_sensor("lifetime")

    def summary(total: float):
        return SimpleNamespace(
            total_kwh=total,
            point_count=3,
            mode="lifetime",
            start=dt_util.parse_datetime("2025-01-01T00:00:00+00:00"),
            end=dt_util.parse_datetime("2026-01-01T00:00:00+00:00"),
        )

    with patch.object(sensor, "_summary", return_value=summary(100.0)):
        assert sensor.native_value == 100.0
        assert sensor.extra_state_attributes["raw_total"] == 100.0
        assert sensor.extra_state_attributes["peak_total"] == 100.0

    # The cloud trims the history: the state holds the peak, the attribute does not.
    with patch.object(sensor, "_summary", return_value=summary(5.0)):
        assert sensor.native_value == 100.0
        assert sensor.extra_state_attributes["raw_total"] == 5.0
        assert sensor.extra_state_attributes["peak_total"] == 100.0

    # Once the cloud catches back up, the attribute follows it.
    with patch.object(sensor, "_summary", return_value=summary(104.5)):
        assert sensor.native_value == 104.5
        assert sensor.extra_state_attributes["raw_total"] == 104.5


async def test_a_large_suppressed_drop_is_logged_at_warning(caplog):
    """A drop big enough to be a trimmed history must not be a debug line (#234).

    More than 10% is the band Home Assistant's ``reset_detected()`` acts on, which is
    why it is held in the first place — and it is also what a *permanent* reduction
    looks like. Logging it at ``debug`` meant the only evidence was invisible.
    """
    sensor = _energy_sensor("lifetime")

    def summary(total: float):
        return SimpleNamespace(
            total_kwh=total,
            point_count=3,
            mode="lifetime",
            start=None,
            end=None,
        )

    with patch.object(sensor, "_summary", return_value=summary(100.0)):
        assert sensor.native_value == 100.0

    with caplog.at_level(logging.DEBUG, logger="custom_components.dimplex.sensor"):
        # 95% down: the case the issue is about.
        with patch.object(sensor, "_summary", return_value=summary(5.0)):
            assert sensor.native_value == 100.0
        large = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("raw_total" in r.getMessage() for r in large), "a >10% suppressed drop must warn"

        caplog.clear()
        # 5% down: routine, and must stay quiet so the warning keeps its meaning.
        with patch.object(sensor, "_summary", return_value=summary(95.0)):
            assert sensor.native_value == 100.0
        assert not [r for r in caplog.records if r.levelno == logging.WARNING]
        assert [r for r in caplog.records if r.levelno == logging.DEBUG]


async def test_daily_totals_publish_no_hold_attributes():
    """Daily totals are not held, so they must not claim a peak or a raw total.

    A daily total legitimately falls to zero at midnight; exposing ``peak_total``
    there would imply a hold that does not exist.
    """
    sensor = _energy_sensor("daily")

    def summary(total: float):
        return SimpleNamespace(
            total_kwh=total,
            point_count=3,
            mode="daily",
            start=dt_util.parse_datetime("2026-01-01T00:00:00+00:00"),
            end=dt_util.parse_datetime("2026-01-01T23:59:59+00:00"),
        )

    with patch.object(sensor, "_summary", return_value=summary(4.0)):
        attributes = sensor.extra_state_attributes
    assert "raw_total" not in attributes
    assert "peak_total" not in attributes


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

    runtime = config_entry.runtime_data
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


async def test_the_lifetime_total_covers_all_history_not_a_request_window(hass):
    """The cumulative total sums every point, however far back it goes (#227).

    The request asks for 30 days (``ENERGY_REQUEST_DAYS``), but with
    ``IncludePreviousPeriod`` the cloud returns the appliance's full available history
    and ignores the start date — so this pins that the integration does not window the
    result client-side. Two reporters, the docs and this repository's own comments all
    read the old constant as "the sensors cover 30 days", which they never did.
    """
    now = dt_util.now()
    points = [
        # Far outside any 30-day request window...
        (now - timedelta(days=700), 12.0),
        (now - timedelta(days=400), 30.0),
        # ...and a recent one.
        (now - timedelta(days=2), 1.5),
    ]
    status_payload, energy_payload = _row(t1=points)

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch("custom_components.dimplex.DimplexApiClient.async_get_status_data", return_value=status_payload),
        patch("custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs", return_value=energy_payload),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = _state(hass, "energy")
    assert state is not None
    assert float(state.state) == 43.5  # 12 + 30 + 1.5, nothing dropped
    assert state.attributes["telemetry_points"] == 3
    assert state.attributes["window_start"] is not None
