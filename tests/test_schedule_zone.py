"""Schedule sensor and zone device helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntry

from custom_components.dimplex.sensor import DimplexScheduleSensor, DimplexZoneSensor


def test_schedule_sensor_native_value_and_periods():
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "e1"
    hub = SimpleNamespace(HubId="h1")
    zone = SimpleNamespace(ZoneId="z1", ZoneName="Living")
    appliance = SimpleNamespace(ApplianceId="a1", FriendlyName="Heater", ApplianceModel="X", ApplianceType="Q")
    period = SimpleNamespace(DayOfWeek=1, StartTime="06:00:00", EndTime="09:00:00", Temperature=20.0)
    schedule = SimpleNamespace(TimerMode=1, TimerPeriods=[period])
    coord = MagicMock()
    coord.data = {
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": None}],
        "schedules": {"a1": schedule},
    }
    coord.last_update_success = True
    sensor = DimplexScheduleSensor(coord, entry, {"hub": hub, "zone": zone, "appliance": appliance, "status": None})
    assert sensor.native_value == "manual"
    attrs = sensor.extra_state_attributes
    assert attrs["period_count"] == 1
    assert attrs["periods"][0]["temperature"] == 20.0


def _schedule_sensor(status_modes, status_two, timer_mode=0):
    """Build a schedule sensor over the given overview + schedule state."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "e1"
    hub = SimpleNamespace(HubId="h1")
    zone = SimpleNamespace(ZoneId="z1", ZoneName="Living")
    appliance = SimpleNamespace(ApplianceId="a1", FriendlyName="Heater", ApplianceModel="X", ApplianceType="Q")
    status = SimpleNamespace(ApplianceModes=status_modes, StatusTwo=status_two)
    schedule = SimpleNamespace(TimerMode=timer_mode, TimerPeriods=[])
    row = {"hub": hub, "zone": zone, "appliance": appliance, "status": status}
    coord = MagicMock()
    coord.data = {"appliances": [row], "schedules": {"a1": schedule}}
    coord.last_update_success = True
    return DimplexScheduleSensor(coord, entry, row)


def test_schedule_sensor_reports_status_two_profile():
    """The active profile comes from the overview, not the timer details (#312).

    A Quantum with Out All Day applied reports TIMER bit + StatusTwo=2 while the
    schedule endpoint still returns TimerMode=0; the sensor must follow the app
    and report out_all_day, not user_timer.
    """
    sensor = _schedule_sensor(status_modes=1, status_two=2, timer_mode=0)
    assert sensor.native_value == "out_all_day"
    assert sensor.extra_state_attributes["status_two"] == 2


def test_schedule_sensor_home_all_day():
    sensor = _schedule_sensor(status_modes=1, status_two=1, timer_mode=0)
    assert sensor.native_value == "home_all_day"


def test_schedule_sensor_user_timer_when_status_two_zero():
    sensor = _schedule_sensor(status_modes=1, status_two=0, timer_mode=0)
    assert sensor.native_value == "user_timer"


def test_schedule_sensor_falls_back_to_timer_mode_without_timer_bit():
    """Without the TIMER bit engaged there is no active profile to name."""
    sensor = _schedule_sensor(status_modes=128, status_two=2, timer_mode=1)
    assert sensor.native_value == "manual"


def test_zone_sensor_goes_unavailable_when_the_zone_disappears():
    """A zone the cloud stops reporting must not keep a stale anchor alive.

    ``available`` used to consult only ``last_update_success``, so a zone that was
    removed or renamed in the Dimplex app left its anchor reporting forever (#198).
    """
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "e1"
    hub = SimpleNamespace(HubId="h1")
    zone = SimpleNamespace(ZoneId="z1", ZoneName="Living", ZoneType="Heating")
    appliance = SimpleNamespace(ApplianceId="a1")
    row = {"hub": hub, "zone": zone, "appliance": appliance, "status": None}

    coord = MagicMock()
    coord.last_update_success = True
    coord.data = {"appliances": [row]}
    sensor = DimplexZoneSensor(coord, entry, {"hub": hub, "zone": zone, "appliance": appliance})
    assert sensor.available is True

    # The zone is gone from the snapshot — removed or renamed in the app.
    coord.data = {"appliances": []}
    assert sensor.available is False

    # Back, but the coordinator is failing: still unavailable.
    coord.data = {"appliances": [row]}
    coord.last_update_success = False
    assert sensor.available is False


def test_zone_device_identifiers():
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "e1"
    hub = SimpleNamespace(HubId="h1")
    zone = SimpleNamespace(ZoneId="z1", ZoneName="Living", ZoneType="Heating")
    appliance = SimpleNamespace(ApplianceId="a1")
    coord = MagicMock()
    coord.last_update_success = True
    zone_sensor = DimplexZoneSensor(coord, entry, {"hub": hub, "zone": zone, "appliance": appliance})
    info = zone_sensor.device_info
    assert ("dimplex", "zone_z1") in info["identifiers"]
    # The parent link is now a registry via_device_id resolved when the entity is
    # attached to hass; offline (no registry) it is simply omitted. Linkage is
    # verified end-to-end in tests/test_entities.py.
    assert "via_device" not in info
    assert info.get("via_device_id") is None
    assert zone_sensor.native_value == "Living"
