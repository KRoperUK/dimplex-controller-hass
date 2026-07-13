"""Tests for config entry diagnostics (redaction)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import (
    CONF_ACCESS_TOKEN,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.dimplex.diagnostics import async_get_config_entry_diagnostics

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


async def test_diagnostics_with_all_appliances_offline(hass: HomeAssistant) -> None:
    """Diagnostics still produce a valid payload when every appliance is offline.

    Regression for dimplex-controller-hass#119. On dell-serve, three Quantum
    QM100RF radiators have been turned off at the wall since February; the
    status coordinator returns rows with ``status=None``. The diagnostics
    payload must still be produced (no exception) and every appliance id
    must be present, hashed/serialised, with ``has_status=False``.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_ENTRY_DATA,
        options={"status_interval": 30, "energy_interval": 1800},
        entry_id="diag-offline",
    )
    entry.add_to_hass(hass)

    hub = SimpleNamespace(
        HubId="hub-1",
        FriendlyName="My Hub",
        Name="My Hub",
        ConnectionState=1,
        FirmwareVersion="1.0",
        HubType="Gateway",
        PrimaryUserEmail="owner@example.com",
        SecurityCode="SECRET",
    )
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="app-1",
        FriendlyName="Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
        FirmwareVersion="6",
        automatic_provisioning=None,
    )
    status_coord = MagicMock()
    status_coord.data = {
        "hubs": [hub],
        "appliances": [
            {"hub": hub, "zone": zone, "appliance": appliance, "status": None},
        ],
    }
    status_coord.last_update_success = True
    status_coord.last_exception = None
    status_coord.update_interval = "0:00:30"

    energy_coord = MagicMock()
    energy_coord.data = {"energy": {}}  # no series at all
    energy_coord.last_update_success = True
    energy_coord.last_exception = None
    energy_coord.update_interval = "0:30:00"

    runtime = SimpleNamespace(status=status_coord, energy=energy_coord)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    with patch("custom_components.dimplex.diagnostics.version", return_value="0.9.0"):
        data = await async_get_config_entry_diagnostics(hass, entry)

    assert data["appliances"][0]["has_status"] is False
    assert data["appliances"][0]["status"] is None
    assert data["appliances"][0]["appliance_id"] == "app-1"
    # No series means energy summary is empty for this hub, not an error.
    assert data["energy_summary"] == {}


async def test_model_snapshot_fallback_when_dump_raises(hass: HomeAssistant) -> None:
    """``_model_snapshot`` falls back to attribute walk when ``model_dump`` raises.

    Regression for dimplex-controller-hass#119. Some appliance models (notably
    in older firmware or stub test doubles) raise from ``model_dump``. The
    diagnostics path must still produce a serialisable dict instead of
    crashing the diagnostics endpoint.
    """
    from custom_components.dimplex.diagnostics import _model_snapshot

    class Exploding:
        def model_dump(self, mode=None):  # type: ignore[override]
            raise RuntimeError("pydantic exploded")

        # Only primitive attributes — these should appear in the fallback.
        ok_field = "value-1"
        another_field = 42

    snap = _model_snapshot(Exploding())
    assert snap is not None
    assert snap.get("ok_field") == "value-1"
    assert snap.get("another_field") == 42
    assert "model_dump" not in snap  # callable excluded by the dir() walk


async def test_model_snapshot_returns_none_for_none_input() -> None:
    """``_model_snapshot(None)`` is ``None`` (downstream handles nullables)."""
    from custom_components.dimplex.diagnostics import _model_snapshot

    assert _model_snapshot(None) is None


async def test_hash_identifier_handles_empty_and_none() -> None:
    """``_hash_identifier`` returns ``None`` for empty/None input."""
    from custom_components.dimplex.diagnostics import _hash_identifier

    assert _hash_identifier(None) is None
    assert _hash_identifier("") is None
    h = _hash_identifier("user@example.com")
    assert h is not None
    assert len(h) == 12
    # Stable: hashing the same value always yields the same digest.
    assert h == _hash_identifier("user@example.com")


async def test_energy_meta_handles_empty_hub_and_missing_fields() -> None:
    """``_energy_meta`` gracefully handles empty/malformed series structures."""
    from custom_components.dimplex.diagnostics import _energy_meta

    # Empty energy data — must not raise.
    assert _energy_meta({}) == {}
    assert _energy_meta({"energy": {}}) == {}
    # Hub with no registers (None treated as empty dict).
    assert _energy_meta({"energy": {"hub-1": None}}) == {"hub-1": {}}
    # Hub with registers but no appliances.
    assert _energy_meta({"energy": {"hub-1": {"t1": None}}}) == {"hub-1": {"t1": {}}}
    # Missing timestamps in points — point_count still recorded, window is null.
    meta = _energy_meta({"energy": {"hub-1": {"t1": {"app-1": [(None, 1.0), (None, 2.0)]}}}})
    assert meta["hub-1"]["t1"]["app-1"]["point_count"] == 2
    assert meta["hub-1"]["t1"]["app-1"]["window_start"] is None
    assert meta["hub-1"]["t1"]["app-1"]["window_end"] is None


async def test_diagnostics_with_no_runtime(hass: HomeAssistant) -> None:
    """Diagnostics still produce a valid payload when the runtime is missing.

    Edge case: the integration is configured but the entry has been
    removed from ``hass.data`` (e.g. mid-unload). The function must not
    raise; it should return a payload with empty coordinators and
    appliance sections.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_ENTRY_DATA,
        options={},
        entry_id="diag-no-runtime",
    )
    entry.add_to_hass(hass)
    # Intentionally do NOT add a runtime to hass.data.

    with patch("custom_components.dimplex.diagnostics.version", return_value="0.9.0"):
        data = await async_get_config_entry_diagnostics(hass, entry)

    assert data["hubs"] == []
    assert data["appliances"] == []
    assert data["energy_summary"] == {}
    assert data["coordinators"]["status"]["last_update_success"] is None
    assert data["coordinators"]["energy"]["last_update_success"] is None


async def test_diagnostics_redacts_tokens_and_summarises_energy(hass: HomeAssistant) -> None:
    """Diagnostics must never include tokens and only energy metadata."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **MOCK_ENTRY_DATA,
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "super-secret",
        },
        options={"status_interval": 30, "energy_interval": 1800},
        entry_id="diag-entry",
    )
    entry.add_to_hass(hass)

    hub = SimpleNamespace(
        HubId="hub-1",
        FriendlyName="My Hub",
        Name="My Hub",
        ConnectionState=1,
        FirmwareVersion="1.0",
        HubType="Gateway",
        PrimaryUserEmail="owner@example.com",
        SecurityCode="SECRET",
    )
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="app-1",
        FriendlyName="Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
        FirmwareVersion="6",
        automatic_provisioning=SimpleNamespace(rated_power=2.0, charge_capacity=10.0),
    )
    status = SimpleNamespace(
        RoomTemperature=21.0,
        ActiveSetPointTemperature=20.0,
        ComfortStatus=True,
    )
    status_coord = MagicMock()
    status_coord.data = {
        "hubs": [hub],
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}],
    }
    status_coord.last_update_success = True
    status_coord.last_exception = None
    status_coord.update_interval = "0:00:30"

    energy_coord = MagicMock()
    energy_coord.data = {
        "energy": {
            "hub-1": {
                "t1": {"app-1": [(None, 1.0), (None, 2.0)]},
                "t2": {},
            }
        }
    }
    energy_coord.last_update_success = True
    energy_coord.last_exception = None
    energy_coord.update_interval = "0:30:00"

    runtime = SimpleNamespace(status=status_coord, energy=energy_coord)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    with patch("custom_components.dimplex.diagnostics.version", return_value="0.9.0"):
        data = await async_get_config_entry_diagnostics(hass, entry)

    blob = str(data)
    assert data["entry"]["data"].get(CONF_REFRESH_TOKEN) != MOCK_ENTRY_DATA[CONF_REFRESH_TOKEN]
    assert data["entry"]["data"].get(CONF_ACCESS_TOKEN) != MOCK_ENTRY_DATA[CONF_ACCESS_TOKEN]
    assert data["entry"]["data"].get(CONF_PASSWORD) != "super-secret"
    assert "super-secret" not in blob
    assert "owner@example.com" not in blob
    assert "SECRET" not in blob  # hub security code
    assert data["versions"]["dimplex_controller"] == "0.9.0"
    assert data["hubs"][0]["hub_id"] == "hub-1"
    assert data["hubs"][0]["primary_user_email_hash"] is not None
    assert data["appliances"][0]["appliance_id"] == "app-1"
    assert data["energy_summary"]["hub-1"]["t1"]["app-1"]["point_count"] == 2
    assert "energy_summary" in data
