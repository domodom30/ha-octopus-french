#!/usr/bin/env python3
"""Authentification à l'API Octopus Energy France.

Obtient un token JWT et le sauvegarde dans tools/.token pour être réutilisé
par les autres scripts.

Usage :
    python tools/auth.py
    python tools/auth.py --email mon@email.fr --password monMotDePasse

Configuration via tools/.env (voir tools/.env.example) ou variables d'environnement :
    OCTOPUS_EMAIL, OCTOPUS_PASSWORD
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ajout du répertoire parent au path pour permettre l'exécution depuis n'importe où
sys.path.insert(0, str(Path(__file__).parent))
from _client import (
    OctopusClient,
    _TOKEN_FILE,
    decode_jwt_payload,
    hr,
    save_token,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authentification à l'API Octopus Energy France",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--email", help="Email du compte Octopus (remplace OCTOPUS_EMAIL)")
    parser.add_argument("--password", help="Mot de passe (remplace OCTOPUS_PASSWORD)")
    parser.add_argument("--show-token", action="store_true", help="Affiche le token complet")
    args = parser.parse_args()

    client = OctopusClient(
        email=args.email or None,
        password=args.password or None,
    )

    print("🔐  Authentification en cours...")
    token = client._authenticate()
    save_token(token)

    # Décodage du payload JWT
    payload = decode_jwt_payload(token)
    exp_ts = payload.get("exp")
    iat_ts = payload.get("iat")
    originator_id = payload.get("originator", {})
    if isinstance(originator_id, dict):
        originator_id = originator_id.get("id", "?")

    print(f"\n✅  Authentification réussie — token sauvegardé dans {_TOKEN_FILE}")
    print(hr())

    if iat_ts:
        issued = datetime.fromtimestamp(iat_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"   Émis le      : {issued}")

    if exp_ts:
        expires = datetime.fromtimestamp(exp_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        now_ts = datetime.now(timezone.utc).timestamp()
        remaining = int((exp_ts - now_ts) / 3600)
        print(f"   Expire le    : {expires}  ({remaining}h restantes)")

    print(hr())

    if args.show_token:
        print(f"\nToken JWT :\n{token}\n")
    else:
        print(f"\nToken (extrait) : {token[:40]}…")
        print("Utilisez --show-token pour afficher le token complet.")


if __name__ == "__main__":
    main()
