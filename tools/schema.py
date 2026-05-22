#!/usr/bin/env python3
"""Introspection du schéma GraphQL de l'API Octopus France.

Permet de découvrir les types et champs disponibles sans consulter
la documentation — utile pour trouver de nouveaux champs liés à OctoTempo
(tempoColor, dayType, label sur consumptionRates, etc.)

Usage :
    python tools/schema.py                             # liste tous les types
    python tools/schema.py --type ElectricityReadingType
    python tools/schema.py --type ElectricityMeterPoint
    python tools/schema.py --search tempo              # filtre par mot-clé
    python tools/schema.py --search consumption
    python tools/schema.py --raw                       # JSON brut du schéma complet

Configuration via tools/.env :
    OCTOPUS_EMAIL, OCTOPUS_PASSWORD
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _client import OctopusClient, hr, print_json

# ── Requête d'introspection ───────────────────────────────────────────────────

QUERY_INTROSPECT_FULL = """
{
  __schema {
    types {
      name
      kind
      description
      possibleTypes {
        name
        kind
      }
      fields {
        name
        description
        type {
          name
          kind
          ofType {
            name
            kind
          }
        }
        args {
          name
          type {
            name
            kind
          }
          defaultValue
        }
      }
      inputFields {
        name
        description
        type {
          name
          kind
        }
      }
      enumValues {
        name
        description
      }
    }
  }
}
"""

# ── Helpers d'affichage ───────────────────────────────────────────────────────

def _type_str(type_ref: dict | None) -> str:
    """Formate une référence de type GraphQL en chaîne lisible."""
    if not type_ref:
        return "?"
    name = type_ref.get("name")
    kind = type_ref.get("kind", "")
    of_type = type_ref.get("ofType")
    if name:
        return name
    if kind == "LIST" and of_type:
        return f"[{_type_str(of_type)}]"
    if kind == "NON_NULL" and of_type:
        return f"{_type_str(of_type)}!"
    return kind or "?"


def _is_builtin(name: str) -> bool:
    """Retourne True pour les types internes GraphQL (commençant par __)."""
    return name.startswith("__") if name else True


# ── Fonctions principales ─────────────────────────────────────────────────────

def list_types(types: list[dict], kind_filter: str | None = None) -> None:
    """Affiche la liste des types disponibles."""
    user_types = [
        t for t in types
        if not _is_builtin(t.get("name", ""))
        and (not kind_filter or t.get("kind") == kind_filter)
    ]
    user_types.sort(key=lambda t: t.get("name", ""))

    kind_groups: dict[str, list[str]] = {}
    for t in user_types:
        kind = t.get("kind", "OTHER")
        kind_groups.setdefault(kind, []).append(t.get("name", "?"))

    print(f"\n{'═' * 60}")
    print(f"  Schéma GraphQL Octopus France — {len(user_types)} types trouvés")
    print(f"{'═' * 60}\n")

    for kind in sorted(kind_groups):
        names = kind_groups[kind]
        print(f"  {kind} ({len(names)}) :")
        for n in names:
            print(f"    • {n}")
        print()


def show_type(types: list[dict], type_name: str) -> None:
    """Affiche les champs d'un type spécifique."""
    found = next((t for t in types if t.get("name") == type_name), None)
    if not found:
        # Recherche insensible à la casse
        type_name_lower = type_name.lower()
        candidates = [t for t in types if type_name_lower in (t.get("name") or "").lower()]
        if not candidates:
            print(f"❌  Type '{type_name}' non trouvé dans le schéma.", file=sys.stderr)
            sys.exit(1)
        if len(candidates) == 1:
            found = candidates[0]
            print(f"💡  Type proche trouvé : {found['name']}")
        else:
            print(f"💡  Plusieurs types proches trouvés :")
            for c in candidates[:10]:
                print(f"    • {c['name']}")
            sys.exit(0)

    name = found.get("name", "?")
    kind = found.get("kind", "?")
    desc = found.get("description") or ""

    print(f"\n{'═' * 60}")
    print(f"  Type : {name}  [{kind}]")
    if desc:
        print(f"  {desc}")
    print(f"{'═' * 60}\n")

    possible_types = found.get("possibleTypes") or []
    if possible_types:
        print(f"  Types possibles ({len(possible_types)}) :\n")
        for pt in possible_types:
            print(f"    • {pt.get('name', '?')}  [{pt.get('kind', '?')}]")
        print()

    fields = found.get("fields") or []
    if fields:
        print(f"  Champs ({len(fields)}) :\n")
        for field in sorted(fields, key=lambda f: f.get("name", "")):
            fname = field.get("name", "?")
            ftype = _type_str(field.get("type"))
            fdesc = (field.get("description") or "").replace("\n", " ").strip()
            args = field.get("args") or []

            print(f"    {fname} : {ftype}")
            if fdesc:
                print(f"         {fdesc}")
            if args:
                args_str = ", ".join(
                    f"{a['name']}: {_type_str(a.get('type'))}"
                    for a in args
                )
                print(f"         Args: ({args_str})")

    enum_values = found.get("enumValues") or []
    if enum_values:
        print(f"  Valeurs énumérées ({len(enum_values)}) :\n")
        for ev in enum_values:
            evname = ev.get("name", "?")
            evdesc = (ev.get("description") or "").replace("\n", " ").strip()
            desc_str = f"  ← {evdesc}" if evdesc else ""
            print(f"    {evname}{desc_str}")

    input_fields = found.get("inputFields") or []
    if input_fields:
        print(f"  Champs d'entrée ({len(input_fields)}) :\n")
        for f in input_fields:
            fname = f.get("name", "?")
            ftype = _type_str(f.get("type"))
            fdesc = (f.get("description") or "").replace("\n", " ").strip()
            print(f"    {fname} : {ftype}  {fdesc}")

    print()


def search_schema(types: list[dict], keyword: str) -> None:
    """Cherche les types et champs contenant le mot-clé."""
    kw = keyword.lower()
    results: list[tuple[str, str, str]] = []  # (type, champ, contexte)

    for t in types:
        tname = t.get("name") or ""
        if _is_builtin(tname):
            continue

        # Correspondance sur le nom du type
        if kw in tname.lower():
            desc = (t.get("description") or "").replace("\n", " ").strip()[:80]
            results.append((tname, "", desc or t.get("kind", "")))

        # Correspondance sur les champs du type
        for field in t.get("fields") or []:
            fname = field.get("name") or ""
            fdesc = field.get("description") or ""
            if kw in fname.lower() or kw in fdesc.lower():
                ftype = _type_str(field.get("type"))
                results.append((tname, fname, ftype))

        # Correspondance sur les valeurs d'énumération
        for ev in t.get("enumValues") or []:
            evname = ev.get("name") or ""
            if kw in evname.lower():
                results.append((tname, evname, f"[ENUM value]"))

    print(f"\n{'═' * 60}")
    print(f"  Recherche : « {keyword} »  —  {len(results)} résultat(s)")
    print(f"{'═' * 60}\n")

    if not results:
        print(f"  Aucun type ni champ ne correspond à « {keyword} ».\n")
        return

    last_type = None
    for tname, fname, context in sorted(results):
        if tname != last_type:
            print(f"  📦  {tname}")
            last_type = tname
        if fname:
            print(f"        └─ {fname} : {context}")
        else:
            print(f"        (type correspondant — {context})")

    print()


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Introspection du schéma GraphQL Octopus France",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--type", metavar="TYPE_NAME", help="Affiche les champs d'un type précis")
    parser.add_argument("--search", metavar="MOT_CLE", help="Filtre types et champs par mot-clé")
    parser.add_argument("--kind", help="Filtre par kind (OBJECT, ENUM, INPUT_OBJECT…)")
    parser.add_argument("--raw", action="store_true", help="Dump JSON brut du schéma complet")
    args = parser.parse_args()

    client = OctopusClient()
    print("📥  Récupération du schéma GraphQL (introspection)...")
    data = client.query(QUERY_INTROSPECT_FULL)
    types = data.get("data", {}).get("__schema", {}).get("types", [])

    if args.raw:
        print_json(data)
        return

    if args.type:
        show_type(types, args.type)
    elif args.search:
        search_schema(types, args.search)
    else:
        list_types(types, kind_filter=args.kind)
        print(f"💡  Astuce :")
        print(f"    python tools/schema.py --type  <NomDuType>   # détails d'un type")
        print(f"    python tools/schema.py --search <motClé>     # recherche libre")
        print(f"    python tools/schema.py --search tempo         # chercher Tempo\n")


if __name__ == "__main__":
    main()
