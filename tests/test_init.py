"""Test dimplex_controller setup process."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex import (
    DimplexRuntimeData,
    _persist_tokens,
    async_unload_entry,
)
from custom_components.dimplex.const import (
    DOMAIN,
)

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


async def test_setup_unload_and_reload_entry(hass, bypass_get_data):
    """Test entry setup and unload."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
    assert isinstance(hass.data[DOMAIN][config_entry.entry_id], DimplexRuntimeData)

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]
    assert isinstance(hass.data[DOMAIN][config_entry.entry_id], DimplexRuntimeData)

    assert await async_unload_entry(hass, config_entry)
    assert config_entry.entry_id not in hass.data[DOMAIN]


async def test_setup_entry_exception(hass, error_on_get_data):
    """Test setup fails when status coordinator cannot refresh."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_invalid_auth(hass, invalid_auth_on_init):
    """Test setup raises ConfigEntryAuthFailed so HA auto-starts reauth.

    See dimplex-controller-hass#114: the integration no longer creates a
    custom repair issue for reauthentication. Instead, ``async_setup_entry``
    raises ``ConfigEntryAuthFailed`` from the HA core exceptions module,
    which causes Home Assistant to mark the entry as ``SETUP_ERROR`` and
    surface the built-in reauth flow automatically.
    """
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    # HA core catches ConfigEntryAuthFailed and marks the entry as
    # SETUP_ERROR with a reauth flow attached; the exception itself does
    # not propagate to the caller of async_setup.
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_status_coordinator_raises_auth_failed_on_invalid_auth(hass, bypass_get_data):
    """Status coordinator surfaces reauth via ConfigEntryAuthFailed.

    Regression for dimplex-controller-hass#114. When the underlying API
    raises ``InvalidAuth`` during a status refresh, the coordinator must
    raise ``ConfigEntryAuthFailed`` so Home Assistant attaches the
    reauth flow to this config entry, not the bespoke
    ``async_create_reauth_issue`` + ``async_start_reauth`` pair.
    """
    from unittest.mock import patch

    from homeassistant.exceptions import ConfigEntryAuthFailed

    from custom_components.dimplex import DimplexStatusCoordinator
    from custom_components.dimplex.api import InvalidAuth

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)

    runtime = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: DimplexStatusCoordinator = runtime.status

    with (
        patch.object(coordinator.api, "async_get_status_data", side_effect=InvalidAuth),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        # _async_update_data must let ConfigEntryAuthFailed propagate so
        # the DataUpdateCoordinator machinery can attach the reauth flow.
        await coordinator._async_update_data()  # noqa: SLF001

    assert await async_unload_entry(hass, config_entry)


async def test_token_expiry_drift_is_persisted(hass):
    """Expiry derived from the access token's JWT is written back to the entry.

    Regression for dimplex-controller-hass#198: the change check compared only
    the tokens, so an entry stored with ``expires_at: 0`` had its expiry
    re-derived from the JWT on every restart and never persisted.
    """
    from unittest.mock import MagicMock

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_ENTRY_DATA, "expires_at": 0},
        entry_id="test",
    )
    config_entry.add_to_hass(hass)

    client = MagicMock()
    client.token_data = {
        "refresh_token": "refresh_token",
        "access_token": "access_token",
        "expires_at": 1234567890,
    }

    _persist_tokens(hass, config_entry, client)

    entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert entry.data["expires_at"] == 1234567890
    # The tokens themselves are unchanged, so nothing else was disturbed.
    assert entry.data["refresh_token"] == "refresh_token"
