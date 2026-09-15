"""Tests for the climate platform."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.climate import (
    _is_away_active,
    _is_boost_active,
    _is_frost_protect_active,
    _is_timer_off_like,
    _timer_mode_from_schedule,
)
from custom_components.dimplex.const import (
    ADVANCE_FLAG,
    AWAY_FLAG,
    AWAY_TEMP_MAX,
    BOOST_FLAG,
    DOMAIN,
    FROST_FLAG,
    HEAT_DEMAND_FLAGS,
    TIMER_FROST,
    TIMER_OFF,
    has_any_mode,
    sane_temperature,
)

from .const import MOCK_ENTRY_DATA


def _payload(*, boost=False, away=False, eco=False, frost=False, room=21.5, target=20, timer_mode=1):
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
        FirmwareVersion="6",
        SeriesIdentifier="G12",
    )
    status = SimpleNamespace(
        EcoStartEnabled=eco,
        ComfortStatus=True,
        RoomTemperature=room,
        ActiveSetPointTemperature=target,
        NormalTemperature=target,
        BoostTemperature=25.0,
        AwayTemperature=15.0,
        BoostDuration=30 if boost else 0,
        AwayDateTime="2026-07-01T00:00:00" if away else None,
        ApplianceModes=((BOOST_FLAG if boost else 0) | (AWAY_FLAG if away else 0) | (FROST_FLAG if frost else 0)),
        OpenWindowEnabled=False,
        SetbackEnabled=False,
    )
    schedule = SimpleNamespace(TimerMode=timer_mode, TimerPeriods=[], ApplianceId="appliance-1")
    return {
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}],
        "hubs": [hub],
        "schedules": {"appliance-1": schedule},
    }


def _climate_entity(hass):
    for state in hass.states.async_all():
        if state.entity_id.startswith("climate."):
            return state.entity_id
    return None


@contextmanager
def _api_data(payload):
    schedules = payload.get("schedules") or {}
    schedule = schedules.get("appliance-1") or SimpleNamespace(TimerMode=1, TimerPeriods=[], ApplianceId="appliance-1")
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_schedule",
            new_callable=AsyncMock,
            return_value=schedule,
        ),
    ):
        yield


def test_flag_values_match_the_library():
    """Guard against regressing to the pre-0.13.0 bit assumptions."""
    assert BOOST_FLAG == 2  # 16 is Advance
    assert AWAY_FLAG == 4  # 32 is FrostProtect


def test_boost_and_away_helpers():
    """Helper detection works for raw status namespaces and flag bits."""
    assert _is_boost_active(None) is False
    assert _is_away_active(None) is False

    # No ApplianceModes reported at all: fall back to the duration / date.
    boost = SimpleNamespace(BoostDuration=10, AwayDateTime=None)
    assert _is_boost_active(boost) is True

    away = SimpleNamespace(BoostDuration=0, AwayDateTime="2026-01-01T00:00:00")
    assert _is_away_active(away) is True

    flags = SimpleNamespace(BoostDuration=0, ApplianceModes=BOOST_FLAG | AWAY_FLAG, AwayDateTime=None)
    assert _is_boost_active(flags) is True
    assert _is_away_active(flags) is True

    # Advance (16) and FrostProtect (32) are not Boost/Away — the #163 bug.
    wrong = SimpleNamespace(BoostDuration=0, ApplianceModes=16 | 32, AwayDateTime=None)
    assert _is_boost_active(wrong) is False
    assert _is_away_active(wrong) is False

    # The mode bit wins over a stale duration / away-until date.
    stale = SimpleNamespace(BoostDuration=30, ApplianceModes=0, AwayDateTime="2026-01-01T00:00:00")
    assert _is_boost_active(stale) is False
    assert _is_away_active(stale) is False

    off = SimpleNamespace(BoostDuration=0, ApplianceModes=0, AwayDateTime="")
    assert _is_boost_active(off) is False
    assert _is_away_active(off) is False


def test_timer_mode_helpers():
    """Frost protection and off timer modes map to HVAC off-like."""
    assert _timer_mode_from_schedule(None) is None
    assert _timer_mode_from_schedule(SimpleNamespace(TimerMode=2)) == 2
    assert _is_timer_off_like(TIMER_FROST) is True
    assert _is_timer_off_like(TIMER_OFF) is True
    assert _is_timer_off_like(0) is False
    assert _is_timer_off_like(1) is False


@pytest.mark.asyncio
async def test_climate_set_temperature_and_presets(hass):
    """Climate services call the API adapter for temperature and presets."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload()

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("current_temperature") == 21.5
    assert state.attributes.get("temperature") == 20
    assert state.attributes.get("preset_mode") == "comfort"

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_appliance_setpoint",
            new_callable=AsyncMock,
        ) as set_temp,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_target_temperature",
            new_callable=AsyncMock,
        ) as rewrite_schedule,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 22.5},
            blocking=True,
        )
        set_temp.assert_awaited_once_with("hub-1", "appliance-1", 22.5)
        # The destructive schedule rewrite is only a fallback.
        rewrite_schedule.assert_not_awaited()

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_boost",
            new_callable=AsyncMock,
        ) as set_boost,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "boost"},
            blocking=True,
        )
        assert set_boost.await_count == 1
        assert set_boost.await_args.kwargs["enable"] is True
        assert set_boost.await_args.kwargs["temperature"] == 25.0

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "away"},
            blocking=True,
        )
        assert set_away.await_count == 1
        assert set_away.await_args.kwargs["enable"] is True

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_eco_start",
            new_callable=AsyncMock,
        ) as set_eco,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "eco"},
            blocking=True,
        )
        set_eco.assert_awaited_once_with("hub-1", "appliance-1", True)


@pytest.mark.asyncio
async def test_climate_comfort_clears_modes(hass):
    """Comfort preset clears boost, away, and eco when active."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(boost=True, away=True, eco=True)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.attributes.get("preset_mode") == "boost"

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_boost",
            new_callable=AsyncMock,
        ) as set_boost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_eco_start",
            new_callable=AsyncMock,
        ) as set_eco,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "comfort"},
            blocking=True,
        )
        assert set_boost.await_count == 1
        assert set_boost.await_args.kwargs["enable"] is False
        assert set_away.await_count == 1
        assert set_away.await_args.kwargs["enable"] is False
        set_eco.assert_awaited_once_with("hub-1", "appliance-1", False)


@pytest.mark.asyncio
async def test_climate_turn_off_clears_boost_and_away(hass):
    """Turning climate off clears boost/away and engages frost protection."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(boost=True, away=True)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_boost",
            new_callable=AsyncMock,
        ) as set_boost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_frost_protect",
            new_callable=AsyncMock,
        ) as set_frost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_timer_mode",
            new_callable=AsyncMock,
        ) as set_timer,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        assert set_boost.await_count == 1
        assert set_away.await_count == 1
        set_frost.assert_awaited_once_with("hub-1", "appliance-1", enable=True)
        # No schedule write — SetTimerMode is what Quantum answers with 403.
        set_timer.assert_not_awaited()


@pytest.mark.asyncio
async def test_climate_frost_timer_reports_hvac_off(hass):
    """Frost protection timer mode surfaces as HVAC off (issue #149)."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    # Away flag still present must not keep HVAC in heat when timer is frost.
    payload = _payload(away=True, timer_mode=2)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"
    assert state.attributes.get("hvac_action") == "off"
    assert state.attributes.get("preset_mode") is None


@pytest.mark.asyncio
async def test_climate_manual_timer_reports_heat(hass):
    """Manual/user timer modes report HVAC heat when status is present."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(timer_mode=1)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "heat"


def test_sane_temperature_drops_sentinel():
    """0xFF (255) sentinel and junk map to None; real values pass through unchanged."""
    assert sane_temperature(255) is None
    assert sane_temperature(255.0) is None
    assert sane_temperature(300) is None
    assert sane_temperature("255") is None
    assert sane_temperature(None) is None
    assert sane_temperature("") is None
    assert sane_temperature("nan-ish") is None
    # Valid readings are returned as float.
    assert sane_temperature(21.5) == 21.5
    assert sane_temperature(7) == 7.0
    assert sane_temperature("20") == 20.0


def test_has_any_mode():
    """Mode-bit helper tolerates missing / unparseable ApplianceModes."""
    assert has_any_mode(SimpleNamespace(ApplianceModes=BOOST_FLAG), HEAT_DEMAND_FLAGS) is True
    assert has_any_mode(SimpleNamespace(ApplianceModes=ADVANCE_FLAG), HEAT_DEMAND_FLAGS) is True
    assert has_any_mode(SimpleNamespace(ApplianceModes=AWAY_FLAG), HEAT_DEMAND_FLAGS) is False
    assert has_any_mode(SimpleNamespace(ApplianceModes=None), HEAT_DEMAND_FLAGS) is False
    assert has_any_mode(SimpleNamespace(ApplianceModes="junk"), HEAT_DEMAND_FLAGS) is False
    assert has_any_mode(SimpleNamespace(), HEAT_DEMAND_FLAGS) is False
    assert has_any_mode(None, HEAT_DEMAND_FLAGS) is False
    assert has_any_mode(SimpleNamespace(ApplianceModes=BOOST_FLAG), 0) is False


@pytest.mark.asyncio
async def test_climate_target_temperature_ignores_sentinel(hass):
    """A 255 ActiveSetPointTemperature must not surface as a 255 °C target (issue: sentinel)."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    # Mirror the live QM100RF idle/EcoStart reading: active setpoint 255, no normal temp.
    payload = _payload(eco=True, target=255)
    payload["appliances"][0]["status"].NormalTemperature = None

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("temperature") is None

    # The target-temperature sensor must also drop the sentinel.
    sensor_state = None
    for candidate in hass.states.async_all():
        if candidate.entity_id.startswith("sensor.") and "target_temperature" in candidate.entity_id:
            sensor_state = candidate
            break
    assert sensor_state is not None
    assert sensor_state.state in ("unknown", "unavailable")


@pytest.mark.asyncio
async def test_climate_target_temperature_falls_back_past_sentinel(hass):
    """When the active setpoint is the sentinel, fall back to a real normal temp."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(timer_mode=1, target=20)
    payload["appliances"][0]["status"].ActiveSetPointTemperature = 255

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("temperature") == 20


@pytest.mark.asyncio
async def test_climate_control_error_surfaces_homeassistant_error(hass):
    """A rejected control call (e.g. Quantum 403) becomes a clean error, not a 500 (#149)."""
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex.api import CannotConnect

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(timer_mode=1)  # heat, no boost/away -> turn off goes straight to frost protect

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_frost_protect",
            new_callable=AsyncMock,
            side_effect=CannotConnect("403"),
        ),
        _api_data(payload),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )


def test_frost_protect_helper():
    """Frost protection is read from the mode bit, not the timer mode."""
    assert _is_frost_protect_active(None) is False
    assert _is_frost_protect_active(SimpleNamespace(ApplianceModes=FROST_FLAG)) is True
    assert _is_frost_protect_active(SimpleNamespace(ApplianceModes=BOOST_FLAG)) is False
    assert _is_frost_protect_active(SimpleNamespace(ApplianceModes=None)) is False
    assert _is_frost_protect_active(SimpleNamespace()) is False


@pytest.mark.asyncio
async def test_climate_frost_mode_bit_reports_hvac_off(hass):
    """The FrostProtect mode bit alone means off, with no schedule read needed."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    # Timer mode is a normal user timer — only the mode bit says "off".
    payload = _payload(frost=True, timer_mode=1)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "off"
    assert state.attributes.get("hvac_action") == "off"
    assert state.attributes.get("preset_mode") is None


@pytest.mark.asyncio
async def test_climate_turn_on_clears_frost_protection(hass):
    """Turning on clears the frost mode rather than only rewriting the schedule."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(frost=True, timer_mode=1)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_frost_protect",
            new_callable=AsyncMock,
        ) as set_frost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_timer_mode",
            new_callable=AsyncMock,
        ) as set_timer,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        set_frost.assert_awaited_once_with("hub-1", "appliance-1", enable=False)
        set_timer.assert_not_awaited()


@pytest.mark.asyncio
async def test_climate_turn_on_restores_legacy_frost_timer_mode(hass):
    """Appliances parked in the frost/off timer mode by older releases recover."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(timer_mode=TIMER_FROST)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_frost_protect",
            new_callable=AsyncMock,
        ) as set_frost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_timer_mode",
            new_callable=AsyncMock,
        ) as set_timer,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        # Mode bit is clear, so only the legacy schedule needs restoring.
        set_frost.assert_not_awaited()
        set_timer.assert_awaited_once_with("hub-1", "appliance-1", 0)


@pytest.mark.asyncio
async def test_climate_set_temperature_falls_back_to_schedule_rewrite(hass):
    """An appliance that *refuses* the dedicated setpoint still gets its target."""
    from custom_components.dimplex.api import ControlRejected

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload()

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_appliance_setpoint",
            new_callable=AsyncMock,
            side_effect=ControlRejected("Forbidden", status=403),
        ) as set_point,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_target_temperature",
            new_callable=AsyncMock,
        ) as rewrite_schedule,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 19.0},
            blocking=True,
        )
        set_point.assert_awaited_once()
        rewrite_schedule.assert_awaited_once_with("hub-1", "appliance-1", 19.0)


@pytest.mark.asyncio
async def test_climate_set_temperature_does_not_rewrite_schedule_on_transient_error(hass):
    """A timeout or 5xx must never trigger the destructive schedule rewrite (#197).

    ``async_set_target_temperature`` overwrites *every* period of the appliance's
    timer schedule. Before #197 it ran for any ``CannotConnect``, so a single dropped
    connection while nudging the target destroyed the user's schedule silently.
    """
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex.api import CannotConnect

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload()

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_appliance_setpoint",
            new_callable=AsyncMock,
            side_effect=CannotConnect("timed out"),
        ) as set_point,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_target_temperature",
            new_callable=AsyncMock,
        ) as rewrite_schedule,
        _api_data(payload),
        pytest.raises(HomeAssistantError, match="Could not reach the Dimplex cloud"),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 19.0},
            blocking=True,
        )

    set_point.assert_awaited_once()
    rewrite_schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_climate_temperature_limits_come_from_capabilities(hass):
    """min/max temp follow the cloud's own 7-30 °C range, not a hard-coded 5.0."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload()

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("min_temp") == 7.0
    assert state.attributes.get("max_temp") == 30.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_kwargs", "preset", "expect_boost_enable", "expect_away_enable", "expect_eco"),
    [
        # away -> eco: the reported no-op. Away must be cleared, EcoStart enabled.
        ({"away": True}, "eco", None, False, True),
        # away -> boost
        ({"away": True}, "boost", True, False, None),
        # boost -> away
        ({"boost": True}, "boost_to_away", None, None, None),
        # eco -> boost: EcoStart must be turned off, not left on underneath.
        ({"eco": True}, "boost", True, None, False),
    ],
)
async def test_preset_switch_clears_the_previous_preset(
    hass, payload_kwargs, preset, expect_boost_enable, expect_away_enable, expect_eco
):
    """Selecting a preset establishes it outright rather than layering onto the last (#173)."""
    if preset == "boost_to_away":
        preset = "away"
        expect_boost_enable, expect_away_enable = False, True

    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(**payload_kwargs)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_boost",
            new_callable=AsyncMock,
        ) as set_boost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_eco_start",
            new_callable=AsyncMock,
        ) as set_eco,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: preset},
            blocking=True,
        )

    for mock, expected, name in (
        (set_boost, expect_boost_enable, "boost"),
        (set_away, expect_away_enable, "away"),
    ):
        if expected is None:
            assert mock.await_count == 0, f"{name} should not have been written"
        else:
            assert mock.await_count == 1, f"{name} should have been written once"
            assert mock.await_args.kwargs["enable"] is expected

    if expect_eco is None:
        assert set_eco.await_count == 0
    else:
        set_eco.assert_awaited_once_with("hub-1", "appliance-1", expect_eco)


@pytest.mark.asyncio
async def test_away_preset_clamps_to_the_away_ceiling(hass):
    """The away preset must not replay an out-of-range AwayTemperature (#174)."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload()
    # An appliance reporting an Away target above the ceiling — the cloud would
    # reduce it silently, so send what will actually be applied.
    payload["appliances"][0]["status"].AwayTemperature = 25.0

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "away"},
            blocking=True,
        )

    assert set_away.await_args.kwargs["temperature"] == AWAY_TEMP_MAX == 18.0
