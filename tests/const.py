"""Constants for dimplex_controller tests."""

from custom_components.dimplex.const import (
    CONF_ACCESS_TOKEN,
)
from custom_components.dimplex.const import (
    CONF_EXPIRES_AT,
)
from custom_components.dimplex.const import (
    CONF_PASSWORD,
)
from custom_components.dimplex.const import (
    CONF_REFRESH_TOKEN,
)
from custom_components.dimplex.const import (
    CONF_USERNAME,
)

MOCK_CONFIG = {CONF_USERNAME: "test_username", CONF_PASSWORD: "test_password"}
MOCK_ENTRY_DATA = {
    CONF_USERNAME: "test_username",
    CONF_REFRESH_TOKEN: "refresh_token",
    CONF_ACCESS_TOKEN: "access_token",
    CONF_EXPIRES_AT: 9999999999,
}
