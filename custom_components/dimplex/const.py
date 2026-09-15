"""Constants for dimplex integration."""

from datetime import timedelta
from typing import Any

from dimplex_controller import (
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
VERSION = "4.0.2"  # x-release-please-version
DOCS_URL = "https://github.com/kroperuk/dimplex-controller-hass"
ISSUE_URL = "https://github.com/kroperuk/dimplex-controller-hass/issues"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
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
ENERGY_REPORT_DAYS = 30
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
