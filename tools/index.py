#!/usr/bin/env python3
"""Affiche l'index électrique Linky (temporalClass, calendarTempClass, valeurs d'index…).

Particulièrement utile pour OctoTempo :
- Révèle les valeurs réelles de `temporalClass.code` (champ structuré, prioritaire)
  et `calendarTempClass` (champ legacy, en fallback)
  (HP, HC, BASE, BLEU_HP, BLEU_HC… selon le type de contrat)
- Affiche les valeurs d'index de début/fin et la consommation journalière

Usage :
    python tools/index.py --account A-XXXX0000 --prm 12345678901234
    python tools/index.py --account A-XXXX0000 --prm 12345678901234 --first 10
    python tools/index.py --account A-XXXX0000 --prm 12345678901234 --raw

Configuration via tools/.env :
    OCTOPUS_EMAIL, OCTOPUS_PASSWORD, OCTOPUS_ACCOUNT
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _client import OctopusClient, get_account_number, hr, print_json


QUERY_GET_INDEX_ELECTRICITY = """
query getElectricityIndex($accountNumber: String!, $prmId: String!, $first: Int!) {
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


_COLOR_MAP = {
    "BLEU":  "\033[94m",
    "BLANC": "\033[97m",
    "ROUGE": "\033[91m",
    "HP":    "\033[93m",
    "HC":    "\033[96m",
    "BASE":  "\033[92m",
}
_RESET = "\033[0m"


def _color(text: str, key: str) -> str:
    """Applique une couleur ANSI si disponible."""
    code = _COLOR_MAP.get(key, "")
    return f"{code}{text}{_RESET}" if code else text



def _get_temporal_code(entry: dict) -> tuple[str, str]:
    """Retourne (code, source) depuis temporalClass ou calendarTempClass (fallback).

    source est 'temporalClass' ou 'calendarTempClass' pour affichage.
    """
    tc_obj = entry.get("temporalClass") or {}
    code = tc_obj.get("code")
    if code:
        return code, "temporalClass"
    legacy = entry.get("calendarTempClass")
    if legacy:
        return legacy, "calendarTempClass"
    return "—", "—"


def print_index(entries: list[dict], prm: str) -> None:
    """Affiche les entrées d'index de façon lisible."""
    all_codes: set[str] = set()
    for e in entries:
        code, _ = _get_temporal_code(e)
        if code != "—":
            all_codes.add(code)

    print(f"\n{'═' * 65}")
    print(f"  Index électrique Linky  —  PRM : {prm}  ({len(entries)} entrées)")
    print(f"{'═' * 65}")
    print(f"\n🔍  Codes temporels rencontrés (temporalClass.code / calendarTempClass) :")
    if all_codes:
        for cls in sorted(all_codes):
            print(f"    → {_color(cls, cls)}")
    else:
        print("    (champ absent ou vide)")

    tempo_colors = {c for c in all_codes if any(col in c for col in ("BLEU", "BLANC", "ROUGE"))}
    if tempo_colors:
        print(f"\n🎨  Classes Tempo détectées : {', '.join(sorted(tempo_colors))}")
        print("    → Ce compteur est sur un contrat OctoTempo !")
    elif any(c in all_codes for c in ("HP", "HC")):
        print("\n    → Contrat HP/HC classique")
    elif "BASE" in all_codes:
        print("\n    → Contrat BASE")

    print(f"\n{hr()}")
    print("  DÉTAIL DES ENTRÉES  (de la plus récente à la plus ancienne)")
    print(hr())

    for entry in entries:
        period_start = (entry.get("periodStartAt") or "?")[:10]
        period_end = (entry.get("periodEndAt") or "?")[:10]
        cal_type = entry.get("calendarType") or "—"
        conso = entry.get("consumption")
        idx_start = entry.get("indexStartValue")
        idx_end = entry.get("indexEndValue")
        status = entry.get("statusProcessed") or "?"
        conso_rel = entry.get("consumptionReliability") or "?"
        idx_rel = entry.get("indexReliability") or "?"

        tc_code, tc_source = _get_temporal_code(entry)
        tc_obj = entry.get("temporalClass") or {}
        tc_label = tc_obj.get("label", "")
        tc_register = tc_obj.get("registerId")
        legacy_tc = entry.get("calendarTempClass") or "—"

        conso_str = f"{float(conso):.3f} kWh" if conso is not None else "—"
        idx_str = (
            f"{idx_start} → {idx_end} kWh"
            if idx_start is not None and idx_end is not None
            else "— (index non disponible)"
        )

        color_key = tc_code
        for k in ("BLEU", "BLANC", "ROUGE"):
            if k in tc_code:
                color_key = k
                break

        tc_display = _color(tc_code, color_key)
        label_str = f"  ({tc_label})" if tc_label else ""
        reg_str = f"  [registerId={tc_register}]" if tc_register else ""

        print(f"\n  📅  {period_start} → {period_end}")
        if tc_source == "temporalClass":
            print(f"      temporalClass.code : {tc_display}{label_str}{reg_str}")
            if legacy_tc != "—":
                print(f"      calendarTempClass  : {legacy_tc}  (legacy)")
        else:
            print(f"      calendarTempClass  : {tc_display}")
            print(f"      temporalClass      : (absent)")
        print(f"      calendarType       : {cal_type}")
        print(f"      Consommation       : {conso_str}  (fiabilité: {conso_rel})")
        print(f"      Index              : {idx_str}  (fiabilité: {idx_rel})")
        print(f"      Statut             : {status}")

    print()



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index électrique Linky avec calendarTempClass",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--account", help="Numéro de compte (ex: A-XXXX0000)")
    parser.add_argument("--prm", required=True, help="Numéro PRM du compteur")
    parser.add_argument("--first", type=int, default=5, help="Nombre d'entrées (défaut: 5)")
    parser.add_argument("--raw", action="store_true", help="Affiche le JSON brut complet")
    args = parser.parse_args()

    client = OctopusClient()
    account_number = args.account or get_account_number()

    if not account_number:
        print("❌  Numéro de compte requis (--account ou OCTOPUS_ACCOUNT dans .env)", file=sys.stderr)
        sys.exit(1)

    print(f"📥  Récupération de l'index électrique (PRM: {args.prm}, {args.first} entrées)...")

    variables = {
        "accountNumber": account_number,
        "prmId": args.prm,
        "first": args.first,
    }
    data = client.query(QUERY_GET_INDEX_ELECTRICITY, variables)
    edges = (
        data.get("data", {})
        .get("electricityReading", {})
        .get("edges", [])
    )
    entries = [e["node"] for e in edges]

    if args.raw:
        print_json({"entries": entries, "count": len(entries)})
        return

    if not entries:
        print("⚠️   Aucune entrée retournée par l'API pour ce PRM.")
        return

    print_index(entries, args.prm)
    print(f"💡  Utilisez --first N pour voir plus d'entrées | --raw pour le JSON complet\n")


if __name__ == "__main__":
    main()
