"""Adds config flow for dimplex_controller."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import CannotConnect
from .api import DimplexApiClient
from .api import InvalidAuth
from .const import CONF_ACCESS_TOKEN
from .const import CONF_EXPIRES_AT
from .const import CONF_PASSWORD
from .const import CONF_REFRESH_TOKEN
from .const import CONF_USERNAME
from .const import DOMAIN
from .const import PLATFORMS


async def validate_input(hass, data):
    """Validate user input allows us to connect and authenticate."""
    session = async_create_clientsession(hass)
    client = DimplexApiClient(
        session=session,
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
    )
    token_data = await client.async_validate_connection()
    return {
        "title": data[CONF_USERNAME],
        "token_data": token_data,
    }


class DimplexFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for dimplex."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        # Uncomment the next 2 lines if only a single instance of the integration is allowed:
        # if self._async_current_entries():
        #     return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidAuth:
                self._errors["base"] = "invalid_auth"
            except CannotConnect:
                self._errors["base"] = "cannot_connect"
            except Exception:
                self._errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_REFRESH_TOKEN: info["token_data"].get(CONF_REFRESH_TOKEN),
                        CONF_ACCESS_TOKEN: info["token_data"].get(CONF_ACCESS_TOKEN),
                        CONF_EXPIRES_AT: info["token_data"].get(CONF_EXPIRES_AT, 0),
                    },
                )

            return await self._show_config_form(user_input)

        return await self._show_config_form(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DimplexOptionsFlowHandler(config_entry)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit location data."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str}
            ),
            errors=self._errors,
        )


class DimplexOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options handler for dimplex."""

    def __init__(self, config_entry):
        """Initialize HACS options flow."""
        self._config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        x.value,
                        default=self.options.get(x.value, True),
                    ): bool
                    for x in sorted(PLATFORMS)
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(
            title=self._config_entry.data.get(CONF_USERNAME), data=self.options
        )
