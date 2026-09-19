"""Diagnostics support for the NEPViewer integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import NepViewerConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_TOKEN,
    "userEmail",
    "installerEmail",
    "street",
    "latitude",
    "longitude",
    "sid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NepViewerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "stale_after_seconds": coordinator.stale_after_seconds,
        "devices": {
            sn: {
                "listing": async_redact_data(device.listing, TO_REDACT),
                "overview": async_redact_data(device.overview, TO_REDACT),
                "detail": async_redact_data(device.detail, TO_REDACT),
                "is_stale": device.is_stale(coordinator.stale_after_seconds),
            }
            for sn, device in (coordinator.data or {}).items()
        },
    }
