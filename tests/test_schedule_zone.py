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
    assert info["via_device"] == ("dimplex", "h1")
    assert zone_sensor.native_value == "Living"
