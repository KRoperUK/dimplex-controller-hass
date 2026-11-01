"""Hot-water holiday mode with an end date and time.

The cylinder only counts holidays in whole days, so Home Assistant keeps the
chosen end time itself and clears Holiday at exactly that moment. The cloud is
still sent the rounded-up day count, so the cylinder comes off holiday on its own
even if Home Assistant is down at the end time.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import DimplexApiClient
from .capabilities import capabilities_for_row
from .const import DOMAIN, HOLIDAY_FLAG, has_any_mode
from .errors import control_errors

DEFAULT_HOLIDAY = timedelta(days=7)


class HolidayManager:
    """Per-entry holiday end times and the timers that act on them."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DimplexApiClient,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
    ) -> None:
        self._hass = hass
        self._api = api
        self._coordinator = coordinator
        self.ends: dict[str, datetime] = {}
        self._timers: dict[str, Callable[[], None]] = {}
        self._listeners: dict[str, list[Callable[[], None]]] = {}

    def _row(self, appliance_id: str) -> dict[str, Any] | None:
        rows: list[dict[str, Any]] = (self._coordinator.data or {}).get("appliances", [])
        for row in rows:
            if row["appliance"].ApplianceId == appliance_id:
                return row
        return None

    def is_active(self, appliance_id: str) -> bool:
        row = self._row(appliance_id)
        return bool(row and has_any_mode(row.get("status"), HOLIDAY_FLAG))

    def add_listener(self, appliance_id: str, listener: Callable[[], None]) -> Callable[[], None]:
        """Call ``listener`` when an appliance's end time changes."""
        self._listeners.setdefault(appliance_id, []).append(listener)
        return lambda: self._listeners[appliance_id].remove(listener)

    def _notify(self, appliance_id: str) -> None:
        for listener in list(self._listeners.get(appliance_id, [])):
            listener()

    async def async_set_end(self, appliance_id: str, end: datetime) -> None:
        """Choose when Holiday ends; re-sends the holiday if one is running."""
        end = dt_util.as_utc(end)
        if end <= dt_util.utcnow():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="holiday_end_in_past",
            )
        self.ends[appliance_id] = end
        self._notify(appliance_id)
        if self.is_active(appliance_id):
            await self.async_start(appliance_id)

    def restore_end(self, appliance_id: str, end: datetime) -> None:
        """Reload a saved end time after a restart and act on it."""
        self.ends[appliance_id] = dt_util.as_utc(end)
        self._notify(appliance_id)
        if not self.is_active(appliance_id):
            return
        if self.ends[appliance_id] <= dt_util.utcnow():
            # The end passed while Home Assistant was down.
            self._hass.async_create_task(self.async_stop(appliance_id))
        else:
            self._schedule(appliance_id)

    async def async_start(self, appliance_id: str) -> None:
        """Engage Holiday until the chosen end (a week from now if none is set)."""
        end = self.ends.get(appliance_id)
        if end is None or end <= dt_util.utcnow():
            end = (dt_util.utcnow() + DEFAULT_HOLIDAY).replace(second=0, microsecond=0)
            self.ends[appliance_id] = end
            self._notify(appliance_id)
        await self._send(appliance_id, True, end)
        self._schedule(appliance_id)

    async def async_stop(self, appliance_id: str) -> None:
        """Clear Holiday now."""
        self._cancel(appliance_id)
        await self._send(appliance_id, False, None)

    async def _send(self, appliance_id: str, enable: bool, end: datetime | None) -> None:
        row = self._row(appliance_id)
        if row is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="cylinder_unavailable",
            )
        caps = capabilities_for_row(row["appliance"], row.get("status"), row.get("product"))
        name = getattr(row["appliance"], "FriendlyName", None) or "hot-water cylinder"
        with control_errors(name):
            await self._api.async_set_hot_water_holiday(
                row["hub"].HubId,
                appliance_id,
                enable=enable,
                until=end,
                heat_pump=caps.heat_pump,
            )
        await self._coordinator.async_request_refresh()

    def _schedule(self, appliance_id: str) -> None:
        self._cancel(appliance_id)
        end = self.ends[appliance_id]

        @callback
        def _end_reached(_now: datetime) -> None:
            self._timers.pop(appliance_id, None)
            if self.is_active(appliance_id):
                self._hass.async_create_task(self.async_stop(appliance_id))

        self._timers[appliance_id] = async_track_point_in_utc_time(self._hass, _end_reached, end)

    def _cancel(self, appliance_id: str) -> None:
        unsub = self._timers.pop(appliance_id, None)
        if unsub is not None:
            unsub()

    @callback
    def async_shutdown(self) -> None:
        for appliance_id in list(self._timers):
            self._cancel(appliance_id)
