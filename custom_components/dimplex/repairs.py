"""Home Assistant repairs for Dimplex Hub."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOCS_URL, DOMAIN

ISSUE_EMPTY_ENERGY = "empty_energy_season"
ISSUE_EMPTY_OVERVIEW = "empty_overview"


def async_update_empty_energy_issue(
    hass: HomeAssistant,
    entry_id: str,
    *,
    empty: bool,
) -> None:
    """Create or clear seasonal empty-energy repair."""
    issue_id = f"{ISSUE_EMPTY_ENERGY}_{entry_id}"
    if empty:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_EMPTY_ENERGY,
            learn_more_url=f"{DOCS_URL}/blob/main/docs/entities.md",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def async_update_empty_overview_issue(
    hass: HomeAssistant,
    entry_id: str,
    *,
    empty: bool,
) -> None:
    """Create or clear empty overview repair."""
    issue_id = f"{ISSUE_EMPTY_OVERVIEW}_{entry_id}"
    if empty:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_EMPTY_OVERVIEW,
            learn_more_url=f"{DOCS_URL}/blob/main/docs/troubleshooting.md",
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
