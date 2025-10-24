5 000 / 5 000
# Octopus Energy France for Home Assistant

[![GitHub Release](https://img.shields.io/github/release/domodom30/ha-octopus-french)](https://github.com/domodom30/ha-octopus-french/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_french.total)

Complete Home Assistant integration for Octopus Energy France customers allowing monitoring of Electricity and gas consumption, rates, bills, and account balances.

## Features

### 📊 Monitoring
- **Electricity Consumption** (peak/off-peak hours)
- **Gas Consumption**
- **Meter Readings** with Index Monitoring
- **Current Rates** (Electricity & Gas)
- **Off-peak Detection** with Binary Sensor

### 💰 Financial Monitoring
- **Account Balance** (Electricity, Gas, and Savings Pot)
- **Latest Bills** for Electricity and Gas
- **Payment Status** and Due Dates

### 🏠 Devices & Organization
- Separate devices for:
- **Octopus Energy Account** (Balances and Bills)
- **Linky or Other Meters** (Electricity)
- **Gazpar or Other Meters** (Gas)
- All Entities Organized by Device

### ⚙️ Advanced Features
- **Configurable Update Interval** (5 to 1440 minutes)
- **Forced Update Service** for immediate refresh
- **Compatible with the Energy Dashboard**
- **Diagnostic Entities** for detailed information
---

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domodom30&repository=ha-octopus-french&category=integration)

### Manual Installation

1. Download the latest version from [GitHub](https://github.com/domodom30/ha-octopus-french/releases)
2. Extract the `octopus_french` folder into your home directory. `custom_components`
3. Restart Home Assistant

---

## Configuration

### Initial Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **Octopus Energy France**
4. Enter your Octopus Energy credentials:
- **Email**
- **Password**
5. Click **Submit**

### Options

After installation, you can configure:

- **Update Interval**: Refresh rate (default: 60 minutes, range: 5-1440)

To access the options:
1. Go to **Settings** → **Devices & Services**
2. Find **Octopus Energy France**
3. Click **Configure**

---

## Entities

### Device Account (Octopus Energy Account)

| Entity | Type | Description |
|--------|------|-------------|
| Money Pot | Sensor | Money Pot Balance |
| Electricity Balance | Sensor | Current Electricity Account Balance |
| Gas Balance | Sensor | Current Gas Account Balance |
| Electricity Bill | Sensor | Last Electricity Bill Amount |
| Gas Bill | Sensor | Last Gas Bill Amount |

### Electricity Meter Device (Linky)

#### Main Sensors
| Entity | Type | Class | Description |
|--------|------|--------|-------------|
| HP Consumption | Sensor | Energy | Peak Consumption (kWh) / month |
| HC Consumption | Sensor | Energy | Off-peak Consumption (kWh) / month |
| Active Off-peak Hours | Binary Sensor | Running | Current Period Status |

### Diagnostic Sensors
| Entity | Type | Description |
|--------|------|-------------|
| HP Index | Sensor | Peak Hours Meter Reading |
| HC Index | Sensor | Off-Peak Hours Meter Reading |
| HP Tariff | Sensor | Current Peak Hours Tariff (€/kWh) |
| HC Tariff | Sensor | Current Off-Peak Hours Tariff (€/kWh) |
| Contract | Sensor | Contract Details and Meter Information |

### Gas Meter Device (Gazpar)

#### Main Sensors
| Entity | Type | Class | Description |
|--------|------|--------|-------------|
| Consumption | Sensor | Energy | Current Gas Consumption (kWh) |

#### Diagnostic Sensors
| Entity | Type | Description |
|--------|------|-------------|
| Index | Sensor | Gas Meter Reading |
| Tariff | Sensor | Current Gas Tariff (€/kWh) |
| Contract | Sensor | Contract Details and Meter Info |

---

## Services

### `octopus_french.force_update`

Forces an immediate data refresh from the Octopus Energy API.

**Example:**
```yaml
service: octopus_french.force_update
```

---

## Energy Dashboard Integration

This integration is fully compatible with the Energy Dashboard
Envoyer des commentaires
Utilisez les flèches pour afficher la traduction complète.
Résultats de traduction disponibles