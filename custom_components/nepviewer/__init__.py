"""The NEPViewer integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NepViewerApi
from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_STALE_AFTER_MINUTES,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_STALE_AFTER_MINUTES,
)
from .coordinator import NepViewerConfigEntry, NepViewerCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: NepViewerConfigEntry) -> bool:
    """Set up NEPViewer from a config entry."""

    def _store_token(token: str, expires_at: int) -> None:
        """Persist a freshly issued token.

        The backend counts sign-in attempts, so tokens (valid 30 days) are
        cached across restarts instead of re-fetched on every setup.
        """
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_TOKEN: token,
                CONF_TOKEN_EXPIRES_AT: expires_at,
            },
        )

    api = NepViewerApi(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        token=entry.data.get(CONF_TOKEN),
        token_expires_at=entry.data.get(CONF_TOKEN_EXPIRES_AT),
        token_callback=_store_token,
    )

    scan_minutes = entry.options.get(
        CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
    )
    stale_minutes = entry.options.get(
        CONF_STALE_AFTER_MINUTES, DEFAULT_STALE_AFTER_MINUTES
    )

    coordinator = NepViewerCoordinator(
        hass,
        entry,
        api,
        scan_interval=timedelta(minutes=scan_minutes),
        stale_after_seconds=stale_minutes * 60,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NepViewerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: NepViewerConfigEntry) -> None:
    """Reload the entry when its options change.

    Entry updates also fire when a refreshed token is written back to the
    entry data, which must not bounce the integration, so the options are
    compared against what the running coordinator was built with.
    """
    coordinator = entry.runtime_data
    scan_minutes = entry.options.get(
        CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
    )
    stale_minutes = entry.options.get(
        CONF_STALE_AFTER_MINUTES, DEFAULT_STALE_AFTER_MINUTES
    )
    if (
        coordinator.scan_interval == timedelta(minutes=scan_minutes)
        and coordinator.stale_after_seconds == stale_minutes * 60
    ):
        return

    await hass.config_entries.async_reload(entry.entry_id)
