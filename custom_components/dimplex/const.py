"""Constants for dimplex integration."""

from datetime import timedelta

from homeassistant.const import Platform

NAME = "Dimplex Hub"
DOMAIN = "dimplex"
VERSION = "2.0.0"  # x-release-please-version
DOCS_URL = "https://github.com/kroperuk/dimplex-controller-hass"
ISSUE_URL = "https://github.com/kroperuk/dimplex-controller-hass/issues"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_AUTH_CODE = "auth_code"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCESS_TOKEN = "access_token"
CONF_EXPIRES_AT = "expires_at"

COORDINATOR_UPDATE_INTERVAL = timedelta(seconds=30)

# Energy monitoring — POST /Reports/GetTsiEnergyReportDataForHub.
# The cloud returns one telemetry bucket per appliance; a 30-day rolling
# window with hourly buckets is a reasonable default that keeps the
# response small while still giving the Energy Dashboard something useful.
ENERGY_REPORT_DAYS = 30
ENERGY_REPORT_INTERVAL = "01:00:00"

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
