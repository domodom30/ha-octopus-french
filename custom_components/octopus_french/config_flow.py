"""Config flow for OEFR Energy integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)


class OctopusFrenchConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OEFR Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.email: str = ""
        self.password: str = ""
        self.api_key: str = ""
        self.auth_method: str = "email"
        self.accounts: list = []
        self.api_client: OctopusFrenchApiClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - choose authentication method."""
        if user_input is not None:
            self.auth_method = user_input[CONF_AUTH_METHOD]
            if self.auth_method == "api_key":
                return await self.async_step_api_key()
            return await self.async_step_email_password()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTH_METHOD,
                        default="email",
                    ): vol.In({"email": "Email/Password", "api_key": "API Key"}),
                }
            ),
        )

    async def _async_handle_authentication_step(
        self,
        user_input: dict[str, Any] | None,
        step_id: str,
        schema: vol.Schema,
    ) -> ConfigFlowResult:
        """Handle authentication step for both email/password and API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Create API client based on authentication method
                if self.auth_method == "email":
                    self.email = user_input[CONF_EMAIL]
                    self.password = user_input[CONF_PASSWORD]
                    self.api_client = OctopusFrenchApiClient(
                        email=self.email, password=self.password
                    )
                else:
                    self.api_key = user_input[CONF_API_KEY]
                    self.api_client = OctopusFrenchApiClient(api_key=self.api_key)

                # Authenticate and get accounts
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
                                data=self._build_config_data(self.accounts[0]["number"]),
                            )
                        # Si plusieurs comptes, passer à l'étape de sélection
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
            finally:
                if self.api_client:
                    await self.api_client.close()

        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    def _build_config_data(self, account_number: str) -> dict[str, Any]:
        """Build config entry data based on authentication method."""
        data = {
            CONF_AUTH_METHOD: self.auth_method,
            CONF_ACCOUNT_NUMBER: account_number,
        }
        if self.auth_method == "email":
            data[CONF_EMAIL] = self.email
            data[CONF_PASSWORD] = self.password
        else:
            data[CONF_API_KEY] = self.api_key
        return data

    async def async_step_email_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle email/password authentication step."""
        return await self._async_handle_authentication_step(
            user_input,
            "email_password",
            vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
        )

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle API key authentication step."""
        return await self._async_handle_authentication_step(
            user_input,
            "api_key",
            vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
        )

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle account selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            account_number = user_input[CONF_ACCOUNT_NUMBER]

            if self.api_client:
                await self.api_client.close()

            return self.async_create_entry(
                title=f"Octopus French Energy - {account_number}",
                data=self._build_config_data(account_number),
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
        return OctopusFrenchOptionsFlow()


class OctopusFrenchOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Octopus Energy France."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)  # type: ignore[return-value]

        return self.async_show_form(  # type: ignore[return-value]
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=self.config_entry.options.get(
                            "scan_interval", DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                }
            ),
        )
