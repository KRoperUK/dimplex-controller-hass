"""Adds config flow for dimplex_controller."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import CannotConnect, DimplexApiClient, InvalidAuth
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_AUTH_CODE,
    CONF_ENERGY_INTERVAL,
    CONF_EXPIRES_AT,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_STATUS_INTERVAL,
    CONF_USERNAME,
    DEFAULT_ENERGY_INTERVAL,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    NAME,
    PLATFORMS,
)


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


async def validate_auth_code(hass: HomeAssistant, auth_input: str) -> dict[str, Any]:
    """Exchange auth code and validate user session."""
    code = _extract_auth_code(auth_input)
    if not code:
        raise InvalidAuth

    session = async_create_clientsession(hass)
    client = DimplexApiClient(session=session)
    return await client.async_exchange_code(code)


async def validate_credentials(hass: HomeAssistant, username: str, password: str) -> dict[str, Any]:
    """Validate username/password login and return token details."""
    session = async_create_clientsession(hass)
    client = DimplexApiClient(session, None, None, 0, username, password)
    return await client.async_validate_connection()


class DimplexFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for dimplex."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Initialize."""
        self._errors: dict[str, str] = {}

    # ── step: user (initial menu) ──────────────────────────────
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            method = user_input.get("auth_method", "credentials")
            if method == "credentials":
                return await self.async_step_credentials()
            return await self.async_step_auth_code()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_method", default="credentials"): vol.In(
                        {
                            "credentials": "Email / password (recommended)",
                            "auth_code": "Manual auth code from browser",
                        }
                    ),
                }
            ),
            errors=self._errors,
        )

    # ── step: credentials ───────────────────────────────────────
    async def async_step_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the email/password credential login step."""
        self._errors = {}

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "")

            if not username or not password:
                self._errors["base"] = "invalid_auth"
            else:
                try:
                    token_data = await validate_credentials(self.hass, username, password)
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
                            CONF_USERNAME: username,
                        },
                    )

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=self._errors,
        )

    # ── step: auth_code ─────────────────────────────────────────
    async def async_step_auth_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the manual auth-code login step."""
        self._errors = {}

        session = async_create_clientsession(self.hass)
        auth_url = DimplexApiClient(session=session).get_auth_url()

        if user_input is not None:
            auth_code = user_input.get(CONF_AUTH_CODE, "").strip()

            if not auth_code:
                self._errors["base"] = "invalid_auth"
            else:
                try:
                    token_data = await validate_auth_code(self.hass, auth_code)
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

        return self.async_show_form(
            step_id="auth_code",
            data_schema=vol.Schema({vol.Required(CONF_AUTH_CODE): str}),
            errors=self._errors,
            description_placeholders={"auth_url": auth_url},
        )

    # ── options ─────────────────────────────────────────────────
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DimplexOptionsFlowHandler(config_entry)

    # ══ reauthentication ════════════════════════════════════════

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle re-authentication — choose method."""
        self._errors = {}

        if user_input is not None:
            method = user_input.get("auth_method", "credentials")
            if method == "credentials":
                return await self.async_step_reauth_credentials()
            return await self.async_step_reauth_auth_code()

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_method", default="credentials"): vol.In(
                        {
                            "credentials": "Email / password (recommended)",
                            "auth_code": "Manual auth code from browser",
                        }
                    ),
                }
            ),
            errors=self._errors,
        )

    async def async_step_reauth_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Re-authenticate with email/password."""
        self._errors = {}

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "")

            if not username or not password:
                self._errors["base"] = "invalid_auth"
            else:
                try:
                    token_data = await validate_credentials(self.hass, username, password)
                except InvalidAuth:
                    self._errors["base"] = "invalid_auth"
                except CannotConnect:
                    self._errors["base"] = "cannot_connect"
                except Exception:
                    self._errors["base"] = "unknown"
                else:
                    return await self._finish_reauth(token_data)

        return self.async_show_form(
            step_id="reauth_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=self._errors,
        )

    async def async_step_reauth_auth_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Re-authenticate with manual auth code."""
        self._errors = {}

        session = async_create_clientsession(self.hass)
        auth_url = DimplexApiClient(session=session).get_auth_url()

        if user_input is not None:
            auth_code = user_input.get(CONF_AUTH_CODE, "").strip()

            if not auth_code:
                self._errors["base"] = "invalid_auth"
            else:
                try:
                    token_data = await validate_auth_code(self.hass, auth_code)
                except InvalidAuth:
                    self._errors["base"] = "invalid_auth"
                except CannotConnect:
                    self._errors["base"] = "cannot_connect"
                except Exception:
                    self._errors["base"] = "unknown"
                else:
                    return await self._finish_reauth(token_data)

        return self.async_show_form(
            step_id="reauth_auth_code",
            data_schema=vol.Schema({vol.Required(CONF_AUTH_CODE): str}),
            errors=self._errors,
            description_placeholders={"auth_url": auth_url},
        )

    async def _finish_reauth(self, token_data: dict[str, Any]) -> ConfigFlowResult:
        """Update the existing config entry with new tokens and re-load."""
        entry_id = self.context["entry_id"]
        existing_entry = self.hass.config_entries.async_get_entry(entry_id)
        if existing_entry is None:
            return self.async_abort(reason="reauth_successful")
        self.hass.config_entries.async_update_entry(
            existing_entry,
            data={
                **existing_entry.data,
                CONF_REFRESH_TOKEN: token_data.get(CONF_REFRESH_TOKEN),
                CONF_ACCESS_TOKEN: token_data.get(CONF_ACCESS_TOKEN),
                CONF_EXPIRES_AT: token_data.get(CONF_EXPIRES_AT, 0),
            },
        )
        await self.hass.config_entries.async_reload(existing_entry.entry_id)
        return self.async_abort(reason="reauth_successful")


class DimplexOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options handler for dimplex."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self.options: dict[str, Any] = dict(config_entry.options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        schema: dict[Any, Any] = {
            vol.Required(
                x.value,
                default=self.options.get(x.value, True),
            ): bool
            for x in sorted(PLATFORMS)
        }
        schema[
            vol.Optional(
                CONF_STATUS_INTERVAL,
                default=int(self.options.get(CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL.total_seconds())),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=15, max=3600))
        schema[
            vol.Optional(
                CONF_ENERGY_INTERVAL,
                default=int(self.options.get(CONF_ENERGY_INTERVAL, DEFAULT_ENERGY_INTERVAL.total_seconds())),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=60, max=86400))

        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema))

    async def _update_options(self) -> ConfigFlowResult:
        """Update config entry options."""
        return self.async_create_entry(title=self._config_entry.title, data=self.options)
