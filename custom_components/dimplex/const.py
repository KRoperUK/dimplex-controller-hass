"""Constants for dimplex integration."""

from datetime import timedelta
from typing import Any

import dimplex_controller as _dc
from dimplex_controller import (
    MODE_TEMP_MAX,
    MODE_TEMP_MIN,
    NO_SETPOINT_SENTINEL,
    ApplianceModeFlag,
    TimerMode,
)
from homeassistant.const import Platform

# The Dimplex cloud reports 0xFF (255) for a temperature field when there is no
# active value for it — e.g. ``ActiveSetPointTemperature`` while the heater is
# idle, running EcoStart, or between schedule periods. Surfacing that verbatim
# produced a nonsensical "255 °C" target temperature on the climate entity and
# the target-temperature sensor. Treat 255 (and anything at/above it) as unset.
SETPOINT_SENTINEL = float(NO_SETPOINT_SENTINEL)

# --- Temperature bounds ----------------------------------------------------
# Setpoints and most mode carousels span 7–30 °C.
SETPOINT_TEMP_MIN = float(MODE_TEMP_MIN)
SETPOINT_TEMP_MAX = float(MODE_TEMP_MAX)

# Away is the exception: the cloud accepts only 7–18 °C for it, and the official
# app's Away picker will not offer above 18. A higher request is silently reduced
# to 18 somewhere in the cloud or the appliance, so clamp locally and say so
# rather than letting it happen invisibly (#174).
#
# Prefer the library's own bounds once it publishes Away-specific ones
# (KRoperUK/dimplex-controller-py#98); until then use the measured figures.
AWAY_TEMP_MIN = float(getattr(_dc, "AWAY_TEMP_MIN", 7.0))
AWAY_TEMP_MAX = float(getattr(_dc, "AWAY_TEMP_MAX", 18.0))

# --- Appliance mode bits ---------------------------------------------------
# ``EApplianceModes`` values, sourced from the library rather than hard-coded.
# Before dimplex-controller 0.13.0 this integration assumed boost was bit 16
# and away bit 32; those are in fact Advance and FrostProtect (#163).
BOOST_FLAG = int(ApplianceModeFlag.BOOST)
AWAY_FLAG = int(ApplianceModeFlag.AWAY)
ADVANCE_FLAG = int(ApplianceModeFlag.ADVANCE)
FROST_FLAG = int(ApplianceModeFlag.FROST_PROTECT)

# Modes that mean the appliance is being driven above its schedule, and so is
# probably drawing power. Used to keep energy polling responsive and to
# estimate live power.
HEAT_DEMAND_FLAGS = BOOST_FLAG | ADVANCE_FLAG

# --- Timer modes -----------------------------------------------------------
TIMER_USER = int(TimerMode.USER_TIMER)
TIMER_MANUAL = int(TimerMode.MANUAL)
TIMER_FROST = int(TimerMode.FROST_PROTECTION)
TIMER_OFF = int(TimerMode.OFF)
# Timer modes the app presents as "off" for most heaters.
TIMER_OFF_LIKE = frozenset({TIMER_FROST, TIMER_OFF})


def sane_temperature(value: Any) -> float | None:
    """Return a real temperature, or ``None`` for sentinel/out-of-range readings.

    ``None``/empty and the 0xFF (255) sentinel both map to ``None`` so callers
    can fall back or report "unknown" rather than an impossible value. Valid
    readings are returned as ``float``.
    """
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num >= SETPOINT_SENTINEL:
        return None
    return num


def has_any_mode(status: Any, flags: int) -> bool:
    """True when ``status.ApplianceModes`` has any bit in ``flags`` set."""
    if status is None or not flags:
        return False
    modes = getattr(status, "ApplianceModes", None)
    if modes is None:
        return False
    try:
        return bool(int(modes) & flags)
    except (TypeError, ValueError):
        return False


NAME = "Dimplex Hub"
DOMAIN = "dimplex"
VERSION = "4.1.1"  # x-release-please-version
DOCS_URL = "https://github.com/kroperuk/dimplex-controller-hass"
ISSUE_URL = "https://github.com/kroperuk/dimplex-controller-hass/issues"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_AUTH_CODE = "auth_code"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_EXPIRES_AT = "expires_at"

CONF_STATUS_INTERVAL = "status_interval"
CONF_ENERGY_INTERVAL = "energy_interval"
CONF_BOOST_DURATION = "boost_duration"
DEFAULT_BOOST_DURATION = 60

# How many coordinator updates a just-written value keeps being shown for before the
# cloud's own state is accepted instead.
#
# ``async_request_refresh`` is debounced and the appliance takes time to reflect a
# write, so the poll that follows a write usually still carries the *old* value: the
# UI snapped back and then corrected itself a poll later, which is what "my change
# didn't take" looked like (#198, #210). The bound matters too — if the cloud
# silently reduced or ignored the write, the entity must eventually show what the
# appliance actually reports.
OPTIMISTIC_UPDATES = 3

# Status (temps, modes) — cloud polling, relatively light.
DEFAULT_STATUS_INTERVAL = timedelta(seconds=30)
# Timer schedules change rarely and cost one API call per appliance, so they
# are refreshed on a slow cadence rather than on every status poll.
DEFAULT_SCHEDULE_INTERVAL = timedelta(minutes=15)
# Energy history rarely changes more than hourly; full history is heavy.
DEFAULT_ENERGY_INTERVAL = timedelta(minutes=30)
# After this many consecutive empty-but-successful energy polls, back off.
ENERGY_EMPTY_BACKOFF_THRESHOLD = 3
# Cap for adaptive energy polling when history is empty (e.g. summer).
DEFAULT_ENERGY_BACKOFF_INTERVAL = timedelta(hours=3)

COORDINATOR_UPDATE_INTERVAL = DEFAULT_STATUS_INTERVAL  # backwards-compatible alias

# Energy monitoring — POST /Reports/GetTsiEnergyReportDataForHub.
# Fetch with IncludePreviousPeriod so idle heaters still return history;
# daily / lifetime totals are computed client-side.
# How far back the energy report request asks for. **It does not bound the response.**
# With `IncludePreviousPeriod` set (which the adapter always sets, so idle appliances still
# return their history) the cloud returns the appliance's full available daily history and
# ignores this — the library's `get_tsi_energy_report` docstring says as much and tells callers
# to filter client-side. The integration deliberately does not filter: the cumulative sensors
# are meant to total everything the cloud holds.
#
# The old name was `ENERGY_REPORT_DAYS` and it was read — by two reporters, by the docs, and by
# the author of this file — as "the sensors cover 30 days". They never did (#227).
ENERGY_REQUEST_DAYS = 30
ENERGY_REPORT_INTERVAL = "00:10:00"

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
