"""Adapter around dimplex_controller for Home Assistant."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import aiohttp
from dimplex_controller import (
    VALUE_KEY_T2,
    DimplexApiError,
    DimplexAuthError,
    DimplexConnectionError,
    DimplexControl,
    TokenBundle,
    parse_telemetry_points,
)

from .const import ENERGY_REPORT_DAYS, ENERGY_REPORT_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Primary register keys — never include T2 (off-peak T1 vs peak T2 stay separate).
# Prefer library export when present (dimplex-controller ≥ fixed release).
try:
    from dimplex_controller import VALUE_KEY_T1 as _VALUE_KEY_T1
except ImportError:  # pragma: no cover - older wheels
    _VALUE_KEY_T1 = (
        "t1",
        "st",
        "value",
        "kwh",
        "energy",
        "consumption",
        "energykwh",
        "amount",
        "v",
    )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class ControlRejected(CannotConnect):
    """The cloud refused this control for this appliance, and a retry will not help.

    Distinct from a plain :class:`CannotConnect` — which covers timeouts, dropped
    connections and 5xx — because callers make destructive decisions on the
    difference. ``climate.async_set_temperature`` falls back to rewriting the whole
    timer schedule when the dedicated setpoint endpoint is refused; doing that for a
    transient failure would silently overwrite every period of the user's schedule
    (#197).

    Subclasses ``CannotConnect`` so existing handlers keep working unchanged.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


# Statuses that mean "this appliance/endpoint will not do this", as opposed to
# "the request did not get through". 403 is the documented Quantum case; 405 and
# 501 are the same class of answer from a hub whose firmware lacks the endpoint.
# Deliberately excludes 400 and 404: those usually mean our payload or ids are
# wrong, and retrying the same value via a destructive path would not help.
REJECTED_STATUSES = frozenset({403, 405, 501})


@contextmanager
def _translated_errors() -> Iterator[None]:
    """Map library exceptions onto the adapter's error types.

    Every control call needs the same mapping. A non-200 cloud response arrives as
    :class:`DimplexApiError` carrying its HTTP status, which is split here: a
    refusal (see :data:`REJECTED_STATUSES`, e.g. the HTTP 403 some Quantum heaters
    return for writes they do not support) becomes :class:`ControlRejected`, while
    everything else — 5xx, timeouts, dropped connections — stays
    :class:`CannotConnect`.
    """
    try:
        yield
    except DimplexAuthError as exception:
        raise InvalidAuth from exception
    except DimplexApiError as exception:
        status = getattr(exception, "status", None)
        if status in REJECTED_STATUSES:
            raise ControlRejected(str(exception), status=status) from exception
        raise CannotConnect from exception
    except DimplexConnectionError as exception:
        raise CannotConnect from exception


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
        self._account_id: str | None = None
        self._client = DimplexControl(
            session=session,
            token_bundle=TokenBundle(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=float(expires_at or 0),
            ),
        )

    @property
    def token_data(self) -> dict[str, Any]:
        """Return current auth token payload for persistence."""
        return self._client.export_tokens().as_dict()

    @property
    def account_id(self) -> str | None:
        """Return the stable Dimplex account id, if a user context was fetched.

        Populated by :meth:`async_validate_connection` / :meth:`async_exchange_code`.
        Used by the config flow as the config-entry unique id so the same
        account cannot be added twice.
        """
        return self._account_id

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
        tokens = self._client.export_tokens()
        if tokens.refresh_token:
            try:
                await self._client.auth.get_access_token()
                return
            except DimplexAuthError as exception:
                raise InvalidAuth from exception
            except DimplexConnectionError as exception:
                raise CannotConnect from exception

        if tokens.access_token:
            expires_at = tokens.expires_at
            if not expires_at:
                expires_at = self._extract_expiry(tokens.access_token)
                self._client.apply_tokens(
                    TokenBundle(
                        access_token=tokens.access_token,
                        refresh_token=tokens.refresh_token,
                        expires_at=expires_at,
                    )
                )

            if expires_at:
                if expires_at <= datetime.now(UTC).timestamp():
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
            context = await self._client.get_user_context()
            self._account_id = getattr(context, "Id", None)
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
            context = await self._client.get_user_context()
            self._account_id = getattr(context, "Id", None)
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            raise CannotConnect from exception

        return self.token_data

    def get_auth_url(self) -> str:
        """Return the browser auth URL for manual token generation."""
        return self._client.auth.get_login_url()

    async def async_get_status_data(self) -> dict[str, Any]:
        """Fetch hubs, zones, and appliance overview (no energy)."""
        try:
            hubs = await self._client.get_hubs()
            appliance_rows: list[dict[str, Any]] = []

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

            return {"appliances": appliance_rows, "hubs": hubs}
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            raise CannotConnect from exception

    async def async_get_data(self) -> dict[str, Any]:
        """Fetch status and energy (combined; used by tests / legacy callers)."""
        status = await self.async_get_status_data()
        energy_by_hub: dict[str, dict[str, dict[str, list[tuple[datetime | None, float]]]]] = {}
        for hub in status.get("hubs", []):
            energy_by_hub[hub.HubId] = await self.async_get_energy_report(hub.HubId)
        return {"appliances": status["appliances"], "energy": energy_by_hub}

    async def async_get_energy_for_hubs(self, hub_ids: list[str]) -> dict[str, Any]:
        """Fetch energy reports for the given hub ids."""
        energy_by_hub: dict[str, dict[str, dict[str, list[tuple[datetime | None, float]]]]] = {}
        for hub_id in hub_ids:
            energy_by_hub[hub_id] = await self.async_get_energy_report(hub_id)
        return {"energy": energy_by_hub}

    async def async_set_eco_start(self, hub_id: str, appliance_id: str, enable: bool) -> None:
        """Enable or disable EcoStart for an appliance."""
        with _translated_errors():
            await self._client.set_eco_start(hub_id, [appliance_id], enable)

    async def async_set_open_window_detection(self, hub_id: str, appliance_id: str, enable: bool) -> None:
        """Enable or disable open-window detection for an appliance."""
        with _translated_errors():
            await self._client.set_open_window_detection(hub_id, [appliance_id], enable)

    async def async_set_appliance_setpoint(self, hub_id: str, appliance_id: str, temperature: float) -> None:
        """Set the active setpoint via the app's own dedicated endpoint.

        ``SetApplianceSetpointTemperature`` applies the target immediately and
        leaves the stored timer periods untouched. Prefer this over
        :meth:`async_set_target_temperature`, which rewrites the schedule and is
        rejected with HTTP 403 by Quantum storage heaters (#149).
        """
        with _translated_errors():
            await self._client.set_appliance_setpoint_temperature(hub_id, [appliance_id], temperature)

    async def async_set_target_temperature(self, hub_id: str, appliance_id: str, temperature: float) -> None:
        """Set the target temperature by rewriting the timer schedule.

        Legacy path, kept as a fallback for appliances that reject the dedicated
        setpoint endpoint. Destructive: it overwrites every period's setpoint.
        """
        with _translated_errors():
            await self._client.set_target_temperature(hub_id, appliance_id, temperature)

    async def async_get_schedule(self, hub_id: str, appliance_id: str) -> Any:
        """Return timer mode settings for an appliance (read-only schedule)."""
        with _translated_errors():
            if hasattr(self._client, "get_schedule"):
                return await self._client.get_schedule(hub_id, appliance_id)
            return await self._client.get_appliance_features(hub_id, appliance_id)

    async def async_set_timer_mode(self, hub_id: str, appliance_id: str, mode: int) -> None:
        """Set the appliance timer / operation mode (manual, frost, off, …).

        Writes the schedule editor, which Quantum rejects with HTTP 403. Use
        :meth:`async_set_frost_protect` to turn an appliance off.
        """
        with _translated_errors():
            await self._client.set_mode(hub_id, appliance_id, mode)

    async def async_set_frost_protect(self, hub_id: str, appliance_id: str, *, enable: bool = True) -> None:
        """Engage or clear frost protection — how the app turns a heater off."""
        with _translated_errors():
            await self._client.set_frost_protect(hub_id, [appliance_id], enable=enable)

    async def async_set_advance(
        self,
        hub_id: str,
        appliance_id: str,
        *,
        enable: bool = True,
        temperature: float | None = None,
    ) -> None:
        """Advance to the next schedule period, or cancel an advance.

        ``temperature`` is the target to advance to. Left unset, the library
        sends the ``255`` "follow the schedule" sentinel, which is what the app
        does for Quantum and Storage Heater models.
        """
        with _translated_errors():
            await self._client.set_advance(
                hub_id,
                [appliance_id],
                enable=enable,
                temperature=temperature,
            )

    async def async_set_boost(
        self,
        hub_id: str,
        appliance_id: str,
        *,
        temperature: float,
        duration_minutes: int = 60,
        enable: bool = True,
    ) -> None:
        """Enable or disable Boost."""
        with _translated_errors():
            await self._client.set_boost(
                hub_id,
                [appliance_id],
                temperature=temperature,
                duration_minutes=duration_minutes,
                enable=enable,
            )

    async def async_set_away(
        self,
        hub_id: str,
        appliance_id: str,
        *,
        temperature: float,
        enable: bool = True,
        until: datetime | None = None,
        number_of_days: int = 0,
    ) -> None:
        """Enable or disable Away mode.

        ``until`` is the "away until" moment the app sends. ``number_of_days`` is
        the simpler equivalent — the library converts it to a date. Away accepts
        a target between 7 and 30 °C and defaults to the 7 °C anti-freeze floor,
        so a low temperature here is by design, not a fault.
        """
        with _translated_errors():
            await self._client.set_away(
                hub_id,
                [appliance_id],
                temperature=temperature,
                enable=enable,
                until=until,
                number_of_days=number_of_days,
            )

    async def async_get_energy_report(
        self,
        hub_id: str,
        days_back: int = ENERGY_REPORT_DAYS,
        interval: str = ENERGY_REPORT_INTERVAL,
    ) -> dict[str, dict[str, list[tuple[datetime | None, float]]]]:
        """Fetch the per-appliance energy telemetry report for a hub.

        Returns a dict with separate ``t1`` and ``t2`` maps (never combined).
        Each maps appliance id to normalised ``(timestamp, value)`` tuples.

        T1 and T2 are independent dual-rate registers (T1 off-peak / cheaper,
        T2 peak / more expensive). Do not sum them into a single total —
        expose each series as its own sensor.

        Empty lists are normal for hubs without metered appliances or when
        heaters have not been running *and* IncludePreviousPeriod returns
        nothing.
        """
        try:
            report = await self._client.get_tsi_energy_report(
                hub_id=hub_id,
                report_type=1,
                interval=interval,
                days_back=days_back,
                include_previous_period=True,
            )
        except DimplexAuthError as exception:
            raise InvalidAuth from exception
        except DimplexConnectionError as exception:
            raise CannotConnect from exception
        except DimplexApiError as exception:
            _LOGGER.warning(
                "Energy report unavailable for hub %s: %s — skipping.",
                hub_id,
                exception,
            )
            return {"t1": {}, "t2": {}}

        return {
            "t1": {
                appliance_id: parse_telemetry_points(points, value_keys=_VALUE_KEY_T1)
                for appliance_id, points in report.ApplianceTelemetryData.items()
            },
            "t2": {
                appliance_id: parse_telemetry_points(points, value_keys=VALUE_KEY_T2)
                for appliance_id, points in report.ApplianceTelemetryData.items()
            },
        }
