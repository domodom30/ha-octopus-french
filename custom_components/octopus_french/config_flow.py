"""Config flow for Octopus Energy French integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import aiohttp_client

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_ACCOUNT_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_GAS_CONVERSION_FACTOR,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_GAS_CONVERSION,
)
from .lib.octopus_french import OctopusFrenchClient
from .utils.logger import LOGGER


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT_NUMBER): str,
    }
)

STEP_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=24)
        ),
        vol.Optional(
            CONF_GAS_CONVERSION_FACTOR, default=DEFAULT_GAS_CONVERSION
        ): vol.All(vol.Coerce(float), vol.Range(min=1, max=20)),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    session = aiohttp_client.async_get_clientsession(hass)
    client = OctopusFrenchClient(data[CONF_EMAIL], data[CONF_PASSWORD], session)

    # Authenticate
    if not await client.authenticate():
        raise InvalidAuth

    # Get accounts
    accounts = await client.get_accounts()
    if not accounts:
        raise CannotConnect

    return {"accounts": accounts}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Octopus Energy French."""

    VERSION = 1
    reauth_entry: config_entries.ConfigEntry | None = None

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._email: str | None = None
        self._password: str | None = None
        self._accounts: list[dict] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                # Always go to account selection step
                self._email = user_input[CONF_EMAIL]
                self._password = user_input[CONF_PASSWORD]
                self._accounts = info["accounts"]
                return await self.async_step_account()

            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle account selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Create the entry with selected account
                data = {
                    CONF_EMAIL: self._email,
                    CONF_PASSWORD: self._password,
                    CONF_ACCOUNT_NUMBER: user_input[CONF_ACCOUNT_NUMBER],
                }

                return self.async_create_entry(
                    title=f"Octopus Energy French ({self._email})",
                    data=data,
                )

            except Exception:
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Create account selection options
        account_options = {
            acc["number"]: f"{acc['number']} ({acc.get('status', 'Unknown')})"
            for acc in self._accounts
        }

        schema = vol.Schema(
            {vol.Required(CONF_ACCOUNT_NUMBER): vol.In(account_options)}
        )

        return self.async_show_form(
            step_id="account",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "email": self._email,
                "account_count": str(len(self._accounts)),
            },
        )

    async def async_step_reauth(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle reauthentication."""
        self.reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauthentication."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate new credentials
                data = {**self.reauth_entry.data, **user_input}
                info = await validate_input(self.hass, data)

                # Update the entry
                self.hass.config_entries.async_update_entry(
                    self.reauth_entry, data=data
                )
                await self.hass.config_entries.async_reload(self.reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Octopus Energy French."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=24))
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
