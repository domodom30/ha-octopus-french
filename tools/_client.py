"""Client HTTP partagé pour les scripts d'exploration de l'API Octopus France.

Utilisation interne — importé par les autres scripts du répertoire tools/.
Seule dépendance externe : requests  (pip install requests)
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌  Module 'requests' manquant. Installez-le avec : pip install requests", file=sys.stderr)
    sys.exit(1)

# ── Constantes ────────────────────────────────────────────────────────────────

API_URL = "https://api.oefr-kraken.energy/v1/graphql/"

_TOOLS_DIR = Path(__file__).parent
_TOKEN_FILE = _TOOLS_DIR / ".token"
_ENV_FILE = _TOOLS_DIR / ".env"

# ── Chargement de la configuration ───────────────────────────────────────────

def load_env() -> None:
    """Charge les variables depuis tools/.env (si présent) sans python-dotenv."""
    if not _ENV_FILE.exists():
        return
    with _ENV_FILE.open() as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_credentials() -> tuple[str, str]:
    """Récupère email et mot de passe depuis l'environnement."""
    load_env()
    email = os.environ.get("OCTOPUS_EMAIL", "")
    password = os.environ.get("OCTOPUS_PASSWORD", "")
    if not email or not password:
        print(
            "❌  Variables OCTOPUS_EMAIL et OCTOPUS_PASSWORD requises.\n"
            "    Créez tools/.env à partir de tools/.env.example.",
            file=sys.stderr,
        )
        sys.exit(1)
    return email, password


def get_account_number() -> str | None:
    """Récupère le numéro de compte depuis l'environnement (optionnel)."""
    load_env()
    return os.environ.get("OCTOPUS_ACCOUNT")


# ── Décodage JWT ──────────────────────────────────────────────────────────────

def decode_jwt_payload(token: str) -> dict:
    """Décode le payload d'un JWT sans vérifier la signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        # Padding base64url → base64 standard
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception:
        return {}


def token_is_expired(token: str, buffer_seconds: int = 60) -> bool:
    """Retourne True si le token est expiré (ou expire dans moins de buffer_seconds)."""
    payload = decode_jwt_payload(token)
    exp = payload.get("exp")
    if exp is None:
        return True
    return datetime.now(timezone.utc).timestamp() + buffer_seconds > exp


# ── Gestion du token ──────────────────────────────────────────────────────────

def save_token(token: str) -> None:
    """Sauvegarde le token JWT dans tools/.token."""
    _TOKEN_FILE.write_text(token.strip())


def load_cached_token() -> str | None:
    """Charge le token sauvegardé s'il existe et n'est pas expiré."""
    if not _TOKEN_FILE.exists():
        return None
    token = _TOKEN_FILE.read_text().strip()
    if not token or token_is_expired(token):
        return None
    return token


# ── Requête GraphQL ───────────────────────────────────────────────────────────

def graphql_request(token: str, query: str, variables: dict | None = None) -> dict:
    """Exécute une requête GraphQL authentifiée.

    Lève SystemExit en cas d'erreur HTTP ou GraphQL (sauf si l'appelant
    gère lui-même les erreurs).
    """
    headers = {
        "Authorization": f"JWT {token}",
        "Content-Type": "application/json",
    }
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
    except requests.ConnectionError as exc:
        print(f"❌  Impossible de joindre l'API : {exc}", file=sys.stderr)
        sys.exit(1)
    except requests.Timeout:
        print("❌  Timeout lors de la requête GraphQL.", file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"❌  HTTP {resp.status_code} : {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    errors = data.get("errors")
    if errors:
        messages = " | ".join(e.get("message", str(e)) for e in errors)
        print(f"❌  Erreur GraphQL : {messages}", file=sys.stderr)
        sys.exit(1)

    return data


def graphql_request_raw(token: str, query: str, variables: dict | None = None) -> dict:
    """Comme graphql_request() mais retourne toujours la réponse complète
    (y compris les errors[]) sans quitter."""
    headers = {
        "Authorization": f"JWT {token}",
        "Content-Type": "application/json",
    }
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Client principal ──────────────────────────────────────────────────────────

class OctopusClient:
    """Client Octopus avec gestion automatique du token JWT."""

    def __init__(self, email: str | None = None, password: str | None = None) -> None:
        if email and password:
            self.email = email
            self.password = password
        else:
            self.email, self.password = get_credentials()
        self._token: str | None = None

    def ensure_token(self) -> str:
        """Retourne un token valide (cache → auth si nécessaire)."""
        if self._token and not token_is_expired(self._token):
            return self._token

        cached = load_cached_token()
        if cached:
            self._token = cached
            return cached

        # Authentification fraîche
        token = self._authenticate()
        self._token = token
        save_token(token)
        return token

    def _authenticate(self) -> str:
        """Envoie la mutation d'authentification et retourne le token JWT."""
        mutation = """
        mutation obtainKrakenToken($input: ObtainJSONWebTokenInput!) {
            obtainKrakenToken(input: $input) {
                token
            }
        }
        """
        payload = {
            "query": mutation,
            "variables": {"input": {"email": self.email, "password": self.password}},
        }
        try:
            resp = requests.post(
                API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
        except requests.ConnectionError as exc:
            print(f"❌  Connexion impossible : {exc}", file=sys.stderr)
            sys.exit(1)

        if resp.status_code != 200:
            print(f"❌  HTTP {resp.status_code} lors de l'auth : {resp.text[:300]}", file=sys.stderr)
            sys.exit(1)

        data = resp.json()
        errors = data.get("errors")
        if errors:
            messages = " | ".join(e.get("message", str(e)) for e in errors)
            print(f"❌  Erreur d'authentification : {messages}", file=sys.stderr)
            sys.exit(1)

        token = data.get("data", {}).get("obtainKrakenToken", {}).get("token")
        if not token:
            print("❌  Token absent dans la réponse d'authentification.", file=sys.stderr)
            sys.exit(1)

        return token

    def query(self, gql: str, variables: dict | None = None) -> dict:
        """Exécute une requête GraphQL avec le token en cours."""
        return graphql_request(self.ensure_token(), gql, variables)

    def query_raw(self, gql: str, variables: dict | None = None) -> dict:
        """Comme query() mais retourne la réponse brute complète."""
        return graphql_request_raw(self.ensure_token(), gql, variables)


# ── Utilitaires d'affichage ────────────────────────────────────────────────────

def print_json(obj: object) -> None:
    """Affiche un objet Python en JSON indenté."""
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def hr(char: str = "─", width: int = 60) -> str:
    """Retourne une ligne horizontale."""
    return char * width
