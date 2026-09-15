"""Test dimplex_controller setup process."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex import (
    DimplexRuntimeData,
    async_unload_entry,
)
from custom_components.dimplex.const import (
    DOMAIN,
)

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


async def test_setup_unload_and_reload_entry(hass, bypass_get_data):
    """Test entry setup and unload.

    Runtime lives on ``entry.runtime_data``; there is no ``hass.data`` mirror to
    keep in step with it (#198).
    """
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    assert isinstance(config_entry.runtime_data, DimplexRuntimeData)
    assert DOMAIN not in hass.data

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert isinstance(config_entry.runtime_data, DimplexRuntimeData)

    # Unload through Home Assistant so its own cleanup runs too — it is what
    # deletes runtime_data once async_unload_entry has reported success.
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert getattr(config_entry, "runtime_data", None) is None


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


async def test_remove_config_entry_device_blocks_only_present_devices(hass):
    """A device the snapshot no longer reports can be deleted; a present one cannot.

    Without ``async_remove_config_entry_device`` a removed appliance left a device
    in the registry the user could not delete, and a newly added one needed a
    reload to appear. The manifest declares quality scale ``silver``, whose
    ``stale-devices`` rule requires this hook (#198).
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from homeassistant.helpers import device_registry as dr

    from custom_components.dimplex import async_remove_config_entry_device

    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneId="z-1", ZoneName="Living", ZoneType="Heating")
    appliance = SimpleNamespace(
        ApplianceId="app-1",
        FriendlyName="Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
        FirmwareVersion="6",
        SeriesIdentifier="G12",
    )
    row = {"hub": hub, "zone": zone, "appliance": appliance, "status": None}
    payload = {"appliances": [row], "hubs": [hub]}

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_schedule",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        registry = dr.async_get(hass)
        present = registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, "app-1")},
        )
        departed = registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, "app-gone")},
        )
        zone_device = registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, "zone_z-1")},
        )

        assert await async_remove_config_entry_device(hass, config_entry, present) is False
        assert await async_remove_config_entry_device(hass, config_entry, zone_device) is False
        assert await async_remove_config_entry_device(hass, config_entry, departed) is True


async def test_remove_config_entry_device_when_not_loaded(hass):
    """The hook stays permissive if the entry has no runtime attached.

    Home Assistant deletes ``runtime_data`` on unload, so the hook cannot assume
    it is there — and refusing would make an already-orphaned device undeletable.
    """
    from homeassistant.helpers import device_registry as dr

    from custom_components.dimplex import async_remove_config_entry_device

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "app-1")},
    )

    assert await async_remove_config_entry_device(hass, config_entry, device) is True


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

    runtime = config_entry.runtime_data
    coordinator: DimplexStatusCoordinator = runtime.status

    with (
        patch.object(coordinator.api, "async_get_status_data", side_effect=InvalidAuth),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        # _async_update_data must let ConfigEntryAuthFailed propagate so
        # the DataUpdateCoordinator machinery can attach the reauth flow.
        await coordinator._async_update_data()  # noqa: SLF001

    assert await async_unload_entry(hass, config_entry)
