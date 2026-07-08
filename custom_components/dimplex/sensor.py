"""Sensor platform for dimplex_controller."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature

from .const import DOMAIN, ENERGY_REPORT_DAYS, ENERGY_REPORT_INTERVAL
from .entity import DimplexEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices: list[SensorEntity] = [
        DimplexRoomTemperatureSensor(coordinator, entry, appliance_row)
        for appliance_row in coordinator.data.get("appliances", [])
    ]
    devices.extend(
        DimplexEnergySensor(coordinator, entry, appliance_row)
        for appliance_row in coordinator.data.get("appliances", [])
    )
    async_add_devices(devices)


class DimplexRoomTemperatureSensor(DimplexEntity, SensorEntity):
    """Room temperature sensor for an appliance."""

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._appliance.FriendlyName} Room Temperature"

    @property
    def native_value(self):
        """Return the room temperature."""
        status = self._status
        return status.RoomTemperature if status else None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return SensorDeviceClass.TEMPERATURE


class DimplexEnergySensor(DimplexEntity, SensorEntity):
    """Cumulative kWh energy used by an appliance over the report window.

    The cloud returns energy telemetry for a rolling
    :data:`~custom_components.dimplex.const.ENERGY_REPORT_DAYS`-day window
    (configurable on the client). This sensor sums every value the cloud
    returned in that window and exposes it as a ``TOTAL`` value with
    ``last_reset`` set to the start of the query window, so the Home
    Assistant Energy Dashboard can plot it. The dashboard subtracts
    ``last_reset`` snapshots, so a rolling window is the natural fit.

    Hardware-dependent: only QRAD / metered appliances report data. When
    the hub returns no data, the sensor is unavailable rather than ``0``,
    so the Energy Dashboard never sees fabricated zero readings.
    """

    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator, config_entry, appliance_row) -> None:
        super().__init__(coordinator, config_entry, appliance_row)
        # Pre-compute the window start once. The API uses UTC, so we use
        # the same here. The cloud only needs the report refreshed on the
        # coordinator interval, so this is stable enough for ``last_reset``.
        self._window_start = datetime.now(UTC) - timedelta(days=ENERGY_REPORT_DAYS)

    @property
    def unique_id(self) -> str:
        """Unique id that disambiguates this from the room-temperature sensor."""
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_energy"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._appliance.FriendlyName} Energy"

    @property
    def _energy_points(self) -> list[tuple[datetime | None, float]]:
        """Return the parsed telemetry points for this appliance, if any."""
        energy = self.coordinator.data.get("energy") or {}
        hub_points = energy.get(self._hub.HubId) or {}
        return hub_points.get(self._appliance.ApplianceId, [])

    @property
    def available(self) -> bool:
        """The sensor is only available when the cloud returned data."""
        return bool(self._energy_points)

    @property
    def native_value(self) -> float | None:
        """Return the total kWh used in the current report window."""
        points = self._energy_points
        if not points:
            return None
        return round(sum(value for _, value in points), 3)

    @property
    def last_reset(self) -> datetime:
        """Return the start of the energy report window."""
        return self._window_start

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the report window for transparency / debugging."""
        points = self._energy_points
        return {
            "window_days": ENERGY_REPORT_DAYS,
            "interval": ENERGY_REPORT_INTERVAL,
            "telemetry_points": len(points),
        }
