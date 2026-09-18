"""Capability helper tests."""

from types import SimpleNamespace
from unittest.mock import patch

from custom_components.dimplex.capabilities import (
    LocalCapabilities,
    capabilities_for_row,
    product_for_appliance,
    product_lookup,
)


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


def test_every_library_flag_survives_the_passthrough():
    """Regression for #199: only 10 of the library's 22 fields used to be copied.

    The dropped ones were exactly the flags that gate controls the integration did
    not implement — ``setpoint_write``, ``advance``, ``frost``, ``hot_water`` and
    friends — so an appliance the library marked incapable still got the control.
    """
    import custom_components.dimplex.capabilities as caps_mod

    every_flag = {field: False for field in caps_mod._BOOL_FIELDS}  # noqa: SLF001
    library_caps = SimpleNamespace(
        **every_flag,
        min_temp=5.0,
        max_temp=35.0,
        frost_temp=5.0,
        default_boost_minutes=45,
        boost_durations=(15, 45),
    )

    with patch.object(caps_mod, "_lib_capabilities_for", lambda *a, **k: library_caps):
        caps = caps_mod.capabilities_for_row(SimpleNamespace())

    for field in caps_mod._BOOL_FIELDS:  # noqa: SLF001
        assert getattr(caps, field) is False, field
    assert caps.min_temp == 5.0
    assert caps.max_temp == 35.0
    assert caps.frost_temp == 5.0
    assert caps.default_boost_minutes == 45
    assert caps.boost_durations == (15, 45)


def test_the_product_row_is_forwarded_to_the_library():
    """Without it the derived flags (storage, hot_water, heat_pump) cannot be derived."""
    import custom_components.dimplex.capabilities as caps_mod

    seen: dict[str, object] = {}
    product = SimpleNamespace(ProductModelName="ASHW 6kW")

    def _record(appliance, *, status=None, product=None):  # noqa: A002
        seen["product"] = product
        return LocalCapabilities()

    with patch.object(caps_mod, "_lib_capabilities_for", _record):
        caps_mod.capabilities_for_row(SimpleNamespace(), None, product)

    assert seen["product"] is product


def test_a_hot_water_product_type_is_read_from_the_catalogue():
    """The catalogue is what makes a cylinder distinguishable from a panel heater."""
    from dimplex_controller import ProductModel

    product = ProductModel(ProductTypeName="Hot Water Cylinder", ProductModelName="HWC 200")
    caps = capabilities_for_row(None, None, product)

    assert caps.hot_water is True
    assert caps.climate is False
    # A cylinder has no "next comfort period" to advance to.
    assert caps.advance is False
    assert caps.hygiene is True


def test_product_lookup_prefers_a_model_match_over_a_type_match():
    """A specific catalogue row must not be shadowed by its shared family entry."""
    family = SimpleNamespace(ProductModelName=None, ProductTypeName="Quantum")
    exact = SimpleNamespace(ProductModelName="QM100RF", ProductTypeName="Quantum")
    lookup = product_lookup([family, exact])

    assert product_for_appliance(lookup, SimpleNamespace(ApplianceModel="QM100RF")) is exact
    assert product_for_appliance(lookup, SimpleNamespace(ApplianceModel=None, ApplianceType="Quantum")) is family


def test_product_lookup_handles_missing_names_and_no_catalogue():
    lookup = product_lookup([SimpleNamespace(ProductModelName=None, ProductTypeName=None), SimpleNamespace()])

    assert lookup == {}
    assert product_for_appliance(lookup, SimpleNamespace(ApplianceModel="QM100RF")) is None
    assert product_for_appliance(None, SimpleNamespace(ApplianceModel="QM100RF")) is None
    assert product_for_appliance({"x": 1}, None) is None


def test_as_dict_covers_every_flag():
    """Diagnostics publish this; a dropped field would be invisible there too."""
    import custom_components.dimplex.capabilities as caps_mod

    payload = LocalCapabilities().as_dict()

    for field in caps_mod._BOOL_FIELDS:  # noqa: SLF001
        assert field in payload
    assert payload["climate_presets"] == ["comfort", "boost", "away", "eco"]
