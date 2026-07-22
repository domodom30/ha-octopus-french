"""Gas sensor entity for Octopus Energy France."""

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, LEDGER_TYPE_GAS
from ..coordinator import OctopusFrenchDataUpdateCoordinator
from ..utils import get_tariff_rate_for_key

_LOGGER = logging.getLogger(__name__)


class OctopusGasSensor(  # pyright: ignore[reportIncompatibleVariableOverride] -- Entity.available and CoordinatorEntity.available are defined incompatible
    CoordinatorEntity[OctopusFrenchDataUpdateCoordinator], SensorEntity
):
    """Sensor for gas data."""

    def __init__(
        self,
        coordinator: OctopusFrenchDataUpdateCoordinator,
        pce_ref: str,
        sensor_config: SensorEntityDescription,
    ) -> None:
        """Initialize the gas sensor."""
        super().__init__(coordinator)

        self._pce_ref = pce_ref
        self._sensor_config = sensor_config
        self._attr_unique_id = f"{DOMAIN}_{pce_ref}_{sensor_config.key}"
        self._attr_translation_key = sensor_config.key
        self._attr_has_entity_name = True
        self._attr_icon = sensor_config.icon
        self._attr_device_class = sensor_config.device_class
        self._attr_state_class = sensor_config.state_class
        self._attr_native_unit_of_measurement = sensor_config.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, pce_ref)})

        if sensor_config.suggested_display_precision is not None:
            self._attr_suggested_display_precision = (
                sensor_config.suggested_display_precision
            )
        self._attr_entity_category = sensor_config.entity_category

        self._current_month: str | None = None
        self._update_attrs()

    def _get_current_month(self) -> str:
        """Get current month in YYYY-MM format."""
        return dt_util.now().strftime("%Y-%m")

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attrs()
        super()._handle_coordinator_update()

    def _update_attrs(self) -> None:
        """Refresh the cached attribute values from coordinator data."""
        self._attr_last_reset = self._compute_last_reset()
        self._attr_native_value = self._compute_native_value()
        self._attr_extra_state_attributes = self._compute_attributes()

    def _calculate_monthly_subscription(self) -> float:
        """Get the monthly subscription cost from agreements."""
        agreements = self.coordinator.data.get("agreements", [])

        for agreement in agreements:
            if agreement.get("prm") == self._pce_ref and agreement.get("is_active"):
                tariffs = agreement.get("tariffs") or {}
                subscription = tariffs.get("subscription") or {}

                if subscription:
                    monthly_ttc = subscription.get("monthly_ttc_eur")
                    if monthly_ttc is not None:
                        return round(monthly_ttc, 2)

        _LOGGER.debug("No subscription found in agreements for PCE %s", self._pce_ref)
        return 0.0

    def _calculate_monthly_total(self) -> float:
        """Calculate total for current month from all readings."""
        readings = self.coordinator.data.get("gas", [])

        if not readings:
            return 0.0

        try:
            sorted_readings = sorted(
                readings, key=lambda x: x.get("startAt", ""), reverse=False
            )
        except (TypeError, KeyError) as e:
            _LOGGER.warning("Error sorting gas readings: %s", e)
            sorted_readings = readings

        current_month = self._get_current_month()
        total = 0.0

        for reading in sorted_readings:
            reading_date = reading.get("startAt")

            if not reading_date:
                continue

            try:
                date_obj = datetime.fromisoformat(reading_date)
                reading_month = date_obj.strftime("%Y-%m")

                if reading_month != current_month:
                    continue

            except (ValueError, TypeError, AttributeError) as e:
                _LOGGER.warning("Error parsing gas date %s: %s", reading_date, e)
                continue

            total += float(reading.get("value", 0))

        return round(total, 2)

    def _calculate_monthly_cost(self) -> float:
        """Calculate monthly cost from consumption and tariff."""
        consumption = self._calculate_monthly_total()

        if consumption == 0:
            return 0.0

        tariff_rate = self._get_tariff_rate()

        if tariff_rate is None or tariff_rate == 0:
            _LOGGER.warning(
                "No tariff rate found for gas meter %s, cannot calculate cost",
                self._pce_ref,
            )
            return 0.0

        cost = consumption * tariff_rate

        return round(cost, 2)

    def _compute_last_reset(self) -> datetime | None:
        """Expose the monthly reset for the current-month total sensors."""
        key = self._sensor_config.key
        if key in ("consumption", "cost", "subscription"):
            return dt_util.start_of_local_day().replace(day=1)
        return None

    def _compute_native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        key = self._sensor_config.key

        if key == "contract":
            return self._get_contract_status()

        if key == "subscription":
            return self._calculate_monthly_subscription()

        if key == "rate_base":
            return self._get_tariff_rate()

        if key == "consumption":
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_total()

        if key == "cost":
            current_month = self._get_current_month()
            if self._current_month != current_month:
                self._current_month = current_month
            return self._calculate_monthly_cost()

        return None

    def _compute_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        key = self._sensor_config.key

        if key == "contract":
            supply_points = self.coordinator.data.get("supply_points", {})
            gas_points = supply_points.get("gas", [])
            meter = next((m for m in gas_points if m.get("prm") == self._pce_ref), None)

            if not meter:
                return {}

            ledger = self.coordinator.data.get("ledgers", {}).get(LEDGER_TYPE_GAS, {})

            return {
                "ledger_id": ledger.get("number"),
                "pce_ref": meter.get("prm"),
                "gas_nature": meter.get("gasNature"),
                "annual_consumption": f"{meter.get('annualConsumption')} kWh",
                "is_smart_meter": meter.get("isSmartMeter"),
                "powered_status": meter.get("poweredStatus"),
            }

        if key == "subscription":
            agreements = self.coordinator.data.get("agreements", [])
            agreement_data = None

            for agreement in agreements:
                if agreement.get("prm") == self._pce_ref and agreement.get("is_active"):
                    agreement_data = agreement
                    break

            attributes: dict[str, Any] = {}

            if agreement_data:
                tariffs = agreement_data.get("tariffs") or {}
                subscription = tariffs.get("subscription") or {}

                attributes.update(
                    {
                        "contract_number": agreement_data.get("contract_number"),
                        "product_name": agreement_data.get("product", {}).get(
                            "display_name"
                        ),
                        "annual_ht_eur": subscription.get("annual_ht_eur"),
                        "annual_ttc_eur": subscription.get("annual_ttc_eur"),
                        "monthly_ttc_eur": subscription.get("monthly_ttc_eur"),
                        "billing_frequency_months": agreement_data.get(
                            "billing_frequency_months"
                        ),
                        "valid_from": agreement_data.get("valid_from"),
                        "calculation_method": "From agreement",
                    }
                )

                next_payment = agreement_data.get("next_payment")
                if next_payment:
                    attributes["next_payment_amount"] = (
                        next_payment.get("amount") / 100
                        if next_payment.get("amount")
                        else None
                    )
                    attributes["next_payment_date"] = next_payment.get("date")
            else:
                attributes.update(
                    {
                        "calculation_method": "No agreement found",
                    }
                )

            return attributes

        if key == "consumption":
            readings = self.coordinator.data.get("gas", [])

            return {
                "current_month": self._current_month,
                "readings_count": len(readings),
                "calculation_method": "Cumulée / mois",
                "last_imported_date": self._last_imported_date(),
            }

        if key == "cost":
            readings = self.coordinator.data.get("gas", [])
            tariff_rate = self._get_tariff_rate()

            return {
                "current_month": self._current_month,
                "readings_count": len(readings),
                "calculation_method": "Cumulée / mois",
                "last_imported_date": self._last_imported_date(),
                "tariff_eur_kwh": tariff_rate,
            }

        if key == "rate_base":
            agreements = self.coordinator.data.get("agreements", [])

            for agreement in agreements:
                if agreement.get("prm") == self._pce_ref and agreement.get("is_active"):
                    tariffs = agreement.get("tariffs") or {}
                    consumption = tariffs.get("consumption", {})
                    base_rate = consumption.get("base")

                    if base_rate:
                        return {
                            "contract_number": agreement.get("contract_number"),
                            "product_name": agreement.get("product", {}).get(
                                "display_name"
                            ),
                            "valid_from": agreement.get("valid_from"),
                            "price_ht_eur_kwh": base_rate.get("price_ht"),
                            "price_ttc_eur_kwh": base_rate.get("price_ttc"),
                        }

            return {"status": "No agreement found"}

        return {}

    def _last_imported_date(self) -> str | None:
        """Dernière date importée dans les statistiques pour ce sensor."""
        importer = getattr(self.coordinator, "statistics_importer", None)
        if importer is None:
            return None
        statistic_id = f"{DOMAIN}:{self._pce_ref}_{self._sensor_config.key}"
        return importer.last_imported.get(statistic_id)

    def _get_tariff_rate(self) -> float | None:
        """Get the tariff rate from agreements."""
        return get_tariff_rate_for_key(
            self.coordinator.data, self._pce_ref, "rate_base"
        )

    def _get_contract_status(self) -> str:
        """Get a human-readable contract status."""
        supply_points = self.coordinator.data.get("supply_points", {})
        gas_points = supply_points.get("gas", [])
        meter = next((m for m in gas_points if m.get("prm") == self._pce_ref), None)

        if not meter:
            return "Inconnu"

        powered = meter.get("poweredStatus", "")
        powered_map = {"non_coupe": "En service", "coupe": "Coupé"}
        return powered_map.get(powered, "Inconnu")
