"""The Octopus French Energy integration."""

import logging
from contextlib import suppress
from dataclasses import dataclass, field

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform, UnitOfApparentPower
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN_EXPIRY,
    DOMAIN,
    SERVICE_FORCE_UPDATE,
)
from .coordinator import OctopusFrenchDataUpdateCoordinator
from .coordinator_intelligent import OctopusIntelligentDataUpdateCoordinator
from .octopus_french import OctopusConnectionError, OctopusFrenchApiClient
from .statistics_import import OctopusStatisticsImporter

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class OctopusFrenchRuntimeData:
    """Runtime data stored in config entry."""

    coordinator: OctopusFrenchDataUpdateCoordinator
    account_number: str
    intelligent_coordinator: OctopusIntelligentDataUpdateCoordinator | None = field(
        default=None
    )


type OctopusFrenchConfigEntry = ConfigEntry[OctopusFrenchRuntimeData]

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Octopus French Energy integration."""

    async def handle_force_update(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.coordinator.async_request_refresh()
                intelligent = entry.runtime_data.intelligent_coordinator
                if intelligent is not None:
                    await intelligent.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_UPDATE,
        handle_force_update,
        schema=vol.Schema({}),
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: OctopusFrenchConfigEntry
) -> bool:
    """Set up Octopus French Energy from a config entry."""
    session = async_get_clientsession(hass)
    api_client = OctopusFrenchApiClient(
        email=entry.data["email"],
        password=entry.data["password"],
        session=session,
    )

    # Réutilise le refresh token persisté (valide 7 j) : évite un full login
    # email/mot de passe à chaque redémarrage, qui alimente le rate-limit
    # Kraken (KT-CT-1199).
    api_client.token_manager.restore_refresh_token(
        entry.data.get(CONF_REFRESH_TOKEN),
        entry.data.get(CONF_REFRESH_TOKEN_EXPIRY),
    )

    @callback
    def _persist_refresh_token(token: str | None, expiry: float | None) -> None:
        data = {**entry.data}
        if token:
            data[CONF_REFRESH_TOKEN] = token
            data[CONF_REFRESH_TOKEN_EXPIRY] = expiry
        else:
            data.pop(CONF_REFRESH_TOKEN, None)
            data.pop(CONF_REFRESH_TOKEN_EXPIRY, None)
        if data != dict(entry.data):
            hass.config_entries.async_update_entry(entry, data=data)

    api_client.on_token_update = _persist_refresh_token

    await _async_authenticate(api_client)

    account_number = await _async_get_account_number(
        api_client, entry.data.get("account_number", "")
    )

    coordinator = OctopusFrenchDataUpdateCoordinator(
        hass=hass,
        api_client=api_client,
        account_number=account_number,
        config_entry=entry,
    )

    # Ne pas envelopper : async_config_entry_first_refresh convertit déjà les
    # UpdateFailed en ConfigEntryNotReady et doit laisser passer
    # ConfigEntryAuthFailed pour déclencher le flow de réauthentification.
    await coordinator.async_config_entry_first_refresh()

    # Import de statistiques centralisé : une passe par cycle au lieu d'une
    # tâche par entité energy_/cost_.
    importer = OctopusStatisticsImporter(hass, coordinator)
    coordinator.statistics_importer = importer
    entry.async_on_unload(coordinator.async_add_listener(importer.schedule_import))
    importer.schedule_import()

    intelligent_coordinator = await _async_setup_intelligent_coordinator(
        hass, api_client, account_number, entry
    )

    entry.runtime_data = OctopusFrenchRuntimeData(
        coordinator=coordinator,
        account_number=account_number,
        intelligent_coordinator=intelligent_coordinator,
    )

    await er.async_migrate_entries(
        hass, entry.entry_id, _async_migrate_intelligent_unique_ids
    )

    await _async_create_devices(hass, entry, coordinator, account_number)

    if intelligent_coordinator is not None:
        await _async_create_intelligent_devices(
            hass, entry, intelligent_coordinator, account_number
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


@callback
def _async_migrate_intelligent_unique_ids(
    entity_entry: er.RegistryEntry,
) -> dict[str, str] | None:
    """Prefix legacy Intelligent unique_ids with the domain for consistency."""
    if not entity_entry.unique_id.startswith(f"{DOMAIN}_"):
        return {"new_unique_id": f"{DOMAIN}_{entity_entry.unique_id}"}
    return None


async def _async_authenticate(api_client: OctopusFrenchApiClient) -> None:
    try:
        authenticated = await api_client.authenticate()
    except OctopusConnectionError as err:
        # Covers rate limiting (KT-CT-1199): transient, so let HA back off and retry
        # instead of asking the user to re-enter valid credentials.
        raise ConfigEntryNotReady(f"Cannot connect to Octopus API: {err}") from err

    if not authenticated:
        raise ConfigEntryAuthFailed("Authentication failed - invalid credentials")


async def _async_setup_intelligent_coordinator(
    hass: HomeAssistant,
    api_client: OctopusFrenchApiClient,
    account_number: str,
    entry: OctopusFrenchConfigEntry,
) -> OctopusIntelligentDataUpdateCoordinator | None:
    """Set up the Intelligent coordinator, returns None if not available."""
    try:
        coordinator = OctopusIntelligentDataUpdateCoordinator(
            hass=hass,
            api_client=api_client,
            account_number=account_number,
            config_entry=entry,
        )
        await coordinator.async_config_entry_first_refresh()
        if not coordinator.data.get("devices"):
            _LOGGER.debug("No Intelligent devices found for account %s", account_number)
            return None
        return coordinator
    except ConfigEntryAuthFailed:
        # Une erreur d'authentification doit déclencher le flow de réauthentification.
        raise
    except Exception as err:
        _LOGGER.debug("Octopus Intelligent not available for this account: %s", err)
        return None


async def _async_get_account_number(
    api_client: OctopusFrenchApiClient, configured_account: str
) -> str:
    """Get and validate account number."""
    with suppress(OctopusConnectionError, KeyError, IndexError, TypeError):
        accounts = await api_client.get_accounts()
        if not accounts:
            return configured_account or ""

        account_numbers = [account["number"] for account in accounts]

        if configured_account:
            if configured_account in account_numbers:
                return configured_account
            # Ne jamais basculer silencieusement sur un autre compte : l'unique_id
            # de l'entry est le numéro configuré, les entités garderaient donc son
            # identité tout en exposant les données d'un autre compte.
            raise ConfigEntryError(
                f"Account {configured_account} is no longer available on this "
                "Octopus Energy login"
            )

        if account_numbers:
            return account_numbers[0]

    return configured_account or ""


async def _async_create_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: OctopusFrenchDataUpdateCoordinator,
    account_number: str,
) -> None:
    """Create devices for all meters."""
    device_registry = dr.async_get(hass)
    supply_points = coordinator.data.get("supply_points", {})

    if account_number:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(account_number))},
            name="Compte Octopus Energy",
            manufacturer="Octopus Energy France",
            model="Compte client",
        )

    for elec_meter in supply_points.get("electricity", []):
        prm_id = elec_meter.get("prm")
        if not prm_id:
            continue

        meter_kind = elec_meter.get("meterKind", "N/A")
        suscribed_max_power = elec_meter.get("subscribedMaxPower", "N/A")
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(prm_id))},
            name=f"{meter_kind} {prm_id}",
            manufacturer="Enedis",
            model=f"{elec_meter.get('meterKind', 'N/A')} - {suscribed_max_power} {UnitOfApparentPower.KILO_VOLT_AMPERE}",
        )

    for gas_meter in supply_points.get("gas", []):
        pce_ref = gas_meter.get("prm")
        if not pce_ref:
            continue

        is_smart = gas_meter.get("isSmartMeter", False)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(pce_ref))},
            name=f"Gazpar {pce_ref}",
            manufacturer="GrDF",
            model="Gazpar" if is_smart else "Compteur gaz traditionnel",
        )


async def _async_create_intelligent_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: OctopusIntelligentDataUpdateCoordinator,
    account_number: str,
) -> None:
    """Create vehicle devices for Octopus Intelligent."""
    device_registry = dr.async_get(hass)

    for device in coordinator.data.get("devices", []):
        device_id = device.get("id")
        if not device_id:
            continue

        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, str(device_id))},
            name=device.get("name") or device_id,
            manufacturer=device.get("chargePointMake"),
            model=device.get("chargePointModel"),
            via_device=(DOMAIN, str(account_number)) if account_number else None,
        )


async def async_unload_entry(
    hass: HomeAssistant, entry: OctopusFrenchConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
