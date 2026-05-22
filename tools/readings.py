#!/usr/bin/env python3
"""Affiche les relevés de consommation avec les labels metaData.statistics.

Particulièrement utile pour investiguer OctoTempo :
révèle les labels exacts présents dans les relevés
(ex : BASE, HEURES_PLEINES, TEMPO_BLEU_HP, TEMPO_ROUGE_HC, etc.)

Usage :
    python tools/readings.py --prm 12345678901234
    python tools/readings.py --prm 12345678901234 --days 14
    python tools/readings.py --prm 12345678901234 --property 123456 --days 7
    python tools/readings.py --prm 12345678901234 --raw

    # Pour trouver le property-id, lancez d'abord account.py
    python tools/account.py

Configuration via tools/.env :
    OCTOPUS_EMAIL, OCTOPUS_PASSWORD, OCTOPUS_ACCOUNT
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _client import OctopusClient, get_account_number, hr, print_json

# ── Requêtes GraphQL ──────────────────────────────────────────────────────────

FRAGMENT_INTERVAL_MEASUREMENT = """
fragment IntervalMeasurement on IntervalMeasurementType {
  __typename
  value
  startAt
  metaData {
    statistics {
      costInclTax {
        estimatedAmount
        costCurrency
      }
      label
      value
    }
  }
}
"""

QUERY_GET_MEASUREMENTS = FRAGMENT_INTERVAL_MEASUREMENT + """
query GetPropertyMeasurements(
  $propertyId: ID!
  $startAt: DateTime!
  $endAt: DateTime!
  $utilityFilters: [UtilityFiltersInput]!
  $first: Int
  $after: String
) {
  property(id: $propertyId) {
    measurements(
      startAt: $startAt
      endAt: $endAt
      first: $first
      after: $after
      utilityFilters: $utilityFilters
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          ...IntervalMeasurement
        }
      }
    }
  }
}
"""

QUERY_GET_ACCOUNT_FOR_PROPERTY = """
query getAccountData($accountNumber: String!, $activeAt: DateTime!) {
  account(accountNumber: $accountNumber) {
    properties {
      id
      address
      supplyPoints(first: 10) {
        edges {
          node {
            id
            externalIdentifier
            meterPoint {
              ... on ElectricityMeterPoint {
                id
              }
            }
          }
        }
      }
    }
  }
}
"""


# ── Logique de recherche de property_id ──────────────────────────────────────

def find_property_id_for_prm(client: OctopusClient, account_number: str, prm: str) -> str | None:
    """Cherche le property_id associé à un PRM dans les données de compte."""
    now_iso = datetime.now(timezone.utc).isoformat()
    data = client.query(
        QUERY_GET_ACCOUNT_FOR_PROPERTY,
        {"accountNumber": account_number, "activeAt": now_iso},
    )
    props = data.get("data", {}).get("account", {}).get("properties", [])
    for prop in props:
        for edge in prop.get("supplyPoints", {}).get("edges", []):
            node = edge.get("node", {})
            if node.get("externalIdentifier") == prm:
                return prop.get("id")
    return None


# ── Affichage des relevés ─────────────────────────────────────────────────────

def print_readings(readings: list[dict], prm: str) -> None:
    """Affiche un résumé lisible des relevés avec leurs labels."""
    # Collecter tous les labels uniques rencontrés
    all_labels: set[str] = set()
    for r in readings:
        for stat in (r.get("metaData") or {}).get("statistics", []):
            lbl = stat.get("label")
            if lbl:
                all_labels.add(lbl)

    print(f"\n{'═' * 65}")
    print(f"  Relevés pour PRM : {prm}  ({len(readings)} jours)")
    print(f"{'═' * 65}")
    print(f"\n📊  Labels présents dans metaData.statistics :")
    if all_labels:
        for lbl in sorted(all_labels):
            marker = "⚠️ " if "TEMPO" in lbl.upper() else "   "
            print(f"    {marker}{lbl}")
    else:
        print("    (aucun label trouvé)")

    # Détection OctoTempo
    tempo_labels = {l for l in all_labels if "TEMPO" in l.upper()}
    if tempo_labels:
        print(f"\n🎨  Labels Tempo détectés : {', '.join(sorted(tempo_labels))}")
        print("    → Ce compte semble avoir l'offre OctoTempo !")

    print(f"\n{hr()}")
    print("  DÉTAIL PAR JOUR")
    print(hr())

    for reading in sorted(readings, key=lambda r: r.get("startAt", ""), reverse=True):
        date = reading.get("startAt", "?")[:10]
        total = reading.get("value")
        total_str = f"{float(total):.3f} kWh" if total is not None else "—"

        print(f"\n  📅  {date}  |  Total brut : {total_str}")
        stats = (reading.get("metaData") or {}).get("statistics", [])

        if not stats:
            print("       (aucune statistique)")
            continue

        for stat in stats:
            lbl = stat.get("label", "?")
            val = stat.get("value")
            cost_data = stat.get("costInclTax") or {}
            cost = cost_data.get("estimatedAmount")
            currency = cost_data.get("costCurrency", "EUR")

            val_str = f"{float(val):.3f} kWh" if val is not None else "—"
            cost_str = f"  →  coût: {float(cost)/100:.4f} {currency}" if cost is not None else ""
            marker = "⚠️ " if "TEMPO" in lbl.upper() else "   "
            print(f"      {marker}{lbl:<30} {val_str}{cost_str}")

    print()


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Relevés de consommation avec labels metaData.statistics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--prm", required=True, help="Numéro PRM du compteur électricité")
    parser.add_argument("--account", help="Numéro de compte (ex: A-XXXX0000)")
    parser.add_argument("--property", help="ID de la propriété (auto-détecté si absent)")
    parser.add_argument("--days", type=int, default=30, help="Nombre de jours (défaut: 30)")
    parser.add_argument("--raw", action="store_true", help="Affiche le JSON brut complet")
    args = parser.parse_args()

    client = OctopusClient()
    account_number = args.account or get_account_number()

    if not account_number:
        print("❌  Numéro de compte requis (--account ou OCTOPUS_ACCOUNT dans .env)", file=sys.stderr)
        sys.exit(1)

    # Trouver le property_id si non fourni
    property_id = args.property
    if not property_id:
        print(f"🔍  Recherche de la propriété pour le PRM {args.prm}...")
        property_id = find_property_id_for_prm(client, account_number, args.prm)
        if not property_id:
            print(
                f"❌  Propriété non trouvée pour PRM={args.prm}.\n"
                f"    Vérifiez le PRM ou utilisez --property <id>\n"
                f"    (Lancez 'python tools/account.py' pour voir les propriétés)",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"    → Propriété trouvée : {property_id}")

    now = datetime.now(timezone.utc)
    start_at = (now - timedelta(days=args.days)).isoformat()
    end_at = now.isoformat()

    print(f"📥  Récupération des relevés ({args.days} derniers jours)...")

    # Pagination
    all_readings: list[dict] = []
    after: str | None = None

    while True:
        variables = {
            "propertyId": property_id,
            "startAt": start_at,
            "endAt": end_at,
            "utilityFilters": [{"electricityFilters": {"readingFrequencyType": "DAY_INTERVAL"}}],
            "first": 100,
            "after": after,
        }
        data = client.query(QUERY_GET_MEASUREMENTS, variables)
        measurements = (
            data.get("data", {})
            .get("property", {})
            .get("measurements", {})
        )
        for edge in measurements.get("edges", []):
            all_readings.append(edge["node"])

        page_info = measurements.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

    if args.raw:
        print_json({"readings": all_readings, "count": len(all_readings)})
        return

    print_readings(all_readings, args.prm)
    print(f"💡  Utilisez --raw pour le JSON complet | --days N pour changer la période\n")


if __name__ == "__main__":
    main()
