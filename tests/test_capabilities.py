"""Capability helper tests."""

from types import SimpleNamespace
from unittest.mock import patch

from custom_components.dimplex.capabilities import capabilities_for_row


def test_default_room_heater_presets():
    app = SimpleNamespace(ApplianceType="Quantum", ApplianceModel="QM100RF", FriendlyName="Hall")
    caps = capabilities_for_row(app)
    assert caps.climate is True
    assert "boost" in caps.climate_presets()


def test_hot_water_skips_climate():
    app = SimpleNamespace(ApplianceType="Hot Water Cylinder", ApplianceModel="X", FriendlyName="DHW")
    caps = capabilities_for_row(app)
    assert caps.climate is False


def test_capabilities_expose_the_cloud_temperature_range():
    """The app's mode carousels are 7-30 °C, with frost pinned at the 7 °C floor."""
    appliance = SimpleNamespace(
        ApplianceId="a1",
        ApplianceType="Quantum",
        ApplianceModel="QM100RF",
        FriendlyName="Hall",
    )
    caps = capabilities_for_row(appliance)
    assert caps.min_temp == 7.0
    assert caps.max_temp == 30.0
    assert caps.frost_temp == 7.0


def test_capability_temperatures_fall_back_when_library_values_are_unusable():
    """A library that reports no/zero limits must not produce a 0 °C minimum."""
    import custom_components.dimplex.capabilities as caps_mod

    broken = SimpleNamespace(min_temp=0, max_temp=None, frost_temp="nonsense", climate=True)
    with patch.object(caps_mod, "_lib_capabilities_for", lambda *a, **k: broken):
        caps = caps_mod.capabilities_for_row(SimpleNamespace())

    assert caps.min_temp == 7.0
    assert caps.max_temp == 30.0
    assert caps.frost_temp == 7.0
