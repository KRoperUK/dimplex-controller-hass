"""Constants for dimplex_controller tests."""

from custom_components.dimplex.const import (
    CONF_ACCESS_TOKEN,
    CONF_AUTH_CODE,
    CONF_EXPIRES_AT,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
)

MOCK_CONFIG = {CONF_AUTH_CODE: "test_auth_code"}
MOCK_CREDENTIALS = {
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: "secret",
}
MOCK_ENTRY_DATA = {
    CONF_REFRESH_TOKEN: "refresh_token",
    CONF_ACCESS_TOKEN: "access_token",
    CONF_EXPIRES_AT: 9999999999,
}
