"""Sensor platform for the NEPViewer integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import DeviceData, NepViewerConfigEntry, NepViewerCoordinator
from .entity import NepViewerEntity
from .util import as_float, dig, to_kwh, to_watts


@dataclass(frozen=True, kw_only=True)
class NepViewerSensorDescription(SensorEntityDescription):
    """Describes a NEPViewer sensor."""

    value_fn: Callable[[DeviceData], StateType | datetime]
    # Power readings keep being served by the cloud long after an inverter
    # stops uploading; these are reported as unknown once the data goes stale.
    clear_when_stale: bool = False
    exists_fn: Callable[[DeviceData], bool] = lambda _device: True
    # For per-PV-input sensors: whether this field carries real data for a
    # given module. NEP populates the cumulative fields but leaves per-module
    # live power at zero, so that entity is only created if it ever moves.
    module_exists_fn: Callable[[dict[str, Any]], bool] | None = None


def _timestamp(device: DeviceData) -> datetime | None:
    """Return the last upload as an aware datetime."""
    ts = device.last_update_ts
    return datetime.fromtimestamp(ts, UTC) if ts else None


DEVICE_SENSORS: tuple[NepViewerSensorDescription, ...] = (
    NepViewerSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        clear_when_stale=True,
        value_fn=lambda d: to_watts(
            d.overview.get("totalNow"), d.overview.get("totalNowUnit")
        ),
    ),
    NepViewerSensorDescription(
        key="energy_today",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: to_kwh(
            dig(d.overview, "production", "today"),
            dig(d.overview, "production", "todayUnit"),
        ),
    ),
    NepViewerSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: to_kwh(
            dig(d.overview, "production", "total"),
            dig(d.overview, "production", "totalUnit"),
        ),
    ),
    NepViewerSensorDescription(
        key="energy_yesterday",
        translation_key="energy_yesterday",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: to_kwh(
            dig(d.overview, "production", "yesterday"),
            dig(d.overview, "production", "yesterdayUnit"),
        ),
    ),
    NepViewerSensorDescription(
        key="energy_month",
        translation_key="energy_month",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: to_kwh(
            dig(d.overview, "production", "month"),
            dig(d.overview, "production", "monthUnit"),
        ),
    ),
    NepViewerSensorDescription(
        key="energy_year",
        translation_key="energy_year",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: to_kwh(
            dig(d.overview, "production", "year"),
            dig(d.overview, "production", "yearUnit"),
        ),
    ),
    NepViewerSensorDescription(
        key="last_report",
        translation_key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_timestamp,
    ),
    NepViewerSensorDescription(
        key="status",
        translation_key="status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.overview.get("statusTitle") or d.listing.get("statusTitle"),
    ),
    NepViewerSensorDescription(
        key="alert_code",
        translation_key="alert_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.overview.get("alertCode") or d.listing.get("alertCode"),
    ),
    NepViewerSensorDescription(
        key="alert_title",
        translation_key="alert_title",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.overview.get("alertTitle") or d.listing.get("alertTitle"),
    ),
    NepViewerSensorDescription(
        key="co2_saved",
        translation_key="co2_saved",
        native_unit_of_measurement="kg",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: as_float(dig(d.overview, "environmentalBenefit", "co2")),
    ),
    # Only meaningful with a smart meter paired; without one the API mirrors
    # PV power into the home and grid legs and hides them in its own UI.
    NepViewerSensorDescription(
        key="home_power",
        translation_key="home_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        clear_when_stale=True,
        exists_fn=lambda d: bool(d.overview.get("isConsumption")),
        value_fn=lambda d: to_watts(
            dig(d.overview, "energy", "home", "power"),
            dig(d.overview, "energy", "home", "powerUnit"),
        ),
    ),
    NepViewerSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        clear_when_stale=True,
        exists_fn=lambda d: bool(d.overview.get("isConsumption")),
        value_fn=lambda d: to_watts(
            dig(d.overview, "energy", "grid", "power"),
            dig(d.overview, "energy", "grid", "powerUnit"),
        ),
    ),
)


def _module(device: DeviceData, addr: Any) -> dict[str, Any]:
    """Return the module dict for a PV input address."""
    for module in device.modules:
        if module.get("addr") == addr:
            return module
    return {}


MODULE_SENSORS: tuple[NepViewerSensorDescription, ...] = (
    NepViewerSensorDescription(
        key="module_power",
        translation_key="module_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        clear_when_stale=True,
        module_exists_fn=lambda m: bool(m.get("lastUpdateTime"))
        or bool(as_float(m.get("now"))),
        value_fn=lambda d: None,  # replaced per module below
    ),
    NepViewerSensorDescription(
        key="module_energy_today",
        translation_key="module_energy_today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        module_exists_fn=lambda m: _module_has_data(m),
        value_fn=lambda d: None,
    ),
    NepViewerSensorDescription(
        key="module_energy_total",
        translation_key="module_energy_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        module_exists_fn=lambda m: _module_has_data(m),
        value_fn=lambda d: None,
    ),
)


def _module_value(key: str, addr: Any) -> Callable[[DeviceData], StateType]:
    """Build a value getter for one module field.

    Module energy is reported in Wh even though the payload labels it kWh, so
    the unit tag from the API is deliberately ignored here.
    """

    def getter(device: DeviceData) -> StateType:
        module = _module(device, addr)
        if key == "module_power":
            return to_watts(module.get("now"), module.get("nowUnit"))
        if key == "module_energy_today":
            return to_kwh(module.get("todayPower"), "Wh")
        return to_kwh(module.get("totalPower"), "Wh")

    return getter


def _module_has_data(module: dict[str, Any]) -> bool:
    """Return True if a PV input has ever reported anything.

    Unused inputs sit at zero forever; creating entities for them is noise.
    """
    return bool(
        module.get("lastUpdateTime")
        or as_float(module.get("totalPower"))
        or as_float(module.get("todayPower"))
        or as_float(module.get("now"))
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NepViewerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NEPViewer sensors."""
    coordinator = entry.runtime_data
    known_modules: set[tuple[str, Any, str]] = set()

    entities: list[SensorEntity] = []
    for sn, device in (coordinator.data or {}).items():
        entities.extend(
            NepViewerSensor(coordinator, sn, description)
            for description in DEVICE_SENSORS
            if description.exists_fn(device)
        )

    @callback
    def _add_module_entities() -> None:
        """Add entities for PV inputs, including ones that appear later."""
        new: list[SensorEntity] = []
        for sn, device in (coordinator.data or {}).items():
            for module in device.modules:
                addr = module.get("addr")
                if addr is None:
                    continue
                for description in MODULE_SENSORS:
                    if (sn, addr, description.key) in known_modules:
                        continue
                    exists = description.module_exists_fn
                    if exists is not None and not exists(module):
                        continue
                    known_modules.add((sn, addr, description.key))
                    new.append(
                        NepViewerModuleSensor(coordinator, sn, description, addr)
                    )
        if new:
            async_add_entities(new)

    _add_module_entities()
    async_add_entities(entities)
    entry.async_on_unload(coordinator.async_add_listener(_add_module_entities))


class NepViewerSensor(NepViewerEntity, SensorEntity):
    """A sensor reading one field of the inverter payload."""

    entity_description: NepViewerSensorDescription

    def __init__(
        self,
        coordinator: NepViewerCoordinator,
        sn: str,
        description: NepViewerSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, sn)
        self.entity_description = description
        self._attr_unique_id = f"{sn}_{description.key}"

    @property
    def native_value(self) -> StateType | datetime:
        """Return the current value."""
        device = self.device
        if device is None:
            return None
        if self.entity_description.clear_when_stale and device.is_stale(
            self.coordinator.stale_after_seconds
        ):
            return None
        return self.entity_description.value_fn(device)


class NepViewerModuleSensor(NepViewerSensor):
    """A sensor for one PV input of the inverter."""

    def __init__(
        self,
        coordinator: NepViewerCoordinator,
        sn: str,
        description: NepViewerSensorDescription,
        addr: Any,
    ) -> None:
        """Initialise the module sensor."""
        super().__init__(coordinator, sn, description)
        self._addr = addr
        self._attr_unique_id = f"{sn}_{addr}_{description.key}"
        self._attr_translation_placeholders = {"input": str(addr)}
        self._value_fn = _module_value(description.key, addr)

    @property
    def native_value(self) -> StateType | datetime:
        """Return the current value for this PV input."""
        device = self.device
        if device is None:
            return None
        if self.entity_description.clear_when_stale and device.is_stale(
            self.coordinator.stale_after_seconds
        ):
            return None
        return self._value_fn(device)
