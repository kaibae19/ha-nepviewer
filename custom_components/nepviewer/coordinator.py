"""Data update coordinator for the NEPViewer integration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NepViewerApi, NepViewerAuthError, NepViewerError
from .const import DOMAIN
from .util import corrected_timestamp

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceData:
    """Everything known about one inverter after a refresh."""

    sn: str
    listing: dict[str, Any]
    overview: dict[str, Any]
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Return a human name for the device."""
        alias = (self.listing.get("alias") or "").strip()
        model = self.listing.get("modelName") or self.detail.get("model") or "NEP"
        return alias or f"{model} {self.sn}"

    @property
    def model(self) -> str | None:
        """Return the model name."""
        return self.listing.get("modelName") or self.detail.get("model")

    @property
    def sw_version(self) -> str | None:
        """Return the WiFi module firmware version."""
        return self.listing.get("WIFIVersion") or self.detail.get("wifiVersion")

    @property
    def raw_last_update_ts(self) -> int | None:
        """Return lastUpdateTime exactly as the API reports it."""
        for source in (self.overview, self.listing):
            ts = source.get("lastUpdateTime")
            if ts:
                return int(ts)
        return None

    @property
    def last_update_ts(self) -> int | None:
        """Return the corrected unix timestamp of the inverter's last upload."""
        return corrected_timestamp(
            self.raw_last_update_ts, self.detail.get("timezone")
        )

    @property
    def modules(self) -> list[dict[str, Any]]:
        """Return the per-PV-input module list."""
        return list(self.listing.get("modules") or [])

    def is_stale(self, stale_after_seconds: int) -> bool:
        """Return True if the last upload is too old to trust as a live value.

        The cloud keeps returning the last reading indefinitely after an
        inverter goes offline, so age has to be checked explicitly.
        """
        ts = self.last_update_ts
        if not ts:
            return True
        return (time.time() - ts) > stale_after_seconds


NepViewerConfigEntry = ConfigEntry["NepViewerCoordinator"]


class NepViewerCoordinator(DataUpdateCoordinator[dict[str, DeviceData]]):
    """Poll the NEPViewer cloud for every device on the account."""

    config_entry: NepViewerConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: NepViewerConfigEntry,
        api: NepViewerApi,
        scan_interval: timedelta,
        stale_after_seconds: int,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
            config_entry=entry,
        )
        self.api = api
        self.scan_interval = scan_interval
        self.stale_after_seconds = stale_after_seconds
        self._details: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, DeviceData]:
        """Fetch the device list and per-device statistics."""
        try:
            devices = await self.api.async_get_devices()

            result: dict[str, DeviceData] = {}
            for listing in devices:
                sn = listing.get("sn")
                if not sn:
                    continue

                overview = await self.api.async_get_overview(sn)

                # Static metadata (model, firmware, timezone) changes rarely,
                # so it is fetched once per device. It is also optional: losing
                # it costs the timezone correction and some device registry
                # detail, which is not worth failing the whole update for.
                if sn not in self._details:
                    try:
                        self._details[sn] = await self.api.async_get_detail(sn)
                    except NepViewerAuthError:
                        raise
                    except NepViewerError as err:
                        _LOGGER.debug("device/detail failed for %s: %s", sn, err)
                        self._details[sn] = {}

                result[sn] = DeviceData(
                    sn=sn,
                    listing=listing,
                    overview=overview,
                    detail=self._details.get(sn) or {},
                )

        except NepViewerAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NepViewerError as err:
            raise UpdateFailed(str(err)) from err

        if not result:
            raise UpdateFailed("no devices returned for this account")

        return result
