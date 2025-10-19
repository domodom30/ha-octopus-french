# Octopus Energy France Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/domodom30/ha-octopus-french)](https://github.com/domodom30/ha-octopus-french/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_french.total)
This custom integration allows you to monitor your Octopus Energy France account directly in Home Assistant. Track your electricity and gas consumption, meter readings, costs, and off-peak hours (Heures Creuses).

## Features

- **Account Balance**: Monitor your "Cagnotte" (savings pot) balance
- **Contract Information**: View your account and meter details
- **Electricity Monitoring**:
  - Separate sensors for HC (Heures Creuses/Off-Peak) and HP (Heures Pleines/Peak) periods
  - Real-time meter index readings
  - Consumption tracking
  - Cost calculation based on current tariffs
  - Binary sensor indicating active off-peak periods
- **Gas Monitoring**:
  - Meter index readings
  - Consumption tracking in m³
  - Cost calculation with automatic kWh conversion
- **Automatic Updates**: Data refreshed every 30 minutes
- **Off-Peak Schedule**: Detailed HC schedule with time ranges and durations

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/domodom30/ha-octopus-french`
6. Select category: "Integration"
7. Click "Add"
8. Search for "Octopus Energy France"
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Download the `custom_components/octopus_french` folder from this repository
2. Copy it to your `custom_components` directory in your Home Assistant configuration folder
3. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Octopus Energy France"
4. Enter your Octopus Energy France credentials:
   - Email
   - Password
5. If you have multiple accounts, select the account you want to monitor
6. Click "Submit"

## Sensors

### Balance Sensor
- **Name**: Cagnotte
- **Unit**: EUR (€)
- **Description**: Your account balance/savings pot
- **Attributes**: Ledger type, name, and number

### Contract Sensor
- **Name**: Contrat
- **Description**: Contract and meter information
- **Attributes**:
  - Account number
  - Electricity meter details (PRM ID, max power, off-peak label, teleoperation status)
  - Gas meter details (PCE reference, annual consumption, smart meter status)

### Electricity Sensors

#### Index Sensors
- **Index Électricité HC**: Off-peak electricity meter reading (kWh)
- **Index Électricité HP**: Peak electricity meter reading (kWh)

#### Consumption Sensors
- **Électricité HC**: Off-peak electricity consumption (kWh)
- **Électricité HP**: Peak electricity consumption (kWh)

#### Cost Sensors
- **Coût Électricité HC**: Off-peak electricity cost (€)
- **Coût Électricité HP**: Peak electricity cost (€)

**Attributes**: PRM ID, period dates, consumption, price per kWh, status

### Gas Sensors

#### Index Sensor
- **Index Gaz**: Gas meter reading (m³)

#### Consumption Sensor
- **Gaz**: Gas consumption (m³)

#### Cost Sensor
- **Coût Gaz**: Gas cost (€)

**Attributes**: PCE reference, period dates, consumption in m³ and kWh, price per kWh

### Binary Sensor

#### Heures Creuses Active
- **State**: ON when currently in off-peak period, OFF otherwise
- **Icon**: Clock with checkmark when active, clock outline when inactive
- **Attributes**:
  - `hc_schedule_available`: Boolean indicating if HC schedule is configured
  - `total_hc_hours`: Total hours of off-peak periods per day
  - `hc_type`: Type of off-peak schedule
  - `hc_range_X`: Individual time ranges (e.g., "22:00 - 06:00")

## Automation Examples

### Turn on water heater during off-peak hours

```yaml
automation:
  - alias: "Water Heater - Off-Peak Hours"
    trigger:
      - platform: state
        entity_id: binary_sensor.heures_creuses_actives
        to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.water_heater
```

### Turn off water heater when peak hours start

```yaml
automation:
  - alias: "Water Heater - Peak Hours"
    trigger:
      - platform: state
        entity_id: binary_sensor.heures_creuses_actives
        to: "off"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.water_heater
```

### Notify when balance is low

```yaml
automation:
  - alias: "Low Balance Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.cagnotte
        below: 10
    action:
      - service: notify.mobile_app
        data:
          title: "Octopus Energy"
          message: "Your balance is low: {{ states('sensor.cagnotte') }}€"
```

### Daily energy consumption report

```yaml
automation:
  - alias: "Daily Energy Report"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Daily Energy Report"
          message: >
            HC: {{ states('sensor.electricite_hc') }} kWh ({{ states('sensor.cout_electricite_hc') }}€)
            HP: {{ states('sensor.electricite_hp') }} kWh ({{ states('sensor.cout_electricite_hp') }}€)
            Gas: {{ states('sensor.gaz') }} m³ ({{ states('sensor.cout_gaz') }}€)
```

## Lovelace Card Example

```yaml
type: entities
title: Octopus Energy France
entities:
  - entity: sensor.cagnotte
  - entity: binary_sensor.heures_creuses_actives
  - entity: sensor.electricite_hc
  - entity: sensor.electricite_hp
  - entity: sensor.cout_electricite_hc
  - entity: sensor.cout_electricite_hp
  - entity: sensor.gaz
  - entity: sensor.cout_gaz
```

## Energy Dashboard Integration

This integration is compatible with Home Assistant's Energy Dashboard:

1. Go to Settings → Dashboards → Energy
2. Click "Add Consumption" under Electricity grid consumption
3. Select:
   - `sensor.electricite_hc` for off-peak consumption
   - `sensor.electricite_hp` for peak consumption
4. For Gas consumption, select `sensor.gaz`

## Troubleshooting

### Sensors not appearing
- Check that your account has active electricity and/or gas contracts
- Verify your credentials are correct
- Check the Home Assistant logs for errors: Settings → System → Logs

### Data not updating
- The integration updates every 30 minutes by default
- You can manually refresh by clicking "Reload" in the integration settings
- Check your internet connection

### Authentication errors
- Verify your email and password are correct
- Try logging into the Octopus Energy France website with the same credentials
- If you recently changed your password, reconfigure the integration

### Binary sensor not working
- Ensure your electricity contract has an off-peak schedule configured
- Check the `hc_schedule_available` attribute
- Verify the off-peak hours in the sensor attributes match your contract

## Debug Logging

To enable debug logging for troubleshooting:

```yaml
logger:
  default: info
  logs:
    custom_components.octopus_french: debug
```

## API Rate Limiting

The integration respects Octopus Energy's API limits:
- Automatic token refresh before expiration
- Retry logic with exponential backoff
- Update interval of 30 minutes

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

If you encounter any issues or have questions:
- Check the [Issues](https://github.com/domodom30/ha-octopus-french/issues) page
- Create a new issue with detailed information and logs

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with or endorsed by Octopus Energy France. Use at your own risk.
