"""Config flow for the NEPViewer integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import NepViewerApi, NepViewerAuthError, NepViewerError
from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_STALE_AFTER_MINUTES,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRES_AT,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_STALE_AFTER_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MAX_STALE_AFTER_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    MIN_STALE_AFTER_MINUTES,
)
from .coordinator import NepViewerConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


class NepViewerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the NEPViewer config flow."""

    VERSION = 1

    async def _async_validate(
        self, email: str, password: str
    ) -> tuple[dict[str, str], NepViewerApi | None, int]:
        """Sign in and count the devices on the account."""
        api = NepViewerApi(async_get_clientsession(self.hass), email, password)
        try:
            await api.async_login()
            devices = await api.async_get_devices()
        except NepViewerAuthError:
            return {"base": "invalid_auth"}, None, 0
        except NepViewerError as err:
            _LOGGER.debug("NEPViewer connection error: %s", err)
            return {"base": "cannot_connect"}, None, 0
        return {}, api, len(devices)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()

            errors, api, device_count = await self._async_validate(email, password)
            if not errors and api is not None:
                if device_count == 0:
                    errors["base"] = "no_devices"
                else:
                    return self.async_create_entry(
                        title=email,
                        data={
                            CONF_EMAIL: email,
                            CONF_PASSWORD: password,
                            CONF_TOKEN: api.token,
                            CONF_TOKEN_EXPIRES_AT: api.token_expires_at,
                        },
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication after the stored credentials stop working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            errors, api, _ = await self._async_validate(
                entry.data[CONF_EMAIL], password
            )
            if not errors and api is not None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_PASSWORD: password,
                        CONF_TOKEN: api.token,
                        CONF_TOKEN_EXPIRES_AT: api.token_expires_at,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    )
                }
            ),
            description_placeholders={CONF_EMAIL: entry.data[CONF_EMAIL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: NepViewerConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return NepViewerOptionsFlow()


class NepViewerOptionsFlow(OptionsFlow):
    """Handle NEPViewer options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage polling and staleness options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_MINUTES: int(
                        user_input[CONF_SCAN_INTERVAL_MINUTES]
                    ),
                    CONF_STALE_AFTER_MINUTES: int(user_input[CONF_STALE_AFTER_MINUTES]),
                }
            )

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=options.get(
                        CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_STALE_AFTER_MINUTES,
                    default=options.get(
                        CONF_STALE_AFTER_MINUTES, DEFAULT_STALE_AFTER_MINUTES
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_STALE_AFTER_MINUTES,
                        max=MAX_STALE_AFTER_MINUTES,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
