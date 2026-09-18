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
    HygieneFrequency,
    SetbackStatus,
    TokenBundle,
    parse_telemetry_points,
)

from .capabilities import product_for_appliance, product_lookup
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
        self._product_models: list[Any] | None = None
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
            # Not fatal: an opaque token has no readable exp, in which case 0
            # means "unknown" and the caller falls back to a refresh. Logged so a
            # token that *looks* like a JWT but will not parse is not invisible.
            _LOGGER.debug("Access token is not a parseable JWT; no expiry available", exc_info=True)
            return 0

        return 0

    async def _resolve_account_id(self) -> str | None:
        """Return a stable identifier for the authenticated account.

        ``get_user_context`` supplies the Dimplex account id, which is what the
        config entry is keyed on. When it omits one, fall back to the account's
        first hub id — still stable, and it keeps the entry from being created
        with no unique id at all, which allowed a duplicate entry polling the
        cloud twice (dimplex-controller-hass#198).
        """
        context = await self._client.get_user_context()
        account_id = getattr(context, "Id", None)
        if account_id:
            return str(account_id)

        for hub in await self._client.get_hubs():
            hub_id = getattr(hub, "HubId", None)
            if hub_id:
                _LOGGER.warning(
                    "Dimplex user context carried no account id; using hub %s as the config entry's unique id instead",
                    hub_id,
                )
                return str(hub_id)
        return None

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
            self._account_id = await self._resolve_account_id()
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
            self._account_id = await self._resolve_account_id()
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

    async def async_get_product_models(self) -> list[Any]:
        """Fetch the account's product catalogue, caching it once it succeeds.

        The catalogue is account-wide and static, but it is the only source of the
        ``AUTOMATIC_PROVISIONING`` metadata behind the ``storage``, ``energy_meter``,
        ``hot_water`` and ``heat_pump`` capability flags — the integration never
        called it, so those flags could not be derived at all (#199).

        Best-effort: a failure leaves the cache empty and is retried on the next
        poll, and capability derivation falls back to the appliance's own type
        tokens. It deliberately does not fail the status poll.
        """
        if self._product_models is not None:
            return self._product_models
        try:
            models = list(await self._client.get_product_models())
        except (DimplexAuthError, DimplexConnectionError, DimplexApiError) as exception:
            _LOGGER.debug("Product catalogue unavailable; capability flags fall back to type tokens: %s", exception)
            return []
        self._product_models = models
        return models

    async def async_get_status_data(self) -> dict[str, Any]:
        """Fetch hubs, zones, and appliance overview (no energy)."""
        try:
            hubs = await self._client.get_hubs()
            products = product_lookup(await self.async_get_product_models())
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
                                # Catalogue row for this appliance, or None. Carried
                                # on the row so capability derivation does not need
                                # the client (#199).
                                "product": product_for_appliance(products, appliance),
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

    async def async_set_setback_temperature(
        self,
        hub_id: str,
        appliance_id: str,
        temperature: float,
        status: int | SetbackStatus = SetbackStatus.ACTIVE,
    ) -> None:
        """Write the setback (reduced) target temperature.

        Setback was read-only: the cloud exposes ``SetSetbackTemperature`` and the
        official app drives it, but nothing in the integration called it, so users
        could see the setback temperature and not change it (#199).

        ``status`` is the ``EStatus`` byte the endpoint carries. It defaults to
        ACTIVE, which is what "set my setback temperature" means — the cloud's other
        values describe the appliance being driven by its own schedule or by a
        demand-side-response signal, not a user choice.
        """
        with _translated_errors():
            await self._client.set_setback_temperature(
                hub_id,
                [appliance_id],
                temperature=temperature,
                status=status,
            )

    async def async_get_schedule(self, hub_id: str, appliance_id: str) -> Any:
        """Return timer mode settings for an appliance (read-only schedule)."""
        with _translated_errors():
            if hasattr(self._client, "get_schedule"):
                return await self._client.get_schedule(hub_id, appliance_id)
            return await self._client.get_appliance_features(hub_id, appliance_id)

    async def async_set_hot_water_temperature(
        self,
        hub_id: str,
        appliance_id: str,
        *,
        mode: str,
        temperature: float,
        enable: bool = True,
    ) -> None:
        """Set a cylinder's Normal or Boost temperature.

        ``mode`` is ``"normal"`` or ``"boost"``. Unlike the mode and hygiene writes
        there is no ASHW-specific variant of these two endpoints, so no heat-pump
        flag is needed.

        .. warning:: Untested — the endpoints are confirmed from the decompiled app
           and have never been run against a real cylinder (#199).
        """
        with _translated_errors():
            if mode == "boost":
                await self._client.set_hot_water_boost_temperature(
                    hub_id,
                    [appliance_id],
                    temperature,
                    enable=enable,
                )
            else:
                await self._client.set_hot_water_normal_temperature(
                    hub_id,
                    [appliance_id],
                    temperature,
                    enable=enable,
                )

    async def async_set_hot_water_hygiene(
        self,
        hub_id: str,
        appliance_id: str,
        *,
        temperature: float,
        frequency: int | HygieneFrequency = HygieneFrequency.WEEKLY,
        enable: bool = True,
        heat_pump: bool = False,
    ) -> None:
        """Configure the cylinder's anti-legionella (hygiene) cycle.

        .. warning:: Untested — APK-confirmed only, and the likeliest of these
           endpoints to be refused by a given hub (#199).
        """
        with _translated_errors():
            await self._client.set_hot_water_hygiene(
                hub_id,
                [appliance_id],
                temperature=temperature,
                frequency=frequency,
                enable=enable,
                heat_pump=heat_pump,
            )

    async def async_get_hot_water_schedule(self, hub_id: str, appliance_id: str) -> Any:
        """Read a heat-pump cylinder's schedule.

        Only ASHW cylinders expose a hot-water schedule; a plain cylinder has no
        equivalent read endpoint.
        """
        with _translated_errors():
            return await self._client.get_heat_pump_hot_water_schedule(hub_id, appliance_id)

    async def async_copy_schedule(
        self,
        hub_id: str,
        from_appliance_id: str,
        appliance_ids: list[str],
        *,
        timer_mode: int = 0,
    ) -> None:
        """Apply one appliance's weekly programme to other appliances.

        ``CopyScheduleToAppliances`` maps neatly onto "make these heaters follow the
        same schedule as that one", and until now had no caller — the integration
        could read a schedule and not propagate it (#199).
        """
        with _translated_errors():
            await self._client.copy_schedule_to_appliances(
                hub_id,
                from_appliance_id,
                appliance_ids,
                timer_mode=timer_mode,
            )

    async def async_set_period_setpoint(
        self,
        hub_id: str,
        appliance_id: str,
        *,
        day_of_week: int,
        start_time: str,
        temperature: float,
        end_time: str | None = None,
    ) -> Any:
        """Update one timer period's setpoint without rewriting the rest.

        Periods are matched on ``DayOfWeek`` + ``StartTime``, so the caller has to
        name an existing period — the library raises ``ValueError`` for one that does
        not exist, which callers should turn into a readable error rather than a
        traceback. Returns the updated ``TimerModeSettings``.
        """
        with _translated_errors():
            return await self._client.set_period_setpoint(
                hub_id,
                appliance_id,
                day_of_week=day_of_week,
                start_time=start_time,
                temperature=temperature,
                end_time=end_time,
            )

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
        a target between 7 and 18 °C (its own bounds, below the 7–30 °C the other
        mode carousels use) and defaults to the 7 °C anti-freeze floor, so a low
        temperature here is by design, not a fault.
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
