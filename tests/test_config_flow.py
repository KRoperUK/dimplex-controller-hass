"""Test dimplex_controller config flow."""

import logging
from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.api import CannotConnect, InvalidAuth
from custom_components.dimplex.const import (
    DOMAIN,
    PLATFORMS,
)

from .const import MOCK_CONFIG, MOCK_CREDENTIALS, MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def bypass_setup_fixture():
    """Prevent setup."""
    with (
        patch(
            "custom_components.dimplex.async_setup",
            return_value=True,
        ),
        patch(
            "custom_components.dimplex.async_setup_entry",
            return_value=True,
        ),
    ):
        yield


# ── setup: auth_code path ──────────────────────────────────────


async def test_menu_step(hass):
    """Test the first-step menu shows the method selector."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    schema = result["data_schema"].schema
    assert "auth_method" in schema


async def test_credentials_path_success(hass):
    """Test successful config flow via email/password."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    # Step 1: choose credentials method
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )
    assert result["step_id"] == "credentials"

    # Step 2: submit credentials
    with patch(
        "custom_components.dimplex.config_flow.validate_credentials",
        return_value=(
            {
                "refresh_token": "rt",
                "access_token": "at",
                "expires_at": 123,
            },
            "acct-1",
        ),
    ) as mock_val:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    mock_val.assert_awaited_once_with(hass, "user@example.com", "secret")
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dimplex Hub"
    assert result["data"]["access_token"] == "at"
    assert result["data"]["refresh_token"] == "rt"


async def test_credentials_duplicate_account_aborts(hass):
    """A second entry for the same Dimplex account aborts as already_configured."""
    existing = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="existing", unique_id="acct-1")
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_credentials",
        return_value=(
            {"refresh_token": "rt", "access_token": "at", "expires_at": 123},
            "acct-1",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_auth_code_path_success(hass):
    """Test successful config flow via manual auth code."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    # Step 1: choose auth_code method
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "auth_code"},
    )
    assert result["step_id"] == "auth_code"

    # Step 2: submit auth code
    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        return_value=(
            {
                "refresh_token": "rt",
                "access_token": "at",
                "expires_at": 123,
            },
            "acct-1",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CONFIG,
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"]["access_token"] == "at"


async def test_credentials_invalid_auth(hass):
    """Test credentials flow handles invalid auth."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_credentials",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "credentials"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_auth_code_invalid(hass):
    """Test auth code flow handles invalid auth."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "auth_code"},
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CONFIG,
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "auth_code"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_auth_code_cannot_connect(hass):
    """Test auth code flow handles connectivity failure."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "auth_code"},
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CONFIG,
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# ── reauth ──────────────────────────────────────────────────────


async def test_reauth_menu(hass):
    """Test reauth shows method selector."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
    )

    assert result["step_id"] == "reauth"
    schema = result["data_schema"].schema
    assert "auth_method" in schema


async def test_reauth_credentials_success(hass):
    """Test reauth via credentials updates entry."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )
    assert result["step_id"] == "reauth_credentials"

    with patch(
        "custom_components.dimplex.config_flow.validate_credentials",
        return_value=(
            {
                "refresh_token": "new_rt",
                "access_token": "new_at",
                "expires_at": 456,
            },
            "acct-1",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert entry.data["access_token"] == "new_at"
    assert entry.data["refresh_token"] == "new_rt"
    assert entry.data["expires_at"] == 456


async def test_reauth_code_success(hass):
    """Test reauth via auth code updates entry."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "auth_code"},
    )
    assert result["step_id"] == "reauth_auth_code"

    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        return_value=(
            {
                "refresh_token": "new_rt",
                "access_token": "new_at",
                "expires_at": 456,
            },
            "acct-1",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CONFIG,
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_credentials_invalid(hass):
    """Test reauth handles invalid credentials."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_credentials",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_credentials"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_rejects_a_different_account(hass):
    """Reauth must not repoint an entry at another Dimplex account.

    Regression for dimplex-controller-hass#198: any working credentials were
    accepted and written to the existing entry, so every appliance id in it then
    belonged to a hub this entry is not set up for and all its entities died with
    no actionable error.
    """
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test", unique_id="acct-1")
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_credentials",
        return_value=(
            {"refresh_token": "other_rt", "access_token": "other_at", "expires_at": 456},
            "acct-2",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_account_mismatch"
    entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert entry.data["access_token"] == "access_token"
    assert entry.data["refresh_token"] == "refresh_token"


async def test_reauth_accepts_the_same_account(hass):
    """The identity check passes when the account matches the entry's unique id."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test", unique_id="acct-1")
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_credentials",
        return_value=(
            {"refresh_token": "new_rt", "access_token": "new_at", "expires_at": 456},
            "acct-1",
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    entry = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert entry.data["access_token"] == "new_at"


async def test_credentials_without_an_account_id_warns(hass, caplog):
    """An account id-less login still creates the entry, but says it is unkeyed.

    Setting the unique id only when the context carried an account id allowed a
    duplicate entry and double polling (#198). The API adapter now falls back to
    the hub id; if even that is missing there is nothing stable to key on, which
    must not pass silently.
    """
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )

    with (
        caplog.at_level(logging.WARNING, logger="custom_components.dimplex.config_flow"),
        patch(
            "custom_components.dimplex.config_flow.validate_credentials",
            return_value=(
                {"refresh_token": "rt", "access_token": "at", "expires_at": 123},
                None,
            ),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert "no unique id" in caplog.text


async def test_unexpected_credentials_error_is_logged(hass, caplog):
    """An unexpected failure is logged, not just reported as "unknown"."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_method": "credentials"},
    )

    with (
        caplog.at_level(logging.ERROR, logger="custom_components.dimplex.config_flow"),
        patch(
            "custom_components.dimplex.config_flow.validate_credentials",
            side_effect=RuntimeError("boom"),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CREDENTIALS,
        )

    assert result["errors"] == {"base": "unknown"}
    assert "Unexpected error validating Dimplex credentials" in caplog.text
    assert "RuntimeError: boom" in caplog.text


# ── options ─────────────────────────────────────────────────────


async def test_options_flow(hass):
    """Test an options flow."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_ENTRY_DATA,
        entry_id="test",
        options={},
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(
        config_entry.entry_id, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    user_input = {x.value: True for x in sorted(PLATFORMS)}
    user_input["status_interval"] = 30
    user_input["energy_interval"] = 1800
    user_input["boost_duration"] = 60
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert dict(config_entry.options) == user_input
