import base64
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiohttp
from dimplex_controller import (
    DimplexApiError,
    DimplexAuthError,
    DimplexConnectionError,
    DimplexControl,
    parse_telemetry_points,
)

from .const import ENERGY_REPORT_DAYS, ENERGY_REPORT_INTERVAL

_LOGGER = logging.getLogger(__name__)


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
            energy_by_hub: dict[str, dict[str, list[tuple[datetime | None, float]]]] = {}

            for hub in hubs:
                zones = await self._client.get_hub_zones(hub.HubId)
                appliance_ids = [appliance.ApplianceId for zone in zones for appliance in zone.Appliances]

                overview_by_id: dict[str, Any] = {}
                if appliance_ids:
                    try:
                        overview = await self._client.get_appliance_overview(hub.HubId, appliance_ids)
                        overview_by_id = {status.ApplianceId: status for status in overview}
                    except DimplexApiError as exception:
                        _LOGGER.warning(
                            "Failed to fetch appliance overview in bulk for hub %s: %s. Retrying individually.",
                            hub.HubId,
                            exception,
                        )
                        for appliance_id in appliance_ids:
                            try:
                                overview = await self._client.get_appliance_overview(hub.HubId, [appliance_id])
                                if overview:
                                    overview_by_id[appliance_id] = overview[0]
                            except DimplexApiError as app_exception:
                                _LOGGER.error(
                                    "Failed to fetch overview for appliance %s: %s",
                                    appliance_id,
                                    app_exception,
                                )

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

                # Energy telemetry is hub-scoped, not appliance-scoped, so it
                # is fetched once per hub. Empty arrays are normal on hubs
                # without metered appliances or when the heaters are not
                # running, so we surface them as-is rather than treating them
                # as failures.
                energy_by_hub[hub.HubId] = await self.async_get_energy_report(hub.HubId)

            return {"appliances": appliance_rows, "energy": energy_by_hub}
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

    async def async_get_energy_report(
        self,
        hub_id: str,
        days_back: int = ENERGY_REPORT_DAYS,
        interval: str = ENERGY_REPORT_INTERVAL,
    ) -> dict[str, list[tuple[datetime | None, float]]]:
        """Fetch the per-appliance energy telemetry report for a hub.

        Returns a dict keyed by appliance id. Each value is the raw telemetry
        list (possibly empty) as returned by the cloud, normalised by
        :func:`parse_telemetry_points` into ``(timestamp, value)`` tuples
        so callers do not need to know the wire format. When the cloud
        returns no data — e.g. the hub has no metered appliances, or the
        heaters have not been running — the dict values are simply empty
        lists. That is treated as success, not an error.
        """
        try:
            report = await self._client.get_tsi_energy_report(
                hub_id=hub_id,
                report_type=1,
                interval=interval,
                days_back=days_back,
            )
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            # Some hubs (e.g. without metered appliances) return a non-200
            # response for this endpoint.  This should not fail the entire
            # coordinator refresh — just return no energy data.
            _LOGGER.warning(
                "Energy report unavailable for hub %s: %s — skipping.",
                hub_id,
                exception,
            )
            return {}

        return {
            appliance_id: parse_telemetry_points(points)
            for appliance_id, points in report.ApplianceTelemetryData.items()
        }
