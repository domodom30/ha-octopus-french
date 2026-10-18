"""Ledger sensor entity for Octopus Energy France."""

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..coordinator import OctopusFrenchDataUpdateCoordinator
from .descriptions import OctopusLedgerSensorDescription

_LOGGER = logging.getLogger(__name__)


def _cents_to_euros(cents: float | None) -> float | None:
    """Convert an amount in cents to euros, keeping None."""
    return cents / 100 if cents is not None else None


class OctopusLedgerSensor(
    CoordinatorEntity[OctopusFrenchDataUpdateCoordinator], SensorEntity
):
    """Sensor for account ledgers (balances)."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        account_number: str,
        sensor_config: OctopusLedgerSensorDescription,
    ) -> None:
        """Initialize the ledger sensor."""
        super().__init__(coordinator)
        self._account_number = account_number
        self._ledger_type = sensor_config.ledger_type
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{account_number}_{sensor_config.key}"
        self._attr_translation_key = sensor_config.key
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config.icon
        self._attr_device_class = sensor_config.device_class
        self._attr_state_class = sensor_config.state_class
        self._attr_native_unit_of_measurement = sensor_config.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, account_number)})

        if sensor_config.suggested_display_precision is not None:
            self._attr_suggested_display_precision = (
                sensor_config.suggested_display_precision
            )
        self._update_attrs()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Recompute derived attributes when coordinator data changes."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        self._attr_native_value = self._compute_native_value()
        self._attr_extra_state_attributes = self._compute_attributes()

    def _compute_native_value(self) -> float | None:
        """Return the balance in euros."""
        key = self._sensor_config.key

        if "bill" in key:
            payment_requests = self.coordinator.data.get("payment_requests", {})

            _LOGGER.debug(
                "Looking for payment request with ledger_type: %s in %s",
                self._ledger_type,
                list(payment_requests.keys()),
            )

            last_payment = payment_requests.get(self._ledger_type)

            if last_payment:
                # customerAmount is what is still due by the customer: it drops
                # to 0 once the payment is cleared, so the bill is totalAmount.
                amount = last_payment.get("totalAmount")
                if amount is None:
                    amount = last_payment.get("customerAmount")
                if amount is not None:
                    return amount / 100
                _LOGGER.warning(
                    "Payment request found but no totalAmount for %s",
                    self._ledger_type,
                )
            else:
                _LOGGER.debug(
                    "No payment request found for ledger type: %s", self._ledger_type
                )
            return None

        ledgers = self.coordinator.data.get("ledgers", {})
        ledger = ledgers.get(self._ledger_type, {})
        balance_cents = ledger.get("balance")

        return balance_cents / 100 if balance_cents is not None else None

    def _compute_attributes(self) -> dict[str, Any]:
        """Return ledger information."""
        key = self._sensor_config.key

        if "bill" in key:
            payment_requests = self.coordinator.data.get("payment_requests", {})
            last_payment = payment_requests.get(self._ledger_type)

            if last_payment:
                return {
                    "payment_status": (last_payment.get("paymentStatus") or "").lower(),
                    "total_amount": _cents_to_euros(last_payment.get("totalAmount")),
                    "customer_amount": _cents_to_euros(
                        last_payment.get("customerAmount")
                    ),
                    "expected_payment_date": last_payment.get("expectedPaymentDate"),
                    "ledger_type": self._ledger_type,
                }
            return {"ledger_type": self._ledger_type, "status": "no_data"}

        ledgers = self.coordinator.data.get("ledgers", {})
        ledger = ledgers.get(self._ledger_type, {})

        return {
            "ledger_number": ledger.get("number"),
            "ledger_name": ledger.get("name"),
            "balance_cents": ledger.get("balance"),
            "ledger_type": self._ledger_type,
        }
