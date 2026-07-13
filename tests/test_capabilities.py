"""Capability helper tests."""

from types import SimpleNamespace

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
