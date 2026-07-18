"""Constants for dimplex integration."""

from datetime import timedelta

from homeassistant.const import Platform

NAME = "Dimplex Hub"
DOMAIN = "dimplex"
VERSION = "4.0.1"  # x-release-please-version
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
