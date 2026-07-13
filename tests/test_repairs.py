"""Tests for Dimplex repair issues (non-auth repairs only)."""

from homeassistant.core import HomeAssistant

from custom_components.dimplex.repairs import (
    async_update_empty_energy_issue,
    async_update_empty_overview_issue,
)


def test_update_empty_energy_issue_create(hass: HomeAssistant) -> None:
    """Empty-energy repair is created when marked empty=True."""
    async_update_empty_energy_issue(hass, "test_entry_id", empty=True)


def test_update_empty_energy_issue_clear(hass: HomeAssistant) -> None:
    """Empty-energy repair is cleared when marked empty=False."""
    async_update_empty_energy_issue(hass, "test_entry_id", empty=False)


def test_update_empty_overview_issue_create(hass: HomeAssistant) -> None:
    """Empty-overview repair is created when marked empty=True."""
    async_update_empty_overview_issue(hass, "test_entry_id", empty=True)


def test_update_empty_overview_issue_clear(hass: HomeAssistant) -> None:
    """Empty-overview repair is cleared when marked empty=False."""
    async_update_empty_overview_issue(hass, "test_entry_id", empty=False)
