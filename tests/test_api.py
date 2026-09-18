"""Tests for dimplex API adapter."""

import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dimplex_controller import (
    DimplexApiError,
    DimplexAuthError,
    DimplexConnectionError,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.dimplex.api import CannotConnect, ControlRejected, DimplexApiClient, InvalidAuth

# asyncio_mode = auto (pyproject.toml) auto-handles async tests, so no module-level
# asyncio mark is needed — and adding one would break the sync unit tests below.


def _jwt(exp) -> str:
    """Build a minimal JWT-like string carrying an exp claim."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


async def test_validate_connection_success(hass):
    """Test connection validation with username/password login path."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="password",
    )

    with (
        patch.object(
            api._client.auth,
            "headless_login",
            new=AsyncMock(),
        ),
        patch.object(
            api._client.auth,
            "get_access_token",
            new=AsyncMock(return_value="token"),
        ),
        patch.object(
            api._client,
            "get_user_context",
            new=AsyncMock(return_value=SimpleNamespace(Id="acct-1", Name="Test User")),
        ),
    ):
        api._client.auth._refresh_token = "refresh"
        token_data = await api.async_validate_connection()

    assert token_data["refresh_token"] == "refresh"
    assert api.account_id == "acct-1"


async def test_account_id_falls_back_to_the_hub_id(hass, caplog):
    """A context without an account id keys the entry on the hub id instead.

    Regression for dimplex-controller-hass#198: with no account id the config
    flow set no unique id at all, so the same account could be added twice and
    polled twice. The hub id is still stable for the account.
    """
    import logging

    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="password",
    )

    with (
        caplog.at_level(logging.WARNING, logger="custom_components.dimplex.api"),
        patch.object(api._client, "get_user_context", new=AsyncMock(return_value=SimpleNamespace(Id=None))),
        patch.object(
            api._client,
            "get_hubs",
            new=AsyncMock(return_value=[SimpleNamespace(HubId="hub-9")]),
        ),
    ):
        assert await api._resolve_account_id() == "hub-9"

    assert "using hub hub-9 as the config entry's unique id" in caplog.text


async def test_account_id_is_none_when_there_is_no_hub_either(hass):
    """Nothing stable to key on: return None rather than inventing an id."""
    api = DimplexApiClient(session=async_get_clientsession(hass))

    with (
        patch.object(api._client, "get_user_context", new=AsyncMock(return_value=SimpleNamespace(Id=None))),
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[])),
    ):
        assert await api._resolve_account_id() is None


def test_extract_expiry_logs_an_unparseable_token(hass, caplog):
    """A token that will not parse is logged rather than swallowed silently."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="custom_components.dimplex.api"):
        assert DimplexApiClient._extract_expiry("not-a-jwt") == 0  # noqa: SLF001

    assert "not a parseable JWT" in caplog.text


async def test_validate_connection_invalid_auth(hass):
    """Test auth failure mapping."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="wrong",
    )

    with (
        patch.object(
            api._client.auth,
            "headless_login",
            new=AsyncMock(side_effect=DimplexAuthError("failed")),
        ),
        pytest.raises(InvalidAuth),
    ):
        await api.async_validate_connection()


async def test_validate_connection_cannot_connect(hass):
    """Test connectivity failure mapping."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="password",
    )

    with (
        patch.object(
            api._client.auth,
            "headless_login",
            new=AsyncMock(side_effect=DimplexConnectionError("offline")),
        ),
        pytest.raises(CannotConnect),
    ):
        await api.async_validate_connection()


async def test_async_get_data_maps_appliances(hass):
    """Test that API payload is transformed into appliance rows."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    status = SimpleNamespace(ApplianceId="appliance-1", EcoStartEnabled=True)
    energy_report = SimpleNamespace(
        ApplianceTelemetryData={
            "appliance-1": [
                {"timestamp": "2026-06-01T00:00:00Z", "value": 0.1},
            ]
        }
    )

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        # The catalogue is fetched once per client to feed capability derivation
        # (#199); an account with none is the normal case for these fixtures.
        patch.object(api._client, "get_product_models", new=AsyncMock(return_value=[])),
        patch.object(
            api._client,
            "get_hub_zones",
            new=AsyncMock(return_value=[zone]),
        ),
        patch.object(
            api._client,
            "get_appliance_overview",
            new=AsyncMock(return_value=[status]),
        ),
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(return_value=energy_report),
        ),
    ):
        data = await api.async_get_data()

    assert len(data["appliances"]) == 1
    assert data["appliances"][0]["appliance"].ApplianceId == "appliance-1"
    # Energy report is indexed by hub id, then by appliance id, and each value
    # is the parsed telemetry list (one normalised point per cloud entry).
    assert "hub-1" in data["energy"]
    assert data["energy"]["hub-1"]["t1"]["appliance-1"] == [(datetime(2026, 6, 1, tzinfo=UTC), 0.1)]
    assert data["energy"]["hub-1"]["t2"]["appliance-1"] == []


async def test_async_get_data_maps_st_telemetry(hass):
    """QRAD models return energy values keyed as ``ST`` instead of ``T1``."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="QRAD075F",
    )
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    status = SimpleNamespace(ApplianceId="appliance-1", EcoStartEnabled=True)
    energy_report = SimpleNamespace(
        ApplianceTelemetryData={
            "appliance-1": [
                {"TS": 1783773600, "ST": 0.06},
            ]
        }
    )

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        # The catalogue is fetched once per client to feed capability derivation
        # (#199); an account with none is the normal case for these fixtures.
        patch.object(api._client, "get_product_models", new=AsyncMock(return_value=[])),
        patch.object(
            api._client,
            "get_hub_zones",
            new=AsyncMock(return_value=[zone]),
        ),
        patch.object(
            api._client,
            "get_appliance_overview",
            new=AsyncMock(return_value=[status]),
        ),
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(return_value=energy_report),
        ),
    ):
        data = await api.async_get_data()

    assert data["energy"]["hub-1"]["t1"]["appliance-1"] == [(datetime(2026, 7, 11, 12, 40, tzinfo=UTC), 0.06)]
    assert data["energy"]["hub-1"]["t2"]["appliance-1"] == []


async def test_async_get_data_overview_fallback(hass):
    """Test that if bulk get_appliance_overview fails, we retry individually."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    status = SimpleNamespace(ApplianceId="appliance-1", EcoStartEnabled=True)
    energy_report = SimpleNamespace(ApplianceTelemetryData={})

    # Side effect: first call (bulk) raises error, second call (individual) succeeds
    mock_overview = AsyncMock()
    mock_overview.side_effect = [
        DimplexApiError(400, "Bad Request"),
        [status],
    ]

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        # The catalogue is fetched once per client to feed capability derivation
        # (#199); an account with none is the normal case for these fixtures.
        patch.object(api._client, "get_product_models", new=AsyncMock(return_value=[])),
        patch.object(api._client, "get_hub_zones", new=AsyncMock(return_value=[zone])),
        patch.object(api._client, "get_appliance_overview", new=mock_overview),
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(return_value=energy_report),
        ),
    ):
        data = await api.async_get_data()

    assert len(data["appliances"]) == 1
    assert data["appliances"][0]["status"] == status
    assert mock_overview.call_count == 2


async def test_async_get_data_energy_report_api_error_is_skipped(hass):
    """Test that a DimplexApiError from the energy report does not fail the coordinator."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    status = SimpleNamespace(ApplianceId="appliance-1", EcoStartEnabled=True)

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        # The catalogue is fetched once per client to feed capability derivation
        # (#199); an account with none is the normal case for these fixtures.
        patch.object(api._client, "get_product_models", new=AsyncMock(return_value=[])),
        patch.object(api._client, "get_hub_zones", new=AsyncMock(return_value=[zone])),
        patch.object(
            api._client,
            "get_appliance_overview",
            new=AsyncMock(return_value=[status]),
        ),
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(side_effect=DimplexApiError(404, "Not Found")),
        ),
    ):
        data = await api.async_get_data()

    # Appliances should still load; energy should contain empty t1/t2 dicts for this hub
    assert len(data["appliances"]) == 1
    assert data["energy"]["hub-1"] == {"t1": {}, "t2": {}}


async def test_set_eco_start_calls_library(hass):
    """Test eco start control call delegates to library client."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    with patch.object(api._client, "set_eco_start", new=AsyncMock()) as set_eco_start:
        await api.async_set_eco_start("hub-1", "appliance-1", True)

    set_eco_start.assert_awaited_once_with("hub-1", ["appliance-1"], True)


async def test_exchange_code_success(hass):
    """Test auth code exchange returns token payload."""
    api = DimplexApiClient(session=async_get_clientsession(hass))

    with (
        patch.object(
            api._client.auth,
            "exchange_code",
            new=AsyncMock(),
        ),
        patch.object(
            api._client,
            "get_user_context",
            new=AsyncMock(return_value=SimpleNamespace(Id="acct-2", Name="Test User")),
        ),
    ):
        api._client.auth._access_token = "access"
        api._client.auth._refresh_token = "refresh"
        api._client.auth._expires_at = 123
        token_data = await api.async_exchange_code("test-code")

    assert token_data["access_token"] == "access"
    assert token_data["refresh_token"] == "refresh"
    assert api.account_id == "acct-2"


# ---------------------------------------------------------------------------
# _extract_expiry
# ---------------------------------------------------------------------------


def test_extract_expiry_valid():
    """A valid JWT exp claim is parsed to a float."""
    assert DimplexApiClient._extract_expiry(_jwt(1893456000)) == 1893456000.0


def test_extract_expiry_invalid_returns_zero():
    """A malformed token yields 0 instead of raising."""
    assert DimplexApiClient._extract_expiry("not-a-jwt") == 0


# ---------------------------------------------------------------------------
# async_initialize branches
# ---------------------------------------------------------------------------


async def test_initialize_refresh_token_path(hass):
    """A stored refresh token just refreshes the access token."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="refresh")
    with patch.object(api._client.auth, "get_access_token", new=AsyncMock(return_value="token")) as get_token:
        await api.async_initialize()
    get_token.assert_awaited_once()


async def test_initialize_refresh_token_auth_error(hass):
    """Auth errors during refresh map to InvalidAuth."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="refresh")
    with (
        patch.object(
            api._client.auth,
            "get_access_token",
            new=AsyncMock(side_effect=DimplexAuthError("nope")),
        ),
        pytest.raises(InvalidAuth),
    ):
        await api.async_initialize()


async def test_initialize_access_token_not_expired(hass):
    """A non-expired access token short-circuits initialization."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = "access"
    api._client.auth._expires_at = 1893456000  # far future
    await api.async_initialize()  # should not raise


async def test_initialize_access_token_expired(hass):
    """An expired access token raises InvalidAuth."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = "access"
    api._client.auth._expires_at = 1  # epoch, long expired
    with pytest.raises(InvalidAuth):
        await api.async_initialize()


async def test_initialize_access_token_expiry_from_jwt(hass):
    """When expires_at is unset, it is derived from the JWT."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = _jwt(1893456000)
    api._client.auth._expires_at = 0
    await api.async_initialize()  # should not raise
    assert api._client.auth._expires_at == 1893456000.0


async def test_initialize_no_credentials(hass):
    """No refresh token, access token, or credentials raises InvalidAuth."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = None
    with pytest.raises(InvalidAuth):
        await api.async_initialize()


# ---------------------------------------------------------------------------
# get_auth_url
# ---------------------------------------------------------------------------


def test_get_auth_url_uses_login_url():
    """get_auth_url delegates to the library auth manager login URL."""
    api = DimplexApiClient(session=MagicMock())
    api._client.auth = SimpleNamespace(get_login_url=lambda: "https://login/url")
    assert api.get_auth_url() == "https://login/url"


# ---------------------------------------------------------------------------
# Error mapping for data + control calls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (DimplexAuthError("a"), InvalidAuth),
        (DimplexConnectionError("c"), CannotConnect),
        (DimplexApiError(500, "e"), CannotConnect),
    ],
)
async def test_get_data_error_mapping(hass, exc, expected):
    """Library errors during data fetch map to integration exceptions."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(side_effect=exc)),
        pytest.raises(expected),
    ):
        await api.async_get_data()


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (DimplexAuthError("a"), InvalidAuth),
        (DimplexConnectionError("c"), CannotConnect),
        (DimplexApiError(500, "e"), CannotConnect),
    ],
)
async def test_set_eco_start_error_mapping(hass, exc, expected):
    """Library errors during control map to integration exceptions."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(api._client, "set_eco_start", new=AsyncMock(side_effect=exc)),
        pytest.raises(expected),
    ):
        await api.async_set_eco_start("hub-1", "appliance-1", True)


# ---------------------------------------------------------------------------
# async_get_energy_report
# ---------------------------------------------------------------------------


async def test_async_get_energy_report(hass):
    """The energy method returns parsed (ts, value) points per appliance."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    report = SimpleNamespace(
        ApplianceTelemetryData={
            "appliance-1": [
                {"timestamp": "2026-06-01T00:00:00Z", "value": 0.1},
                {"timestamp": "2026-06-01T01:00:00Z", "value": 0.2},
            ],
            "appliance-2": [],
        }
    )
    with patch.object(
        api._client,
        "get_tsi_energy_report",
        new=AsyncMock(return_value=report),
    ) as lib_call:
        result = await api.async_get_energy_report("hub-1")

    assert set(result) == {"t1", "t2"}
    assert result["t1"]["appliance-2"] == []
    assert result["t1"]["appliance-1"] == [
        (datetime(2026, 6, 1, tzinfo=UTC), 0.1),
        (datetime(2026, 6, 1, 1, tzinfo=UTC), 0.2),
    ]
    assert result["t2"]["appliance-1"] == []
    lib_call.assert_awaited_once()


async def test_async_get_energy_report_passes_window_to_library(hass):
    """The integration passes the configured days/interval to the library."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    report = SimpleNamespace(ApplianceTelemetryData={})
    with patch.object(
        api._client,
        "get_tsi_energy_report",
        new=AsyncMock(return_value=report),
    ) as lib_call:
        await api.async_get_energy_report("hub-1", days_back=7, interval="00:10:00")

    lib_call.assert_awaited_once_with(
        hub_id="hub-1",
        report_type=1,
        interval="00:10:00",
        days_back=7,
        include_previous_period=True,
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (DimplexAuthError("a"), InvalidAuth),
        (DimplexConnectionError("c"), CannotConnect),
    ],
)
async def test_async_get_energy_report_error_mapping(hass, exc, expected):
    """Auth/connection errors during energy fetch map to integration exceptions."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(side_effect=exc),
        ),
        pytest.raises(expected),
    ):
        await api.async_get_energy_report("hub-1")


async def test_async_get_energy_report_api_error_returns_empty(hass):
    """A DimplexApiError (e.g. 404/400 for hubs with no metered appliances) returns {} instead of raising."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with patch.object(
        api._client,
        "get_tsi_energy_report",
        new=AsyncMock(side_effect=DimplexApiError(404, "Not Found")),
    ):
        result = await api.async_get_energy_report("hub-1")
    assert result == {"t1": {}, "t2": {}}


async def test_control_helpers_delegate_to_library(hass):
    """Boost/away/target/OWD helpers wrap library methods."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(api._client, "set_boost", new=AsyncMock()) as set_boost,
        patch.object(api._client, "set_away", new=AsyncMock()) as set_away,
        patch.object(api._client, "set_target_temperature", new=AsyncMock()) as set_temp,
        patch.object(api._client, "set_open_window_detection", new=AsyncMock()) as set_owd,
    ):
        await api.async_set_boost("h", "a", temperature=24.0, duration_minutes=45, enable=True)
        await api.async_set_away("h", "a", temperature=16.0, enable=True)
        await api.async_set_target_temperature("h", "a", 21.0)
        await api.async_set_open_window_detection("h", "a", True)

    set_boost.assert_awaited_once()
    set_away.assert_awaited_once()
    set_temp.assert_awaited_once_with("h", "a", 21.0)
    set_owd.assert_awaited_once_with("h", ["a"], True)


async def test_setpoint_and_frost_helpers_use_the_dedicated_endpoints(hass):
    """The app's own setpoint / off endpoints are used, not the schedule editor."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(api._client, "set_appliance_setpoint_temperature", new=AsyncMock()) as set_point,
        patch.object(api._client, "set_frost_protect", new=AsyncMock()) as set_frost,
    ):
        await api.async_set_appliance_setpoint("h", "a", 21.5)
        await api.async_set_frost_protect("h", "a", enable=True)
        await api.async_set_frost_protect("h", "a", enable=False)

    set_point.assert_awaited_once_with("h", ["a"], 21.5)
    assert [call.kwargs["enable"] for call in set_frost.await_args_list] == [True, False]


@pytest.mark.parametrize(
    ("library_error", "expected"),
    [
        (DimplexApiError(403, "Forbidden"), ControlRejected),
        (DimplexApiError(405, "Method Not Allowed"), ControlRejected),
        (DimplexApiError(501, "Not Implemented"), ControlRejected),
        (DimplexConnectionError("offline"), CannotConnect),
        (DimplexAuthError("expired"), InvalidAuth),
    ],
)
async def test_control_errors_are_translated(hass, library_error, expected):
    """A refusal becomes ControlRejected; a transient failure stays CannotConnect."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(
            api._client,
            "set_appliance_setpoint_temperature",
            new=AsyncMock(side_effect=library_error),
        ),
        pytest.raises(expected),
    ):
        await api.async_set_appliance_setpoint("h", "a", 21.0)


@pytest.mark.parametrize("status", [500, 502, 503, 400, 404, 429])
async def test_transient_and_client_errors_are_not_control_rejections(hass, status):
    """Only 403/405/501 may unlock the destructive schedule-rewrite fallback (#197).

    A 5xx means the write did not get through, and 400/404 mean the payload or ids
    are wrong — none of which justify overwriting every timer period.
    """
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(
            api._client,
            "set_appliance_setpoint_temperature",
            new=AsyncMock(side_effect=DimplexApiError(status, "boom")),
        ),
        pytest.raises(CannotConnect) as caught,
    ):
        await api.async_set_appliance_setpoint("h", "a", 21.0)
    assert not isinstance(caught.value, ControlRejected)


async def test_control_rejected_carries_its_status(hass):
    """The status is kept so the log line can say what the cloud actually answered."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(
            api._client,
            "set_appliance_setpoint_temperature",
            new=AsyncMock(side_effect=DimplexApiError(403, "Forbidden")),
        ),
        pytest.raises(ControlRejected) as caught,
    ):
        await api.async_set_appliance_setpoint("h", "a", 21.0)
    assert caught.value.status == 403
    assert isinstance(caught.value, CannotConnect)


async def test_async_get_energy_for_hubs(hass):
    """Energy-for-hubs helper returns t1/t2 maps per hub."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    report = SimpleNamespace(ApplianceTelemetryData={"a-1": [{"TS": 1767225600, "T1": 1.5}]})
    with patch.object(api._client, "get_tsi_energy_report", new=AsyncMock(return_value=report)):
        data = await api.async_get_energy_for_hubs(["hub-1"])
    assert "hub-1" in data["energy"]
    assert data["energy"]["hub-1"]["t1"]["a-1"]


def test_energy_registers_parse_separately():
    """Dual-register points must not mix T2 kWh into the T1 series."""
    from dimplex_controller import VALUE_KEY_T2, parse_telemetry_points

    from custom_components.dimplex.api import _VALUE_KEY_T1

    points = [
        {"TS": 1767225600, "T1": 7.46, "T2": 0.36},
        {"TS": 1767312000, "T1": 8.02, "T2": 0.18},
        {"TS": 1767398400, "T2": 0.50},  # T2-only day must not appear in T1
    ]
    t1 = parse_telemetry_points(points, value_keys=_VALUE_KEY_T1)
    t2 = parse_telemetry_points(points, value_keys=VALUE_KEY_T2)
    assert [v for _, v in t1] == [7.46, 8.02]
    assert [v for _, v in t2] == [0.36, 0.18, 0.50]
    assert sum(v for _, v in t1) == 15.48
    assert sum(v for _, v in t2) == 1.04


async def test_advance_helper_delegates_to_library(hass):
    """Advance passes the optional target through; None lets the library pick 255."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with patch.object(api._client, "set_advance", new=AsyncMock()) as set_advance:
        await api.async_set_advance("h", "a")
        await api.async_set_advance("h", "a", enable=False, temperature=19.0)

    first, second = set_advance.await_args_list
    assert first.args == ("h", ["a"])
    assert first.kwargs == {"enable": True, "temperature": None}
    assert second.kwargs == {"enable": False, "temperature": 19.0}


async def test_product_catalogue_is_fetched_once_and_matched_to_rows(hass):
    """The catalogue is static per account, and joins a row to its product (#199)."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(ApplianceId="a-1", ApplianceModel="QM100RF", ApplianceType="Quantum")
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    product = SimpleNamespace(ProductModelName="QM100RF", ProductTypeName="Quantum")

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        patch.object(api._client, "get_hub_zones", new=AsyncMock(return_value=[zone])),
        patch.object(api._client, "get_appliance_overview", new=AsyncMock(return_value=[])),
        patch.object(api._client, "get_product_models", new=AsyncMock(return_value=[product])) as catalogue,
    ):
        first = await api.async_get_status_data()
        second = await api.async_get_status_data()

    assert first["appliances"][0]["product"] is product
    assert second["appliances"][0]["product"] is product
    catalogue.assert_awaited_once()


async def test_product_catalogue_failure_is_survivable_and_retried(hass):
    """A missing catalogue must not fail the poll, and must be retried later."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(ApplianceId="a-1", ApplianceModel="QM100RF", ApplianceType="Quantum")
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        patch.object(api._client, "get_hub_zones", new=AsyncMock(return_value=[zone])),
        patch.object(api._client, "get_appliance_overview", new=AsyncMock(return_value=[])),
        patch.object(
            api._client,
            "get_product_models",
            new=AsyncMock(side_effect=DimplexConnectionError("catalogue unavailable")),
        ) as catalogue,
    ):
        data = await api.async_get_status_data()

    assert data["appliances"][0]["product"] is None
    # Not cached, so the next poll tries again rather than degrading forever.
    assert catalogue.await_count == 1
    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        patch.object(api._client, "get_hub_zones", new=AsyncMock(return_value=[zone])),
        patch.object(api._client, "get_appliance_overview", new=AsyncMock(return_value=[])),
        patch.object(api._client, "get_product_models", new=AsyncMock(return_value=[])),
    ):
        await api.async_get_status_data()


async def test_schedule_write_helpers_delegate_to_library(hass):
    """Schedule writes pass through to the library with the cloud's own shapes."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    with (
        patch.object(api._client, "copy_schedule_to_appliances", new=AsyncMock()) as copy,
        patch.object(api._client, "set_period_setpoint", new=AsyncMock(return_value="settings")) as period,
    ):
        await api.async_copy_schedule("h", "a1", ["a2"], timer_mode=2)
        result = await api.async_set_period_setpoint("h", "a1", day_of_week=1, start_time="06:00:00", temperature=21.0)

    assert copy.await_args.args == ("h", "a1", ["a2"])
    assert copy.await_args.kwargs == {"timer_mode": 2}
    assert period.await_args.kwargs == {
        "day_of_week": 1,
        "start_time": "06:00:00",
        "temperature": 21.0,
        "end_time": None,
    }
    assert result == "settings"


async def test_set_period_setpoint_does_not_swallow_a_missing_period(hass):
    """The library signals "no such period" with ValueError; callers must see it.

    The adapter's error translation covers the cloud's failures, not the library's
    own argument checks — the services layer turns this one into a readable message.
    """
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    with (
        patch.object(
            api._client,
            "set_period_setpoint",
            new=AsyncMock(side_effect=ValueError("No timer period")),
        ),
        pytest.raises(ValueError, match="No timer period"),
    ):
        await api.async_set_period_setpoint("h", "a1", day_of_week=1, start_time="06:00:00", temperature=21.0)
