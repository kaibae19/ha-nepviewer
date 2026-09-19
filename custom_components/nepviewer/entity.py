"""Shared entity base for the NEPViewer integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import DeviceData, NepViewerCoordinator


class NepViewerEntity(CoordinatorEntity[NepViewerCoordinator]):
    """Base entity tied to one inverter."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NepViewerCoordinator, sn: str) -> None:
        """Initialise the entity for a given serial number."""
        super().__init__(coordinator)
        self._sn = sn

    @property
    def device(self) -> DeviceData | None:
        """Return the current data for this inverter."""
        return (self.coordinator.data or {}).get(self._sn)

    @property
    def available(self) -> bool:
        """Return True while the account still reports this inverter."""
        return super().available and self.device is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return registry information for this inverter."""
        device = self.device
        info = DeviceInfo(
            identifiers={(DOMAIN, self._sn)},
            manufacturer=MANUFACTURER,
            serial_number=self._sn,
            name=device.name if device else self._sn,
        )
        if device:
            if device.model:
                info["model"] = device.model
            if device.sw_version:
                info["sw_version"] = device.sw_version
            info["configuration_url"] = "https://user.nepviewer.com"
        return info
