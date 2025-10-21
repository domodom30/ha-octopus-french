"""Config flow for OEFR Energy integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ACCOUNT_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .octopus_french import OctopusFrenchApiClient


class OctopusFrenchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OEFR Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.email: str | None = None
        self.password: str | None = None
        self.accounts: list = []
        self.api_client: OctopusFrenchApiClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.email = user_input[CONF_EMAIL]
            self.password = user_input[CONF_PASSWORD]
            self.api_client = OctopusFrenchApiClient(self.email, self.password)

            try:
                auth_success = await self.api_client.authenticate()

                if not auth_success:
                    errors["base"] = "invalid_auth"
                else:
                    self.accounts = await self.api_client.get_accounts()

                    if not self.accounts:
                        errors["base"] = "no_accounts"
                    else:
                        await self.async_set_unique_id(self.accounts[0]["number"])
                        self._abort_if_unique_id_configured()

                        if len(self.accounts) == 1:
                            return self.async_create_entry(
                                title=f"Octopus French Energy - {self.accounts[0]['number']}",
                                data={
                                    CONF_EMAIL: self.email,
                                    CONF_PASSWORD: self.password,
                                    CONF_ACCOUNT_NUMBER: self.accounts[0]["number"],
                                },
                            )
            except Exception:
                errors["base"] = "cannot_connect"
            finally:
                if self.api_client:
                    await self.api_client.close()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle account selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            account_number = user_input[CONF_ACCOUNT_NUMBER]

            if self.api_client:
                await self.api_client.close()

            return self.async_create_entry(
                title=f"Octopus French Energy - {account_number}",
                data={
                    CONF_EMAIL: self.email,
                    CONF_PASSWORD: self.password,
                    CONF_ACCOUNT_NUMBER: account_number,
                },
            )

        account_list = {
            account["number"]: f"{account['number']}" for account in self.accounts
        }

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCOUNT_NUMBER): vol.In(account_list),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OctopusFrenchOptionsFlow:
        """Get the options flow for this handler."""
        return OctopusFrenchOptionsFlow(config_entry)


class OctopusFrenchOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Octopus Energy France."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

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
                        "scan_interval",
                        default=self.config_entry.options.get(
                            "scan_interval", DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
