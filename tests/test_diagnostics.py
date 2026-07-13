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
