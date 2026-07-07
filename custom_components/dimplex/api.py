"""API adapter for Dimplex Controller."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

import aiohttp
from dimplex_controller import (
    DimplexApiError,
    DimplexAuthError,
    DimplexConnectionError,
    DimplexControl,
)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class DimplexApiClient:
    """Adapter around `dimplex_controller.DimplexControl`."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str | None = None,
        access_token: str | None = None,
        expires_at: float = 0,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the API adapter."""
        self._session = session
        self._username = username
        self._password = password
        self._client = DimplexControl(
            session=session,
            refresh_token=refresh_token,
            access_token=access_token,
            expires_at=expires_at,
        )

    @property
    def token_data(self) -> dict[str, Any]:
        """Return current auth token payload for persistence."""
        return {
            "access_token": self._client.auth._access_token,
            "refresh_token": self._client.auth._refresh_token,
            "expires_at": self._client.auth._expires_at,
        }

    @staticmethod
    def _extract_expiry(access_token: str) -> float:
        """Extract the exp claim from a JWT access token."""
        try:
            payload_part = access_token.split(".")[1]
            payload_part += "=" * (-len(payload_part) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_part.encode()))
            exp = payload.get("exp")
            if isinstance(exp, int | float):
                return float(exp)
        except Exception:
            return 0

        return 0

    async def async_initialize(self) -> None:
        """Ensure the underlying library is authenticated."""
        if self._client.auth._refresh_token:
            try:
                await self._client.auth.get_access_token()
                return
            except DimplexAuthError as exception:
                raise InvalidAuth from exception
            except DimplexConnectionError as exception:
                raise CannotConnect from exception

        if self._client.auth._access_token:
            if not self._client.auth._expires_at:
                self._client.auth._expires_at = self._extract_expiry(self._client.auth._access_token)

            if self._client.auth._expires_at:
                if self._client.auth._expires_at <= datetime.now(UTC).timestamp():
                    raise InvalidAuth
                return

        if not self._username or not self._password:
            raise InvalidAuth

        try:
            await self._client.auth.headless_login(self._username, self._password)
            await self._client.auth.get_access_token()
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception

    async def async_validate_connection(self) -> dict[str, Any]:
        """Validate credentials/token and return token payload."""
        try:
            await self.async_initialize()
            await self._client.get_user_context()
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            raise CannotConnect from exception

        return self.token_data

    async def async_exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange auth code for tokens and validate the session."""
        try:
            await self._client.auth.exchange_code(code)
            await self._client.get_user_context()
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            raise CannotConnect from exception

        return self.token_data

    def get_auth_url(self) -> str:
        """Return the browser auth URL for manual token generation."""
        auth_manager = self._client.auth
        if hasattr(auth_manager, "get_auth_url"):
            return auth_manager.get_auth_url()

        return auth_manager.get_login_url()

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch hubs, zones, and appliance overview data."""
        try:
            hubs = await self._client.get_hubs()
            appliance_rows: list[dict[str, Any]] = []

            for hub in hubs:
                zones = await self._client.get_hub_zones(hub.HubId)
                appliance_ids = [appliance.ApplianceId for zone in zones for appliance in zone.Appliances]

                overview_by_id: dict[str, Any] = {}
                if appliance_ids:
                    overview = await self._client.get_appliance_overview(hub.HubId, appliance_ids)
                    overview_by_id = {status.ApplianceId: status for status in overview}

                for zone in zones:
                    for appliance in zone.Appliances:
                        appliance_rows.append(
                            {
                                "hub": hub,
                                "zone": zone,
                                "appliance": appliance,
                                "status": overview_by_id.get(appliance.ApplianceId),
                            }
                        )

            return {"appliances": appliance_rows}
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            raise CannotConnect from exception

    async def async_set_eco_start(self, hub_id: str, appliance_id: str, enable: bool) -> None:
        """Enable or disable EcoStart for an appliance."""
        try:
            await self._client.set_eco_start(hub_id, [appliance_id], enable)
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            raise CannotConnect from exception
