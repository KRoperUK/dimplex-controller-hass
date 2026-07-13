"""Unit tests for dimplex entity icons (state-aware)."""

from types import SimpleNamespace

import pytest

from custom_components.dimplex.binary_sensor import DimplexComfortBinarySensor
from custom_components.dimplex.switch import DimplexEcoStartSwitch


def _appliance_row(eco_start: bool, comfort: bool):
    """Build a coordinator/config_entry/row trio with the given state."""
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    status = SimpleNamespace(EcoStartEnabled=eco_start, ComfortStatus=comfort, RoomTemperature=21.5)
    row = {"hub": hub, "zone": zone, "appliance": appliance, "status": status}
    coordinator = SimpleNamespace(data={"appliances": [row]})
    config_entry = SimpleNamespace(entry_id="test")
    return coordinator, config_entry, row


@pytest.mark.parametrize(
    ("eco_start", "expected_icon"),
    [(True, "mdi:leaf"), (False, "mdi:leaf-off")],
)
def test_ecostart_switch_icon(eco_start, expected_icon):
    """The EcoStart switch icon reflects its on/off state."""
    coordinator, config_entry, row = _appliance_row(eco_start=eco_start, comfort=False)
    switch = DimplexEcoStartSwitch(coordinator, config_entry, row, api=SimpleNamespace())
    assert switch.is_on is eco_start
    assert switch.icon == expected_icon


@pytest.mark.parametrize(
    ("comfort", "expected_icon"),
    [(True, "mdi:sofa"), (False, "mdi:sofa-outline")],
)
def test_comfort_binary_sensor_icon(comfort, expected_icon):
    """The Comfort binary sensor icon reflects its on/off state."""
    coordinator, config_entry, row = _appliance_row(eco_start=False, comfort=comfort)
    sensor = DimplexComfortBinarySensor(coordinator, config_entry, row)
    assert sensor.is_on is comfort
    assert sensor.icon == expected_icon
