#!/usr/bin/env python3
"""
Collecte complète d'un contrat OctoTempo / OctoFlex, anonymisée.

Rassemble en une seule commande tout ce qu'il faut pour diagnostiquer la
couleur Tempo (issue #84) :

- le calendrier fournisseur et les descriptions de classes temporelles
  (ce sont elles qui portent les bornes de saison : « Avril à octobre »…) ;
- `offPeakValues`, qui donnerait ces mêmes bornes sous forme structurée ;
- les tarifs souscrits avec leur `temporalClass` et leurs créneaux ;
- 90 relevés d'index, soit une quinzaine de jours sur un contrat à six
  registres — l'intégration n'en demande que 8, ce qui masquait le problème ;
- 60 jours de relevés quotidiens avec leurs labels `metaData.statistics`.

Le PRM, le numéro de compte, l'adresse, l'e-mail et les identifiants internes
sont remplacés par des jetons stables avant écriture : le fichier produit peut
être joint tel quel à une issue GitHub.

Usage :
    python tools/octoflex.py
    python tools/octoflex.py --prm 12345678901234
    python tools/octoflex.py --days 90 --first 120
    python tools/octoflex.py --output mon-diagnostic.json

Configuration via tools/.env :
    OCTOPUS_EMAIL, OCTOPUS_PASSWORD, OCTOPUS_ACCOUNT
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _client import OctopusClient, get_account_number, hr
from readings import QUERY_GET_MEASUREMENTS

QUERY_OCTOFLEX_ACCOUNT = """
query OctoflexAccount($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    properties {
      id
      address
      supplyPoints(first: 10) {
        edges {
          node {
            id
            externalIdentifier
            marketName
            meterPoint {
              ... on ElectricityMeterPoint {
                id
                distributorStatus
                meterKind
                subscribedMaxPower
                offPeakLabel
                offPeakValues {
                  label
                  seasonCode
                  season {
                    code
                    name
                    startDay
                    startMonth
                    endDay
                    endMonth
                  }
                }
                providerCalendar {
                  id
                  name
                  temporalClasses {
                    code
                    label
                    description
                    registerId
                  }
                }
              }
            }
          }
        }
      }
    }
    agreements(first: 10) {
      edges {
        node {
          validFrom
          validTo
          isActive
          supplyPoint {
            id
            externalIdentifier
          }
          product {
            code
            fullName
            displayName
          }
          energySupplyRate {
            standingRate {
              pricePerUnit
              pricePerUnitWithTaxes
              unitType
            }
            rates(first: 20) {
              edges {
                node {
                  __typename
                  pricePerUnit
                  pricePerUnitWithTaxes
                  unitType
                  validFrom
                  validTo
                  ... on ElectricitySupplyConsumptionRateType {
                    timeSlots {
                      startAt
                      endAt
                    }
                    temporalClass {
                      code
                      label
                      description
                      registerId
                    }
                  }
                  ... on ElectricityConsumptionRateType {
                    temporalClass {
                      code
                      label
                      description
                      registerId
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

QUERY_INDEX = """
query OctoflexIndex($accountNumber: String!, $prmId: String!, $first: Int!) {
  electricityReading(
    accountNumber: $accountNumber
    prmId: $prmId
    first: $first
    calendarType: PROVIDER
  ) {
    edges {
      node {
        consumption
        periodStartAt
        periodEndAt
        indexStartValue
        indexEndValue
        statusProcessed
        calendarType
        calendarTempClass
        consumptionReliability
        indexReliability
        temporalClass {
          ... on ProviderTemporalClassType {
            code
            label
            description
            registerId
          }
          ... on DistributorTemporalClassType {
            code
          }
        }
      }
    }
  }
}
"""

# Plafond de pagination de `electricityReading`, mesuré sur l'API.
API_MAX_READINGS = 100

# Couleur OctoTempo portée par chaque registre du calendrier fournisseur.
REGISTER_TO_COLOR = {
    "HPE": "ETE",
    "HCE": "ETE",
    "HPHI": "HIVER",
    "HCHI": "HIVER",
    "HPP": "ROUGE",
    "HCP": "ROUGE",
}


class Anonymizer:
    """Remplace les données identifiantes par des jetons stables et lisibles."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def token(self, value: str | None, kind: str) -> str | None:
        """Retourne un jeton stable pour une valeur donnée."""
        if not value:
            return value
        if value not in self._tokens:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            self._tokens[value] = f"<{kind}_{self._counters[kind]}>"
        return self._tokens[value]

    def scrub(self, obj: Any) -> Any:
        """Applique les jetons connus à toute chaîne d'une structure JSON."""
        if isinstance(obj, dict):
            return {key: self.scrub(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self.scrub(item) for item in obj]
        if isinstance(obj, str):
            for clear, token in self._tokens.items():
                if clear and clear in obj:
                    obj = obj.replace(clear, token)
            return obj
        return obj

    def collect(self, account: dict[str, Any], email: str) -> None:
        """Repère dans les données de compte tout ce qui doit être masqué."""
        self.token(email, "EMAIL")
        self.token(account.get("number"), "COMPTE")
        for prop in account.get("properties") or []:
            self.token(prop.get("id"), "PROPRIETE")
            self.token(prop.get("address"), "ADRESSE")
            for edge in (prop.get("supplyPoints") or {}).get("edges") or []:
                node = edge.get("node") or {}
                self.token(node.get("externalIdentifier"), "PRM")
                self.token(node.get("id"), "POINT")
                self.token((node.get("meterPoint") or {}).get("id"), "COMPTEUR")


def find_electricity_supply_points(account: dict[str, Any]) -> list[dict[str, Any]]:
    """Retourne les points de livraison électricité, avec leur propriété."""
    found = []
    for prop in account.get("properties") or []:
        for edge in (prop.get("supplyPoints") or {}).get("edges") or []:
            node = edge.get("node") or {}
            meter_point = node.get("meterPoint") or {}
            if "providerCalendar" not in meter_point:
                continue
            found.append(
                {
                    "prm": node.get("externalIdentifier"),
                    "property_id": prop.get("id"),
                    "meter_point": meter_point,
                }
            )
    return found


def fetch_measurements(
    client: OctopusClient, property_id: str, days: int
) -> list[dict[str, Any]]:
    """Récupère les relevés quotidiens sur la fenêtre demandée."""
    now = datetime.now(UTC)
    variables = {
        "propertyId": property_id,
        "startAt": (now - timedelta(days=days)).isoformat(),
        "endAt": now.isoformat(),
        "utilityFilters": [
            {"electricityFilters": {"readingFrequencyType": "DAY_INTERVAL"}}
        ],
        "first": 100,
        "after": None,
    }
    readings: list[dict[str, Any]] = []
    while True:
        data = client.query(QUERY_GET_MEASUREMENTS, variables)
        measurements = ((data.get("data") or {}).get("property") or {}).get(
            "measurements"
        ) or {}
        readings.extend(
            edge["node"] for edge in measurements.get("edges") or [] if edge.get("node")
        )
        page_info = measurements.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return readings
        variables["after"] = page_info.get("endCursor")


def color_by_day(index_edges: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Somme la consommation par couleur et par journée relevée."""
    totals: dict[str, dict[str, float]] = {}
    for edge in index_edges:
        node = edge.get("node") or {}
        code = ((node.get("temporalClass") or {}).get("code")) or node.get(
            "calendarTempClass"
        )
        color = REGISTER_TO_COLOR.get((code or "").upper())
        if not color:
            continue
        day = (node.get("periodStartAt") or "")[:10]
        try:
            consumption = float(node.get("consumption") or 0)
        except (TypeError, ValueError):
            consumption = 0.0
        totals.setdefault(day, {})
        totals[day][color] = totals[day].get(color, 0.0) + consumption
    return totals


def report(
    meter_point: dict[str, Any],
    product_codes: list[str],
    index_edges: list[dict[str, Any]],
    measurements: list[dict[str, Any]],
) -> None:
    """Affiche le résumé lisible qui répond aux questions de l'issue #84."""
    print(f"\n{'═' * 68}")
    print("  RÉSUMÉ OCTOFLEX")
    print(f"{'═' * 68}")

    calendar = meter_point.get("providerCalendar") or {}
    classes = calendar.get("temporalClasses") or []
    print(
        f"\n📅  Calendrier fournisseur : {calendar.get('id')} — {calendar.get('name')}"
    )
    for temporal_class in classes:
        code = temporal_class.get("code")
        color = REGISTER_TO_COLOR.get((code or "").upper(), "—")
        print(
            f"    {code:<6} [{color:<6}] {temporal_class.get('description') or '(vide)'}"
        )

    off_peak_values = meter_point.get("offPeakValues") or []
    print(f"\n🌓  offPeakValues : {len(off_peak_values)} entrée(s)")
    for value in off_peak_values:
        season = value.get("season") or {}
        bounds = (
            f"{season.get('startDay')}/{season.get('startMonth')}"
            f" → {season.get('endDay')}/{season.get('endMonth')}"
        )
        print(f"    {value.get('seasonCode'):<10} {bounds:<16} {value.get('label')}")
    if not off_peak_values:
        print(
            "    (vide — les bornes de saison devront être lues dans les descriptions)"
        )

    print(f"\n📦  product.code : {', '.join(product_codes) or '(aucun)'}")

    totals = color_by_day(index_edges)
    print(f"\n🎨  Couleur par journée relevée ({len(totals)} jours) :")
    for day in sorted(totals, reverse=True):
        parts = " ".join(
            f"{color}={consumed:.3f}" for color, consumed in sorted(totals[day].items())
        )
        consumed_colors = [c for c, v in totals[day].items() if v > 0]
        verdict = consumed_colors[0] if len(consumed_colors) == 1 else "?"
        print(f"    {day}  →  {verdict:<6}  ({parts})")

    red_days = [
        day
        for day, colors in totals.items()
        if [c for c, v in colors.items() if v > 0] == ["ROUGE"]
    ]
    print(f"\n🔴  Journées entièrement ROUGE : {len(red_days)}")
    if red_days:
        print(f"    {', '.join(sorted(red_days, reverse=True))}")

    if totals:
        latest = max(totals)
        lag = (date.today() - date.fromisoformat(latest)).days
        print(f"\n⏱️   Dernier relevé d'index : {latest} ({lag} jour(s) de décalage)")

    labels = {
        stat.get("label")
        for reading in measurements
        for stat in (reading.get("metaData") or {}).get("statistics") or []
        if stat.get("label")
    }
    print(f"\n🏷️   Labels de relevés ({len(labels)}) : {', '.join(sorted(labels))}")
    print()


def main() -> None:
    """Point d'entrée en ligne de commande du script."""
    parser = argparse.ArgumentParser(
        description="Collecte anonymisée d'un contrat OctoTempo / OctoFlex",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--account", help="Numéro de compte (ex: A-XXXX0000)")
    parser.add_argument("--prm", help="PRM à collecter (défaut : le premier trouvé)")
    parser.add_argument(
        "--first",
        type=int,
        default=90,
        help="Relevés d'index à demander (défaut: 90, maximum 100)",
    )
    parser.add_argument(
        "--days", type=int, default=60, help="Jours de relevés quotidiens (défaut: 60)"
    )
    parser.add_argument(
        "--output",
        default="octoflex-diagnostic.json",
        help="Fichier de sortie (défaut: octoflex-diagnostic.json)",
    )
    parser.add_argument(
        "--no-anonymize",
        action="store_true",
        help="Conserve les données identifiantes — à ne PAS partager",
    )
    args = parser.parse_args()

    # Au-delà de 100, l'API répond « Invalid pagination parameters ».
    if args.first > API_MAX_READINGS:
        print(f"⚠️   --first ramené à {API_MAX_READINGS}, maximum accepté par l'API.")
        args.first = API_MAX_READINGS

    client = OctopusClient()
    account_number = args.account or get_account_number()
    if not account_number:
        print(
            "❌  Numéro de compte requis (--account ou OCTOPUS_ACCOUNT dans .env)",
            file=sys.stderr,
        )
        sys.exit(1)

    print("📥  Compte, calendrier fournisseur et tarifs...")
    account_data = client.query(
        QUERY_OCTOFLEX_ACCOUNT, {"accountNumber": account_number}
    )
    account = (account_data.get("data") or {}).get("account") or {}

    supply_points = find_electricity_supply_points(account)
    if not supply_points:
        print("❌  Aucun point de livraison électricité trouvé.", file=sys.stderr)
        sys.exit(1)

    selected = next(
        (point for point in supply_points if point["prm"] == args.prm),
        supply_points[0] if not args.prm else None,
    )
    if selected is None:
        available = ", ".join(point["prm"] or "?" for point in supply_points)
        print(
            f"❌  PRM {args.prm} introuvable. Disponibles : {available}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"    → PRM sélectionné : {selected['prm']}")

    print(f"📥  Relevés d'index ({args.first} entrées)...")
    index_data = client.query(
        QUERY_INDEX,
        {
            "accountNumber": account_number,
            "prmId": selected["prm"],
            "first": args.first,
        },
    )
    index_edges = ((index_data.get("data") or {}).get("electricityReading") or {}).get(
        "edges"
    ) or []
    print(f"    → {len(index_edges)} entrées reçues")

    print(f"📥  Relevés quotidiens ({args.days} jours)...")
    measurements = fetch_measurements(client, selected["property_id"], args.days)
    print(f"    → {len(measurements)} journées reçues")

    product_codes = [
        code
        for edge in (account.get("agreements") or {}).get("edges") or []
        if (code := ((edge.get("node") or {}).get("product") or {}).get("code"))
    ]

    report(selected["meter_point"], product_codes, index_edges, measurements)

    bundle: dict[str, Any] = {
        "collected_at": datetime.now(UTC).isoformat(),
        "account": account,
        "index": {"prm": selected["prm"], "edges": index_edges},
        "measurements": measurements,
    }

    if not args.no_anonymize:
        anonymizer = Anonymizer()
        anonymizer.collect(account, client.email)
        bundle = anonymizer.scrub(bundle)
        # Filet de sécurité : tout PRM à 14 chiffres qui aurait échappé aux jetons.
        serialized = re.sub(r"\b\d{14}\b", "<PRM_INCONNU>", json.dumps(bundle))
        bundle = json.loads(serialized)

    output = Path(args.output)
    # `ensure_ascii=False` garde les descriptions accentuées du calendrier : sans
    # encodage explicite, Windows les écrit dans la locale (cp1252) et le fichier
    # produit n'est plus du JSON lisible ailleurs.
    output.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
        newline="\n",
    )

    print(hr())
    print(f"  ✅  Écrit dans {output.resolve()}")
    if args.no_anonymize:
        print("  ⚠️   Données NON anonymisées — ne partagez pas ce fichier tel quel.")
    else:
        print("  Le fichier est anonymisé : il peut être joint à une issue GitHub.")
    print(hr())


if __name__ == "__main__":
    main()
