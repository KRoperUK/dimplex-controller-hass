"""Test dimplex_controller config flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.api import CannotConnect, InvalidAuth
from custom_components.dimplex.const import (
    DOMAIN,
    PLATFORMS,
)

from .const import MOCK_CONFIG

pytestmark = pytest.mark.asyncio


# This fixture bypasses the actual setup of the integration
# since we only want to test the config flow. We test the
# actual functionality of the integration in other test modules.
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


# Here we simulate a successful config flow from the backend.
async def test_successful_config_flow(hass):
    """Test a successful config flow."""
    # Initialize a config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Check that the config flow shows the user form as the first step
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    # If a user enters an access token, it results in this validation call.
    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        return_value={
            "refresh_token": "refresh_token",
            "access_token": "access_token",
            "expires_at": 123,
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    # Check that the config flow is complete and a new entry is created with
    # the input data
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dimplex Hub"
    assert result["data"]["access_token"] == "access_token"
    assert result["data"]["refresh_token"] == "refresh_token"
    assert result["data"]["expires_at"] == 123
    assert result["result"]


# In this case, we want to simulate a failure during the config flow.
# We use the `error_on_get_data` mock instead of `bypass_get_data`
# (note the function parameters) to raise an Exception during
# validation of the input config.
async def test_failed_config_flow(hass, error_on_get_data):
    """Test a failed config flow due to credential validation failure."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect_config_flow(hass):
    """Test a failed config flow due to connectivity failure."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        side_effect=CannotConnect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


# Our config flow also has an options flow, so we must test it as well.
async def test_options_flow(hass):
    """Test an options flow."""
    # Create a new MockConfigEntry and add to HASS (we're bypassing config
    # flow entirely)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dimplex Hub",
        data=MOCK_CONFIG,
        entry_id="test",
    )
    entry.add_to_hass(hass)

    # Initialize an options flow
    await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)

    # Verify that the first options step is a user form
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    # Enter some fake data into the form
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            platform.value: platform.value != "sensor" for platform in PLATFORMS
        },
    )

    # Verify that the flow finishes
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Dimplex Hub"

    # Verify that the options were updated
    assert entry.options == {
        "binary_sensor": True,
        "sensor": False,
        "switch": True,
    }

async def test_reauth_flow(hass):
    """Test reauth flow updates existing entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dimplex Hub",
        data=MOCK_ENTRY_DATA,
        entry_id="test",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        return_value={
            "refresh_token": "new_refresh_token",
            "access_token": "new_access_token",
            "expires_at": 456,
        },
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["refresh_token"] == "new_refresh_token"
    assert entry.data["access_token"] == "new_access_token"
    assert entry.data["expires_at"] == 456


async def test_reauth_flow_invalid_auth(hass):
    """Test reauth flow handles invalid auth."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dimplex Hub",
        data=MOCK_ENTRY_DATA,
        entry_id="test",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    with patch(
        "custom_components.dimplex.config_flow.validate_auth_code",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_CONFIG
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

