# Octopus Energy France for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/domodom30/ha-octopus-french)](https://github.com/domodom30/ha-octopus-french/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_french.total)

A comprehensive Home Assistant integration for Octopus Energy France customers to monitor electricity and gas consumption, tariffs, bills, and account balance.

## Features

### 📊 Monitoring
- **Electricity consumption** (peak/off-peak hours)
- **Gas consumption**
- **Meter readings** with index tracking
- **Current tariffs** (electricity & gas)
- **Off-peak hours** detection with binary sensor

### 💰 Financial Tracking
- **Account balance** (electricity, gas, and pot ledgers)
- **Latest bills** for electricity and gas
- **Payment status** and expected payment dates
- **Cost tracking** with detailed breakdowns

### 🏠 Devices & Organization
- Separate devices for:
  - **Octopus Energy account** (balances and bills)
  - **Linky meters** (electricity)
  - **Gazpar meters** (gas)
- All entities organized by device
- Support for multiple meters

### ⚙️ Advanced Features
- **Configurable update interval** (5 to 1440 minutes)
- **Force update service** for immediate data refresh
- **Energy dashboard integration** compatible
- **Diagnostic entities** for detailed meter information
- **Contract information** with meter specifications

---

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add the repository URL: `https://github.com/domodom30/ha-octopus-french`
6. Select category: "Integration"
7. Click "Add"
8. Search for "Octopus Energy France"
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub](https://github.com/domodom30/ha-octopus-french/releases)
2. Extract the `octopus_french` folder to your `custom_components` directory
3. Restart Home Assistant

---

## Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"Octopus Energy France"**
4. Enter your Octopus Energy credentials:
   - **Email**
   - **Password**
5. Click **Submit**

### Options

After installation, you can configure:

- **Update interval**: Refresh frequency (default: 60 minutes, range: 5-1440)

To access options:
1. Go to **Settings** → **Devices & Services**
2. Find **Octopus Energy France**
3. Click **Configure**

---

## Entities

### Account Device (Compte Octopus Energy)

| Entity | Type | Description |
|--------|------|-------------|
| Pot Balance | Sensor | Pot/savings balance |
| Electricity Balance | Sensor | Current electricity account balance |
| Gas Balance | Sensor | Current gas account balance |
| Electricity Bill | Sensor | Latest electricity bill amount |
| Gas Bill | Sensor | Latest gas bill amount |

### Electricity Meter Device (Linky)

#### Main Sensors
| Entity | Type | Class | Description |
|--------|------|-------|-------------|
| HP Consumption | Sensor | Energy | Peak hours consumption (kWh) |
| Off-peak Consumption | Sensor | Energy | Off-peak hours consumption (kWh) |
| Off-peak Hours Active | Binary Sensor | Running | Current period status |

#### Diagnostic Sensors
| Entity | Type | Description |
|--------|------|-------------|
| HP Index | Sensor | Peak hours meter reading |
| Off-peak Index | Sensor | Off-peak hours meter reading |
| HP Rate | Sensor | Current peak hours tariff (€/kWh) |
| Off-peak Rate | Sensor | Current off-peak hours tariff (€/kWh) |
| Contract | Sensor | Contract details and meter info |

### Gas Meter Device (Gazpar)

#### Main Sensors
| Entity | Type | Class | Description |
|--------|------|-------|-------------|
| Consumption | Sensor | Energy | Current gas consumption (kWh) |

#### Diagnostic Sensors
| Entity | Type | Description |
|--------|------|-------------|
| Index | Sensor | Gas meter reading |
| Rate | Sensor | Current gas tariff (€/kWh) |
| Contract | Sensor | Contract details and meter info |

---

## Services

### `octopus_french.force_update`

Forces an immediate data refresh from Octopus Energy API.

**Example:**
```yaml
service: octopus_french.force_update
```

---

## Energy Dashboard Integration

This integration is fully compatible with Home Assistant's Energy Dashboard.

### Setup Instructions

1. Go to **Settings** → **Dashboards** → **Energy**
2. Click **"Add Consumption"**
3. Select:
   - **Electricity - Peak hours**: `sensor.linky_XXXXXX_consumption_hp`
   - **Electricity - Off-peak hours**: `sensor.linky_XXXXXX_consumption_hc`
   - **Gas**: `sensor.gazpar_XXXXXX_consumption`

### Individual Costs

For each consumption sensor, you can configure the cost:
1. Click on the sensor in Energy Dashboard
2. Enable **"Use a static price"** or link to the tariff sensor
3. For electricity:
   - HP: Link to `sensor.linky_XXXXXX_tarif_hp`
   - Off-peak: Link to `sensor.linky_XXXXXX_tarif_hc`
4. For gas:
   - Link to `sensor.gazpar_XXXXXX_tarif`

---

## Attributes Details

### Contract Sensor Attributes

#### Electricity Contract
- `prm_id`: Point Reference Meter identifier
- `ledger_id`: Associated ledger number
- `distributor_status`: SERVC (In service) / RESIL (Terminated)
- `meter_kind`: Meter type (Linky)
- `subscribed_max_power`: Subscribed power (kVA)
- `is_teleoperable`: Remote control capability
- `off_peak_label`: Off-peak hours schedule
- `powered_status`: Power status (ALIM/LIMI)

#### Gas Contract
- `pce_ref`: PCE reference number
- `ledger_id`: Associated ledger number
- `gas_nature`: Natural/Propane
- `annual_consumption`: Estimated annual consumption
- `is_smart_meter`: Communicating meter (Gazpar)
- `powered_status`: Connection status
- `price_level`: Pricing tier
- `tariff_option`: Tariff option

### Bill Sensor Attributes
- `payment_status`: Payment status
- `total_amount`: Total bill amount
- `customer_amount`: Customer portion
- `expected_payment_date`: Expected payment date

### Consumption/Index Attributes
- `period_start`: Reading period start
- `period_end`: Reading period end
- `reliability`: Data reliability (REAL)
- `status`: Processing status (OK)

### Off-peak Hours Binary Sensor
- `hc_schedule_available`: Schedule availability
- `total_hc_hours`: Total off-peak hours per day
- `hc_type`: Schedule type
- `hc_range_1`, `hc_range_2`, etc.: Individual time ranges

---

## Automation Examples

### Notification when entering off-peak hours
```yaml
automation:
  - alias: "Off-peak Hours Started"
    trigger:
      - platform: state
        entity_id: binary_sensor.linky_XXXXXX_heures_creuses_actives
        to: "on"
    action:
      - service: notify.notify
        data:
          title: "⚡ Off-peak Hours"
          message: "Off-peak hours have started. Good time to run energy-intensive appliances!"
```

### High bill alert
```yaml
automation:
  - alias: "High Bill Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.compte_octopus_energy_facture_electricite
        above: 100
    action:
      - service: notify.notify
        data:
          title: "💰 High Bill Alert"
          message: "Your electricity bill is {{ states('sensor.compte_octopus_energy_facture_electricite') }}€"
```

### Daily consumption report
```yaml
automation:
  - alias: "Daily Consumption Report"
    trigger:
      - platform: time
        at: "20:00:00"
    action:
      - service: notify.notify
        data:
          title: "📊 Daily Consumption"
          message: >
            HP: {{ states('sensor.linky_XXXXXX_consumption_hp') }} kWh
            Off-peak: {{ states('sensor.linky_XXXXXX_consumption_hc') }} kWh
            Gas: {{ states('sensor.gazpar_XXXXXX_consumption') }} kWh
```

---

## Troubleshooting

### Entities not appearing
- Verify your credentials are correct
- Check that your account has active meters
- Restart Home Assistant after installation

### Data not updating
- Check the update interval in configuration options
- Use the `force_update` service to trigger immediate refresh
- Verify API connectivity in Home Assistant logs

### Terminated meters
- Terminated meters (RESIL status) are automatically excluded
- Only active meters appear in the integration

### Missing consumption data
- Some data may take 24-48h to appear after meter installation
- Check Octopus Energy website to verify data availability

---

## Support

- **Issues**: [GitHub Issues](https://github.com/domodom30/ha-octopus-french/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/domodom30/ha-octopus-french/discussions)

---