#!/usr/bin/env python3
"""
Affiche les données du compte Octopus : compteurs, accords, tarifs.

Particulièrement utile pour :
- Trouver les numéros PRM (compteurs électricité) et PCE (gaz)
- Connaître le product.code de votre contrat (ex : identifier un contrat OctoTempo)
- Voir les taux de consommation retournés par l'API

Usage :
    python tools/account.py
    python tools/account.py --account A-XXXX0000
    python tools/account.py --raw          ← dump JSON brut complet

Configuration via tools/.env :
    OCTOPUS_EMAIL, OCTOPUS_PASSWORD, OCTOPUS_ACCOUNT
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _client import OctopusClient, get_account_number, hr, print_json

QUERY_GET_ACCOUNTS = """
{
  viewer {
    accounts {
      number
      ledgers {
        balance
        ledgerType
        name
        number
      }
    }
  }
}
"""

QUERY_GET_ACCOUNT_DATA = """
query getAccountData($accountNumber: String!, $activeAt: DateTime!) {
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
                isTeleoperable
                offPeakLabel
                poweredStatus
                isSmartMeter
                isThreePhase
                circuitBreakerIntensity
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
              ... on GasMeterPoint {
                id
                gasNature
                annualConsumption
                isSmartMeter
                poweredStatus
                serial
                contractualStatus
              }
            }
          }
        }
      }
    }
    agreements(activeAt: $activeAt, first: 10) {
      edges {
        node {
          id
          validFrom
          validTo
          isActive
          supplyContractNumber
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
              currency
              pricePerUnit
              unitType
              pricePerUnitWithTaxes
            }
            consumptionRates(first: 10) {
              edges {
                node {
                  currency
                  pricePerUnit
                  unitType
                  pricePerUnitWithTaxes
                  timeSlots {
                    startAt
                    endAt
                  }
                }
              }
            }
          }
          billingFrequency
          nextPaymentForecast {
            amount
            date
          }
        }
      }
    }
  }
}
"""


def _fmt_price(
    price_unit: str | None, with_taxes: str | None, unit_type: str | None
) -> str:
    ht = float(price_unit or 0) / 100
    ttc = float(with_taxes or 0) / 100
    return f"{ttc:.4f} €/{unit_type or '?'} TTC  (HT: {ht:.4f})"


def print_account_summary(account: dict) -> None:
    """Affiche un résumé lisible d'un compte et de ses points de livraison."""
    print(f"\n{'═' * 60}")
    print(f"  Compte : {account.get('number', '?')}")
    print(f"{'═' * 60}")

    props = account.get("properties", [])
    for prop in props:
        print(f"\n📍  Propriété #{prop.get('id', '?')}  —  {prop.get('address', '')}")
        edges = prop.get("supplyPoints", {}).get("edges", [])
        for edge in edges:
            node = edge.get("node", {})
            mp = node.get("meterPoint", {})
            prm = node.get("externalIdentifier", "?")

            if "meterKind" in mp or "subscribedMaxPower" in mp:
                status = mp.get("distributorStatus", "?")
                powered = mp.get("poweredStatus", "?")
                provider_cal = mp.get("providerCalendar") or {}
                calendar_id = provider_cal.get("id", "—")
                off_peak = mp.get("offPeakLabel", "—")
                temporal_classes = provider_cal.get("temporalClasses") or []
                print(f"\n  ⚡  Électricité  PRM: {prm}")
                print(f"      Statut: {status} / Alimentation: {powered}")
                print(
                    f"      Puissance souscrite: {mp.get('subscribedMaxPower', '?')} kVA"
                )
                print(f"      Calendrier fournisseur: {calendar_id}")
                print(f"      Horaires HC (offPeakLabel): {off_peak}")
                print(f"      Compteur communicant: {mp.get('isSmartMeter', '?')}")
                print(f"      Télé-opérable: {mp.get('isTeleoperable', '?')}")
                if temporal_classes:
                    print(
                        f"      Classes temporelles du calendrier ({len(temporal_classes)}) :"
                    )
                    for tc in temporal_classes:
                        reg = (
                            f"  [registerId={tc.get('registerId')}]"
                            if tc.get("registerId")
                            else ""
                        )
                        print(
                            f"        • code={tc.get('code', '?')!r:<20} label={tc.get('label', '?')!r}{reg}"
                        )
                    if len(temporal_classes) == 6:
                        print("        ⚠️  6 classes détectées → contrat OctoTempo !")

            elif "gasNature" in mp or "serial" in mp:
                print(f"\n  🔥  Gaz  PCE: {prm}")
                print(f"      Statut: {mp.get('contractualStatus', '?')}")
                print(f"      Conso annuelle: {mp.get('annualConsumption', '?')} kWh")
                print(f"      Numéro de série: {mp.get('serial', '?')}")

    agreements = account.get("agreements", {}).get("edges", [])
    if agreements:
        print(f"\n{hr()}")
        print("  ACCORDS TARIFAIRES")
        print(hr())
        for edge in agreements:
            ag = edge.get("node", {})
            product = ag.get("product", {})
            active = "✅ actif" if ag.get("isActive") else "❌ inactif"
            sp_prm = (ag.get("supplyPoint") or {}).get("externalIdentifier", "?")

            print(f"\n  📄  Contrat #{ag.get('supplyContractNumber', '?')}  [{active}]")
            print(f"      PRM associé  : {sp_prm}")
            print(f"      Valide du    : {ag.get('validFrom', '?')}")
            print(f"      au           : {ag.get('validTo', '(en cours)')}")
            print(f"      product.code : {product.get('code', '?')}")
            print(f"      Nom produit  : {product.get('displayName', '?')}")
            print(
                f"      Facturation  : tous les {ag.get('billingFrequency', '?')} mois"
            )

            rate = ag.get("energySupplyRate") or {}
            standing = rate.get("standingRate") or {}
            if standing:
                print(
                    f"      Abonnement   : {_fmt_price(standing.get('pricePerUnit'), standing.get('pricePerUnitWithTaxes'), standing.get('unitType'))}"
                )

            consumption_edges = (rate.get("consumptionRates") or {}).get("edges", [])
            if consumption_edges:
                rates_sorted = sorted(
                    [e["node"] for e in consumption_edges],
                    key=lambda r: float(r.get("pricePerUnitWithTaxes", 0)),
                )
                print(
                    f"      Taux de conso ({len(rates_sorted)} taux, trié par prix ↑) :"
                )
                for r in rates_sorted:
                    slots = r.get("timeSlots") or []

                    slots_str = ""
                    if slots:
                        slots_str = "  horaires=" + ", ".join(
                            f"{s.get('startAt', '?')}-{s.get('endAt', '?')}"
                            for s in slots
                        )

                    print(
                        f"        {_fmt_price(r.get('pricePerUnit'), r.get('pricePerUnitWithTaxes'), r.get('unitType'))}{slots_str}"
                    )

                if len(rates_sorted) == 6:
                    print("        ⚠️  6 taux → contrat OctoTempo !")
                elif len(rates_sorted) == 2:
                    print("        → HP/HC classique")
                elif len(rates_sorted) == 1:
                    print("        → Tarif BASE")

            nxt = ag.get("nextPaymentForecast") or {}
            if nxt.get("amount"):
                amount = float(nxt["amount"]) / 100
                print(
                    f"      Prochain prélèvement : {amount:.2f} € le {nxt.get('date', '?')}"
                )


def main() -> None:
    """Point d'entrée en ligne de commande du script."""
    parser = argparse.ArgumentParser(
        description="Données du compte Octopus Energy France",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--account", help="Numéro de compte (ex: A-XXXX0000)")
    parser.add_argument(
        "--raw", action="store_true", help="Affiche le JSON brut complet"
    )
    args = parser.parse_args()

    client = OctopusClient()
    now_iso = datetime.now(UTC).isoformat()

    accounts_data = client.query(QUERY_GET_ACCOUNTS)
    accounts = accounts_data.get("data", {}).get("viewer", {}).get("accounts", [])

    if not accounts:
        print("❌  Aucun compte trouvé.", file=sys.stderr)
        sys.exit(1)

    account_number = args.account or get_account_number()
    if not account_number:
        if len(accounts) == 1:
            account_number = accounts[0]["number"]
        else:
            print("Comptes disponibles :")
            for acc in accounts:
                print(f"  - {acc['number']}")
            print("\nUtilisez --account <numéro> ou OCTOPUS_ACCOUNT=<numéro> dans .env")
            sys.exit(0)

    account_data = client.query(
        QUERY_GET_ACCOUNT_DATA,
        {"accountNumber": account_number, "activeAt": now_iso},
    )
    account = account_data.get("data", {}).get("account", {})

    if args.raw:
        print_json(account_data)
        return

    print_account_summary(account)
    print(f"\n{'═' * 60}")
    print("💡  Astuce : utilisez --raw pour le JSON complet")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
