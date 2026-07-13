"""Home Assistant repairs for Dimplex Hub."""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir

from .const import DOCS_URL, DOMAIN

ISSUE_REAUTH = "reauth_required"
ISSUE_EMPTY_ENERGY = "empty_energy_season"
ISSUE_EMPTY_OVERVIEW = "empty_overview"


class ReauthRepairFlow(RepairsFlow):
    """Repair flow that starts config-entry reauth."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> FlowResult:
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(self._entry_id)
            if entry is not None:
                entry.async_start_reauth(self.hass)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="confirm")


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
) -> RepairsFlow:
    """Create flow for repair issues that need user confirmation."""
    if issue_id.startswith(f"{ISSUE_REAUTH}_"):
        entry_id = issue_id[len(f"{ISSUE_REAUTH}_") :]
        return ReauthRepairFlow(entry_id)
    return ConfirmRepairFlow()


def async_create_reauth_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Surface a reauthentication repair."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_REAUTH}_{entry_id}",
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_REAUTH,
        data={"entry_id": entry_id},
        learn_more_url=f"{DOCS_URL}/blob/main/docs/troubleshooting.md",
    )


def async_delete_reauth_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Clear reauth repair when auth succeeds."""
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_REAUTH}_{entry_id}")


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
