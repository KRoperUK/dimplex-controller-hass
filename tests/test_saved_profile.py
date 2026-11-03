"""Saved heating profiles: period matching and coordinator cache (#336)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex import DimplexStatusCoordinator
from custom_components.dimplex.const import (
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    TIMER_USER,
    matching_saved_profile,
    schedule_slot,
)

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


def _make_coordinator(hass, api):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    entry.add_to_hass(hass)
    return DimplexStatusCoordinator(hass, entry, api, DEFAULT_STATUS_INTERVAL)


async def test_heating_profiles_cached_between_polls(hass):
    """Profiles ride the slow cadence — fetched once, then reused."""
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
