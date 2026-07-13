"""Tests for adaptive energy poll interval and estimated power helper."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dimplex import DimplexEnergyCoordinator
from custom_components.dimplex.__init__ import _interval_from_options
from custom_components.dimplex.api import CannotConnect
from custom_components.dimplex.const import DEFAULT_ENERGY_BACKOFF_INTERVAL, ENERGY_EMPTY_BACKOFF_THRESHOLD
from custom_components.dimplex.sensor import _estimated_power_kw


def test_estimated_power_zero_when_idle():
    prov = SimpleNamespace(rated_power=2.0)
    appliance = SimpleNamespace(automatic_provisioning=prov)
    status = SimpleNamespace(ComfortStatus=False, ApplianceModes=0, BoostDuration=0)
    assert _estimated_power_kw(status, appliance) == 0.0


def test_estimated_power_rated_when_heating():
    prov = SimpleNamespace(rated_power=2.5)
    appliance = SimpleNamespace(automatic_provisioning=prov)
    status = SimpleNamespace(ComfortStatus=True, ApplianceModes=0, BoostDuration=0)
    assert _estimated_power_kw(status, appliance) == 2.5


def test_estimated_power_none_without_rated():
    appliance = SimpleNamespace(automatic_provisioning=None)
    status = SimpleNamespace(ComfortStatus=True, ApplianceModes=0, BoostDuration=0)
    assert _estimated_power_kw(status, appliance) is None


def test_energy_empty_detection():
    assert DimplexEnergyCoordinator._energy_is_empty({"energy": {}}) is True
    assert DimplexEnergyCoordinator._energy_is_empty({"energy": {"h1": {"t1": {"a1": []}, "t2": {}}}}) is True
    assert (
        DimplexEnergyCoordinator._energy_is_empty({"energy": {"h1": {"t1": {"a1": [(None, 1.0)]}, "t2": {}}}}) is False
    )


def test_adapt_interval_backs_off_after_threshold():
    coord = object.__new__(DimplexEnergyCoordinator)
    coord._base_interval = timedelta(minutes=30)
    coord._empty_polls = 0
    coord.update_interval = timedelta(minutes=30)
    coord._status = MagicMock(data={"appliances": []})

    empty = {"energy": {"h1": {"t1": {}, "t2": {}}}}
    for _ in range(ENERGY_EMPTY_BACKOFF_THRESHOLD):
        coord._adapt_interval(empty)  # type: ignore[attr-defined]

    assert coord.update_interval == max(timedelta(minutes=30), DEFAULT_ENERGY_BACKOFF_INTERVAL)
    assert coord._empty_polls >= ENERGY_EMPTY_BACKOFF_THRESHOLD

    # Recover when points return
    coord._adapt_interval({"energy": {"h1": {"t1": {"a1": [(None, 1.0)]}, "t2": {}}}})  # type: ignore[attr-defined]
    assert coord._empty_polls == 0
    assert coord.update_interval == timedelta(minutes=30)


def test_any_heating_active_comfort():
    coord = object.__new__(DimplexEnergyCoordinator)
    status = SimpleNamespace(ComfortStatus=True, ApplianceModes=0, BoostDuration=0)
    coord._status = MagicMock(data={"appliances": [{"status": status}]})
    assert coord._any_heating_active() is True


def test_any_heating_active_boost():
    coord = object.__new__(DimplexEnergyCoordinator)
    status = SimpleNamespace(ComfortStatus=False, ApplianceModes=0, BoostDuration=60)
    coord._status = MagicMock(data={"appliances": [{"status": status}]})
    assert coord._any_heating_active() is True


def test_any_heating_active_manual():
    coord = object.__new__(DimplexEnergyCoordinator)
    status = SimpleNamespace(ComfortStatus=False, ApplianceModes=16, BoostDuration=0)
    coord._status = MagicMock(data={"appliances": [{"status": status}]})
    assert coord._any_heating_active() is True


def test_any_heating_active_inactive():
    coord = object.__new__(DimplexEnergyCoordinator)
    status = SimpleNamespace(ComfortStatus=False, ApplianceModes=0, BoostDuration=0)
    coord._status = MagicMock(data={"appliances": [{"status": status}]})
    assert coord._any_heating_active() is False


def test_any_heating_active_none_status():
    coord = object.__new__(DimplexEnergyCoordinator)
    coord._status = MagicMock(data={"appliances": [{"status": None}]})
    assert coord._any_heating_active() is False


def test_adapt_interval_heating_resets_polls():
    coord = object.__new__(DimplexEnergyCoordinator)
    coord._base_interval = timedelta(minutes=30)
    coord._empty_polls = 5
    coord.update_interval = timedelta(hours=3)
    status = SimpleNamespace(ComfortStatus=True, ApplianceModes=0, BoostDuration=0)
    coord._status = MagicMock(data={"appliances": [{"status": status}]})
    coord._adapt_interval({"energy": {"h1": {"t1": {}, "t2": {}}}})  # type: ignore[attr-defined]
    assert coord._empty_polls == 0
    assert coord.update_interval == timedelta(minutes=30)


def test_adapt_interval_noop_when_already_at_target():
    coord = object.__new__(DimplexEnergyCoordinator)
    coord._base_interval = timedelta(minutes=30)
    coord._empty_polls = 0
    coord.update_interval = timedelta(minutes=30)
    coord._status = MagicMock(data={"appliances": []})
    coord._adapt_interval({"energy": {"h1": {"t1": {}, "t2": {}}}})  # type: ignore[attr-defined]
    assert coord._empty_polls == 1
    assert coord.update_interval == timedelta(minutes=30)


def test_interval_from_options_valid():
    assert _interval_from_options({"k": "300"}, "k", timedelta(seconds=30)) == timedelta(seconds=300)


def test_interval_from_options_below_minimum():
    assert _interval_from_options({"k": "5"}, "k", timedelta(seconds=30)) == timedelta(seconds=30)


def test_interval_from_options_invalid_value():
    assert _interval_from_options({"k": "abc"}, "k", timedelta(seconds=30)) == timedelta(seconds=30)


def test_interval_from_options_type_error():
    assert _interval_from_options({"k": [1, 2, 3]}, "k", timedelta(seconds=30)) == timedelta(seconds=30)


async def test_energy_update_data_cannot_connect():
    coord = object.__new__(DimplexEnergyCoordinator)
    coord._status = MagicMock()
    coord._status.data = {"hubs": [SimpleNamespace(HubId="h1")]}
    coord.api = MagicMock()
    coord.api.async_get_energy_for_hubs = AsyncMock(side_effect=CannotConnect)

    with pytest.raises(UpdateFailed, match="Cannot connect"):
        await coord._async_update_data()


async def test_energy_update_data_generic_error():
    coord = object.__new__(DimplexEnergyCoordinator)
    coord._status = MagicMock()
    coord._status.data = {"hubs": [SimpleNamespace(HubId="h1")]}
    coord.api = MagicMock()
    coord.api.async_get_energy_for_hubs = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
