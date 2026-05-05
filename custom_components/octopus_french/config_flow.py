"""Config flow for OEFR Energy integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCOUNT_NUMBER, DOMAIN
from .octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)


class OctopusFrenchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OEFR Energy."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.email: str = ""
        self.password: str = ""
        self.accounts: list = []
        self.api_client: OctopusFrenchApiClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.email = user_input[CONF_EMAIL]
            self.password = user_input[CONF_PASSWORD]
            self.api_client = OctopusFrenchApiClient(
                self.email, self.password, async_get_clientsession(self.hass)
            )

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
                        return await self.async_step_account()

            except (ConnectionError, TimeoutError) as err:
                _LOGGER.error("Connection error during authentication: %s", err)
                errors["base"] = "cannot_connect"
            except ValueError as err:
                _LOGGER.error("Invalid data received: %s", err)
                errors["base"] = "invalid_auth"
            except (KeyError, IndexError, TypeError) as err:
                _LOGGER.error("Error parsing account data: %s", err)
                errors["base"] = "unknown"

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
    ) -> ConfigFlowResult:
        """Handle account selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            account_number = user_input[CONF_ACCOUNT_NUMBER]

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

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            email = reauth_entry.data[CONF_EMAIL]
            api_client = OctopusFrenchApiClient(
                email, user_input[CONF_PASSWORD], async_get_clientsession(self.hass)
            )

            try:
                auth_success = await api_client.authenticate()
                if not auth_success:
                    errors["base"] = "invalid_auth"
                else:
                    return self.async_update_reload_and_abort(
                        reauth_entry,
                        data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                    )
            except (ConnectionError, TimeoutError):
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
