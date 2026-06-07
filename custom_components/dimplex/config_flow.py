"""Adds config flow for dimplex_controller."""

from __future__ import annotations

from urllib.parse import parse_qs
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import CannotConnect
from .api import DimplexApiClient
from .api import InvalidAuth
from .const import CONF_ACCESS_TOKEN
from .const import CONF_AUTH_CODE
from .const import CONF_EXPIRES_AT
from .const import CONF_PASSWORD
from .const import CONF_REFRESH_TOKEN
from .const import CONF_USERNAME
from .const import DOMAIN
from .const import NAME
from .const import PLATFORMS


def _extract_auth_code(raw_input: str) -> str:
    """Extract auth code from a full redirect URL or raw code."""
    if "code=" in raw_input:
        try:
            parsed = urlparse(raw_input)
            query = parse_qs(parsed.query)
            return query.get("code", [""])[0]
        except ValueError:
            return ""

    return raw_input.strip()


async def validate_auth_code(hass, auth_input):
    """Exchange auth code and validate user session."""
    code = _extract_auth_code(auth_input)
    if not code:
        raise InvalidAuth

    session = async_create_clientsession(hass)
    client = DimplexApiClient(session=session)
    return await client.async_exchange_code(code)


async def validate_credentials(hass, username, password):
    """Validate username/password login and return token details."""
    session = async_create_clientsession(hass)
    client = DimplexApiClient(session, None, None, 0, username, password)
    return await client.async_validate_connection()


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
                auth_code = user_input.get(CONF_AUTH_CODE, "").strip()
                username = user_input.get(CONF_USERNAME, "").strip()
                password = user_input.get(CONF_PASSWORD, "")

                if auth_code:
                    token_data = await validate_auth_code(self.hass, auth_code)
                elif username and password:
                    token_data = await validate_credentials(
                        self.hass, username, password
                    )
                else:
                    raise InvalidAuth
            except InvalidAuth:
                self._errors["base"] = "invalid_auth"
            except CannotConnect:
                self._errors["base"] = "cannot_connect"
            except Exception:
                self._errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=NAME,
                    data={
                        CONF_REFRESH_TOKEN: token_data.get(CONF_REFRESH_TOKEN),
                        CONF_ACCESS_TOKEN: token_data.get(CONF_ACCESS_TOKEN),
                        CONF_EXPIRES_AT: token_data.get(CONF_EXPIRES_AT, 0),
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
        session = async_create_clientsession(self.hass)
        auth_url = DimplexApiClient(session=session).get_auth_url()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_USERNAME, default=""): str,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                    vol.Optional(CONF_AUTH_CODE, default=""): str,
                }
            ),
            errors=self._errors,
            description_placeholders={"auth_url": auth_url},
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
            title=self._config_entry.title, data=self.options
        )
