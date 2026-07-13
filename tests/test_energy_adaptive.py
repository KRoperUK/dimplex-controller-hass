"""Tests for adaptive energy poll interval and estimated power helper."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.dimplex import DimplexEnergyCoordinator
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
