"""Binary sensor platform for the NEPViewer integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DeviceData, NepViewerConfigEntry, NepViewerCoordinator
from .entity import NepViewerEntity

OK_ALERT_CODES = {"0000", "0", ""}


@dataclass(frozen=True, kw_only=True)
class NepViewerBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a NEPViewer binary sensor."""

    value_fn: Callable[[DeviceData, int], bool | None]


def _reporting(device: DeviceData, stale_after_seconds: int) -> bool:
    """Return True while the inverter is uploading fresh data.

    The cloud reports "online" from its last known state, so freshness of the
    last upload is the honest signal here.
    """
    return not device.is_stale(stale_after_seconds)


def _problem(device: DeviceData, _stale_after_seconds: int) -> bool:
    """Return True if the inverter is reporting an alert."""
    code = str(
        device.overview.get("alertCode") or device.listing.get("alertCode") or ""
    ).strip()
    return code not in OK_ALERT_CODES


BINARY_SENSORS: tuple[NepViewerBinarySensorDescription, ...] = (
    NepViewerBinarySensorDescription(
        key="reporting",
        translation_key="reporting",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_reporting,
    ),
    NepViewerBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_problem,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NepViewerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up NEPViewer binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        NepViewerBinarySensor(coordinator, sn, description)
        for sn in (coordinator.data or {})
        for description in BINARY_SENSORS
    )


class NepViewerBinarySensor(NepViewerEntity, BinarySensorEntity):
    """Binary sensor derived from the inverter payload."""

    entity_description: NepViewerBinarySensorDescription

    def __init__(
        self,
        coordinator: NepViewerCoordinator,
        sn: str,
        description: NepViewerBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, sn)
        self.entity_description = description
        self._attr_unique_id = f"{sn}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the current state."""
        device = self.device
        if device is None:
            return None
        return self.entity_description.value_fn(
            device, self.coordinator.stale_after_seconds
        )
