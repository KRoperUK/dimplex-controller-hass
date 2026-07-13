"""Tests for Dimplex repair issues."""

from homeassistant.components.repairs import ConfirmRepairFlow

from custom_components.dimplex.repairs import (
    ISSUE_REAUTH,
    ReauthRepairFlow,
    async_create_fix_flow,
    async_create_reauth_issue,
    async_update_empty_energy_issue,
    async_update_empty_overview_issue,
)


def test_create_reauth_issue(hass):
    async_create_reauth_issue(hass, "test_entry_id")


def test_update_empty_energy_issue_create(hass):
    async_update_empty_energy_issue(hass, "test_entry_id", empty=True)


def test_update_empty_overview_issue_create(hass):
    async_update_empty_overview_issue(hass, "test_entry_id", empty=True)


async def test_create_fix_flow_reauth(hass):
    flow = await async_create_fix_flow(hass, f"{ISSUE_REAUTH}_test")
    assert isinstance(flow, ReauthRepairFlow)


async def test_create_fix_flow_other(hass):
    flow = await async_create_fix_flow(hass, "some_other_issue")
    assert isinstance(flow, ConfirmRepairFlow)


async def test_reauth_repair_flow_init(hass):
    flow = ReauthRepairFlow("entry1")
    flow.hass = hass
    result = await flow.async_step_init()
    assert result is not None


async def test_reauth_repair_flow_confirm(hass):
    flow = ReauthRepairFlow("entry1")
    flow.hass = hass
    result = await flow.async_step_confirm({"confirm": True})
    assert result is not None
