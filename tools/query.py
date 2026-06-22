#!/usr/bin/env python3
"""Exécuteur de requête GraphQL libre.

Permet de tester n'importe quelle query ou mutation GraphQL directement
depuis un fichier ou stdin, avec optionnellement des variables JSON.

Usage :
    # Depuis un fichier .graphql
    python tools/query.py --file ma_query.graphql
    python tools/query.py --file ma_query.graphql --vars '{"accountNumber": "A-XXXX0000"}'

    # Depuis stdin
    echo '{ viewer { accounts { number } } }' | python tools/query.py

    # Requête en ligne
    python tools/query.py --query '{ viewer { accounts { number } } }'

    # Sauvegarder dans un fichier
    python tools/query.py --file ma_query.graphql > resultat.json

    # Sans authentification (pour les queries publiques)
    python tools/query.py --no-auth --query '{ __typename }'

Configuration via tools/.env :
    OCTOPUS_EMAIL, OCTOPUS_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _client import OctopusClient, print_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exécuteur de requête GraphQL libre",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", "-f", metavar="FICHIER.graphql", help="Fichier contenant la query GraphQL")
    source.add_argument("--query", "-q", metavar="QUERY", help="Query GraphQL en ligne de commande")

    parser.add_argument(
        "--vars", "-v",
        metavar="JSON",
        help='Variables GraphQL en JSON (ex: \'{"accountNumber": "A-XXXX0000"}\')',
    )
    parser.add_argument(
        "--vars-file",
        metavar="FICHIER.json",
        help="Fichier JSON contenant les variables",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Exécuter sans token d'authentification (queries publiques)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Sortie JSON compacte (sans indentation)",
    )
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"❌  Fichier non trouvé : {args.file}", file=sys.stderr)
            sys.exit(1)
        query_str = path.read_text()
    elif args.query:
        query_str = args.query
    elif not sys.stdin.isatty():
        query_str = sys.stdin.read()
    else:
        print("❌  Aucune query fournie. Utilisez --file, --query, ou stdin.", file=sys.stderr)
        print("    Exemple : echo '{ viewer { accounts { number } } }' | python tools/query.py", file=sys.stderr)
        sys.exit(1)

    query_str = query_str.strip()
    if not query_str:
        print("❌  La query est vide.", file=sys.stderr)
        sys.exit(1)

    variables: dict | None = None
    if args.vars:
        try:
            variables = json.loads(args.vars)
        except json.JSONDecodeError as exc:
            print(f"❌  JSON invalide dans --vars : {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.vars_file:
        vars_path = Path(args.vars_file)
        if not vars_path.exists():
            print(f"❌  Fichier de variables non trouvé : {args.vars_file}", file=sys.stderr)
            sys.exit(1)
        try:
            variables = json.loads(vars_path.read_text())
        except json.JSONDecodeError as exc:
            print(f"❌  JSON invalide dans {args.vars_file} : {exc}", file=sys.stderr)
            sys.exit(1)

    if args.no_auth:
        import requests
        from _client import API_URL
        payload: dict = {"query": query_str}
        if variables:
            payload["variables"] = variables
        resp = requests.post(API_URL, json=payload, timeout=30)
        result = resp.json()
    else:
        client = OctopusClient()
        result = client.query_raw(query_str, variables)

    if args.compact:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print_json(result)


if __name__ == "__main__":
    main()
