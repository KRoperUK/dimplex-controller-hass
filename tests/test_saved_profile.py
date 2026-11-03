"""Saved heating profiles: period matching, coordinator cache, picker (#336)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.select import SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex import DimplexStatusCoordinator
from custom_components.dimplex.const import (
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    TIMER_USER,
    matching_saved_profile,
    schedule_slot,
)
from custom_components.dimplex.select import DimplexSavedProfileSelect
from custom_components.dimplex.sensor import DimplexSavedProfileSensor

from .const import MOCK_ENTRY_DATA


def _period(day=1, start="06:00:00", end="09:00:00", temperature=21.0):
    return SimpleNamespace(DayOfWeek=day, StartTime=start, EndTime=end, Temperature=temperature)


def _profile(name, profile_id, periods):
    return SimpleNamespace(Id=profile_id, ProfileName=name, UserHeatingProfilePeriods=list(periods))


def _winter():
    return _profile("Winter", "prof-winter", [_period(), _period(day=2)])


def _summer():
    return _profile("Summer", "prof-summer", [_period(start="07:00:00", temperature=18)])


def _schedule(periods, timer_mode=0):
    return SimpleNamespace(TimerMode=timer_mode, TimerPeriods=list(periods))


def _status():
    return SimpleNamespace(
        EcoStartEnabled=False,
        ComfortStatus=True,
        RoomTemperature=21.5,
        ActiveSetPointTemperature=20,
        OpenWindowEnabled=False,
        ApplianceModes=1,
        StatusTwo=0,
    )


def _payload(status=None):
    hub = SimpleNamespace(HubId="hub-1", FriendlyName="Hub")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
    )
    return {
        "appliances": [
            {
                "hub": hub,
                "zone": SimpleNamespace(ZoneName="Living Room"),
                "appliance": appliance,
                "status": status or _status(),
            }
        ]
    }


def test_matching_saved_profile_exact_match():
    """Identical period sets match, ignoring int/float temperature shape."""
    schedule = _schedule([_period(temperature=21.0), _period(day=2, temperature=21.0)])
    assert matching_saved_profile(schedule, [_summer(), _winter()]) == "Winter"


def test_matching_saved_profile_returns_none_when_edited():
    """A timer edited since applying matches nothing — unknown, not stale."""
    schedule = _schedule([_period(temperature=22.0), _period(day=2)])
    assert matching_saved_profile(schedule, [_winter()]) is None


def test_matching_saved_profile_ignores_bad_rows():
    """Malformed periods and nameless profiles never match."""
    schedule = _schedule([_period()])
    bad_periods = [SimpleNamespace(DayOfWeek=1)]
    profiles = [
        SimpleNamespace(Id="x", ProfileName="", UserHeatingProfilePeriods=[_period()]),
        SimpleNamespace(Id="y", ProfileName="Bad", UserHeatingProfilePeriods=bad_periods),
    ]
    assert matching_saved_profile(schedule, profiles) is None
    assert matching_saved_profile(None, [_winter()]) is None
    assert matching_saved_profile(_schedule([]), [_winter()]) is None
    assert matching_saved_profile(_schedule([_period()]), []) is None


def test_schedule_slot_prefers_the_cached_echo():
    """The fetch echo wins; the overview is the fallback; user timer is last."""
    assert schedule_slot(_schedule([_period()], timer_mode=2), _status()) == 2
    assert schedule_slot(None, _status()) == 0
    assert schedule_slot(_schedule([_period()], timer_mode="bogus"), _status()) == 0
    assert schedule_slot(None, None) == TIMER_USER


def _coordinator_payload(profiles):
    payload = _payload()
    payload["schedules"] = {"appliance-1": _schedule([_period(), _period(day=2)])}
    payload["heating_profiles"] = profiles
    return payload


def _direct_select(profiles, schedule=None, status=None):
    api = SimpleNamespace(async_apply_heating_profile=AsyncMock())
    data = _payload(status=status)
    data["schedules"] = {"appliance-1": schedule}
    data["heating_profiles"] = profiles
    coordinator = SimpleNamespace(
        data=data,
        last_update_success=True,
        async_request_refresh=AsyncMock(),
        invalidate_schedules=MagicMock(),
    )
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    select = DimplexSavedProfileSelect(coordinator, config_entry, data["appliances"][0], api)
    return select, api, coordinator


async def test_select_options_and_current_option_from_cache():
    """Options are the cached profile names; current is the period match."""
    select, _, _ = _direct_select([_summer(), _winter()], _schedule([_period(), _period(day=2)]))

    assert select.options == ["Summer", "Winter"]
    assert select.current_option == "Winter"
    assert select.available is True


async def test_select_current_option_unknown_when_custom():
    """An edited timer reads unknown rather than a stale profile name."""
    select, _, _ = _direct_select([_winter()], _schedule([_period(temperature=19.0)]))

    assert select.current_option is None


async def test_select_unavailable_without_profiles():
    """No cached profiles means nothing to pick — unavailable, not empty."""
    select, _, _ = _direct_select([], _schedule([_period()]))

    assert select.options == []
    assert select.available is False


async def test_select_applies_to_the_active_slot():
    """Choosing applies the profile id to the slot the schedule echo names."""
    select, api, coordinator = _direct_select([_winter()], _schedule([_period(), _period(day=2)], timer_mode=2))

    await select.async_select_option("Winter")

    api.async_apply_heating_profile.assert_awaited_once_with(
        "hub-1", "appliance-1", profile=2, profile_id="prof-winter"
    )
    coordinator.invalidate_schedules.assert_called_once()
    coordinator.async_request_refresh.assert_awaited_once()


async def test_select_falls_back_to_status_slot_without_schedule():
    """Without a cached schedule the overview's active profile names the slot."""
    status = _status()
    status.StatusTwo = 2
    select, api, _ = _direct_select([_winter()], None, status=status)

    await select.async_select_option("Winter")

    api.async_apply_heating_profile.assert_awaited_once_with(
        "hub-1", "appliance-1", profile=2, profile_id="prof-winter"
    )


async def test_select_rejects_unknown_profile():
    """An option outside the cached list raises and writes nothing."""
    select, api, _ = _direct_select([_winter()], _schedule([_period()]))

    with pytest.raises(ValueError, match="not a saved heating profile"):
        await select.async_select_option("Autumn")
    api.async_apply_heating_profile.assert_not_awaited()


async def test_sensor_reports_the_match():
    """The sensor names the matching profile and lists the available ones."""
    data = _coordinator_payload([_summer(), _winter()])
    coordinator = SimpleNamespace(data=data, last_update_success=True)
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    sensor = DimplexSavedProfileSensor(coordinator, config_entry, data["appliances"][0])

    assert sensor.available is True
    assert sensor.native_value == "Winter"
    assert sensor.extra_state_attributes == {"profiles": ["Summer", "Winter"]}


async def test_sensor_unknown_when_custom_or_unscheduled():
    """An edited timer, or no cached schedule, reads unknown."""
    data = _coordinator_payload([_winter()])
    data["schedules"] = {"appliance-1": _schedule([_period(temperature=19.0)])}
    coordinator = SimpleNamespace(data=data, last_update_success=True)
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    assert DimplexSavedProfileSensor(coordinator, config_entry, data["appliances"][0]).native_value is None

    data["schedules"] = {"appliance-1": None}
    sensor = DimplexSavedProfileSensor(coordinator, config_entry, data["appliances"][0])
    assert sensor.available is False
    assert sensor.native_value is None


def _setup_payload():
    payload = _payload()
    payload["hubs"] = [payload["appliances"][0]["hub"]]
    return payload


def _api_patches(payload, profiles):
    return (
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
            return_value=_schedule([_period(), _period(day=2)]),
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_heating_profiles",
            return_value=profiles,
        ),
    )


async def _setup(hass, payload, profiles):
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    with ExitStack() as stack:
        for patcher in _api_patches(payload, profiles):
            stack.enter_context(patcher)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


def _entity_id(hass, domain, needle):
    for state in hass.states.async_all():
        if state.entity_id.startswith(f"{domain}.") and needle in state.entity_id:
            return state.entity_id
    return None


async def test_setup_exposes_picker_and_readback(hass):
    """A heater with saved profiles gets the select and the sensor (#336)."""
    await _setup(hass, _setup_payload(), [_summer(), _winter()])

    select_id = _entity_id(hass, "select", "saved_profile")
    assert select_id is not None
    state = hass.states.get(select_id)
    assert state.attributes.get("options") == ["Summer", "Winter"]
    assert state.state == "Winter"

    sensor_id = _entity_id(hass, "sensor", "saved_profile")
    assert sensor_id is not None
    assert hass.states.get(sensor_id).state == "Winter"


async def test_setup_without_profiles_leaves_picker_unavailable(hass):
    """With no saved profiles the picker is unavailable but the sensor reads unknown."""
    await _setup(hass, _setup_payload(), [])

    select_id = _entity_id(hass, "select", "saved_profile")
    assert select_id is not None
    assert hass.states.get(select_id).state == "unavailable"

    sensor_id = _entity_id(hass, "sensor", "saved_profile")
    assert sensor_id is not None
    assert hass.states.get(sensor_id).state == "unknown"


def _make_coordinator(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    entry.add_to_hass(hass)
    return DimplexStatusCoordinator(hass, entry, api, DEFAULT_STATUS_INTERVAL)


async def test_heating_profiles_cached_between_polls(hass):
    """Profiles ride the slow cadence — fetched once, then reused."""
    from unittest.mock import AsyncMock

    api = AsyncMock()
    api.async_get_status_data.return_value = {"hubs": [], "appliances": []}
    api.async_get_heating_profiles.return_value = [_winter()]
    api.token_data = {}

    coordinator = _make_coordinator(hass, api)
    first = await coordinator._async_update_data()  # noqa: SLF001

    assert [profile.ProfileName for profile in first["heating_profiles"]] == ["Winter"]

    second = await coordinator._async_update_data()  # noqa: SLF001
    assert api.async_get_heating_profiles.await_count == 1
    assert second["heating_profiles"] is first["heating_profiles"]


async def test_heating_profile_fetch_failure_keeps_previous(hass):
    """A failed GetProfiles keeps the previous list instead of wiping options."""
    from unittest.mock import AsyncMock

    api = AsyncMock()
    api.async_get_status_data.return_value = {"hubs": [], "appliances": []}
    api.async_get_heating_profiles.return_value = [_winter()]
    api.token_data = {}

    coordinator = _make_coordinator(hass, api)
    first = await coordinator._async_update_data()  # noqa: SLF001
    assert len(first["heating_profiles"]) == 1

    api.async_get_heating_profiles.side_effect = RuntimeError("boom")
    coordinator._schedules_fetched_at -= 10**9  # noqa: SLF001
    second = await coordinator._async_update_data()  # noqa: SLF001

    assert [profile.ProfileName for profile in second["heating_profiles"]] == ["Winter"]


async def test_setup_applies_through_the_service(hass):
    """Picking a profile through Home Assistant reaches the cloud write."""
    payload = _setup_payload()
    with patch(
        "custom_components.dimplex.DimplexApiClient.async_apply_heating_profile",
        return_value=None,
    ) as apply:
        with ExitStack() as stack:
            for patcher in _api_patches(payload, [_winter()]):
                stack.enter_context(patcher)
            config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
            config_entry.add_to_hass(hass)
            assert await hass.config_entries.async_setup(config_entry.entry_id)
            await hass.async_block_till_done()

        select_id = _entity_id(hass, "select", "saved_profile")
        await hass.services.async_call(
            SELECT_DOMAIN,
            SERVICE_SELECT_OPTION,
            {ATTR_ENTITY_ID: select_id, "option": "Winter"},
            blocking=True,
        )

    apply.assert_awaited_once_with("hub-1", "appliance-1", profile=0, profile_id="prof-winter")
