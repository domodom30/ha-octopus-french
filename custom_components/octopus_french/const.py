from homeassistant.components.sensor import SensorStateClass, SensorDeviceClass

"""Constants for the Octopus Energy French integration."""

DOMAIN = "octopus_french"
PACKAGE_NAME = "custom_components.octopus_french"
ATTRIBUTION = "Data provided by Octopus Energy French"

GRAPH_QL_ENDPOINT = "https://api.oefr-kraken.energy/v1/graphql/"

SOLAR_WALLET_LEDGER = "SOLAR_WALLET_LEDGER"
POT_WALLET_LEDGER = "POT_LEDGER"
ELECTRICITY_LEDGER = "FRA_ELECTRICITY_LEDGER"
GAZ_LEDGER = "FRA_GAS_LEDGER"


SUPPORTED_LEDGER_TYPES = {
    "SOLAR_WALLET_LEDGER": {
        "balance_key": "solar_wallet",
        "create_sensor": True,
        "sensor_name": "Portefeuille Solaire",
        "unit": "€",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
    },
    "POT_LEDGER": {
        "balance_key": "pot", 
        "create_sensor": True,
        "sensor_name": "Cagnotte",
        "unit": "€",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
    },
    "FRA_ELECTRICITY_LEDGER": {
        "balance_key": "electricity",
        "create_sensor": True,
        "sensor_name": "Électricité",
        "unit": "€",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
    },
    "FRA_GAS_LEDGER": {
        "balance_key": "gas",
        "create_sensor": True,
        "sensor_name": "Gaz",
        "unit": "€",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.TOTAL,
    },
}


# Clés de configuration (strings)
CONF_SCAN_INTERVAL = "scan_interval"
CONF_GAS_CONVERSION_FACTOR = "gas_conversion_factor"

# Valeurs par défaut
DEFAULT_SCAN_INTERVAL = 1
DEFAULT_GAS_CONVERSION = 11

# Configuration
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_ACCOUNT_NUMBER = "account_number"

# GraphQL Queries
QUERY_GET_ACCOUNTS = """
query getAccountNumber { 
    viewer { 
        accounts { 
            number 
            status 
        } 
    } 
}
"""

QUERY_GET_LEDGERS = """
query ledger($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    ledgers {
      ledgerType
      name
      number
      balance
    }
    properties {
      id
    }
  }
  supplyPoints(accountNumber: $accountNumber) {
    edges {
      node {
        id
        externalIdentifier
        marketName
        meterPoint {
          id
          propertyId
        }
      }
    }
  }
}
"""

MUTATION_LOGIN = """
mutation obtainKrakenToken($input: ObtainJSONWebTokenInput!) {
    obtainKrakenToken(input: $input) {
        token
    }
}
"""

QUERY_CAGNOTTE = """
query getPot ($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    id
    creditStorage {
      ledger {
        currentBalance
        ledgerType
        name
        number
      }
    }
  }
}
"""

QUERY_SUPPLY_POINTS = """
query getSupplyPoints($accountNumber: String!) {
    account(accountNumber: $accountNumber) {
        properties {
            supplyPoints(first: 10) {
                edges {
                    node {
                        id
                        externalIdentifier
                        marketName
                    }
                }
            }
        }
    }
}
"""

QUERY_GAS_READINGS = """
query gasReadings($accountNumber: String!, $pceRef: String!, $first: Int!) {
    gasReading(accountNumber: $accountNumber, pceRef: $pceRef, first: $first) {
        edges {
            node {
                consumption
                readingDate
                indexStartValue
                indexEndValue
                statusProcessed
                readingType
                energyQualification
            }
        }
    }
}
"""

QUERY_ELECTRICITY_READINGS = """
query mesureMonthElectricity($accountNumber: String!, $prmId: String!, $first: Int!) {
    electricityReading(accountNumber: $accountNumber, prmId: $prmId, first: $first) {
        edges {
            node {
                consumption
                readingDate
                periodStartAt
                periodEndAt
                indexStartValue
                indexEndValue
                statusProcessed
                calendarType
                calendarTempClass
                consumptionReliability
                indexReliability
            }
        }
    }
}
"""