# 🛠️ Outils d'exploration de l'API GraphQL Octopus France

Scripts CLI autonomes pour interroger directement l'API GraphQL Octopus Energy France :
`https://api.oefr-kraken.energy/v1/graphql/`

Conçus pour l'investigation de nouvelles offres (OctoTempo, etc.) et le débogage
de l'intégration Home Assistant.

---

## Prérequis

```bash
pip install requests
```

C'est la seule dépendance externe. Pas d'asyncio, pas de Home Assistant.

---

## Configuration

```bash
# Copier le modèle de configuration
cp tools/.env.example tools/.env

# Éditer avec vos identifiants Octopus
nano tools/.env   # ou votre éditeur préféré
```

Contenu de `tools/.env` :
```ini
OCTOPUS_EMAIL=votre@email.fr
OCTOPUS_PASSWORD=votre_mot_de_passe
OCTOPUS_ACCOUNT=A-XXXX0000
```

> ⚠️ `tools/.env` et `tools/.token` sont ignorés par git (ne pas committer vos credentials).

Alternativement, utilisez des variables d'environnement :
```bash
export OCTOPUS_EMAIL=votre@email.fr
export OCTOPUS_PASSWORD=votre_mot_de_passe
export OCTOPUS_ACCOUNT=A-XXXX0000
```

---

## Scripts disponibles

| Script | Description |
|--------|-------------|
| `auth.py` | Authentification et sauvegarde du token JWT |
| `account.py` | Données du compte (compteurs, accords, `product.code`, tarifs) |
| `readings.py` | Relevés de consommation avec labels `metaData.statistics` |
| `index.py` | Index électrique Linky (`calendarTempClass`, valeurs d'index) |
| `schema.py` | Introspection du schéma GraphQL |
| `query.py` | Exécution d'une requête GraphQL libre |

---

## Utilisation

### 1. Authentification

```bash
python tools/auth.py
# Affiche le token et sa date d'expiration
# Sauvegarde dans tools/.token (réutilisé par les autres scripts)
```

### 2. Données du compte

```bash
# Résumé lisible (compteurs, contrats, tarifs)
python tools/account.py

# Avec numéro de compte spécifique
python tools/account.py --account A-XXXX0000

# JSON brut complet
python tools/account.py --raw
```

**Exemple de sortie :**
```
  Compte : A-XXXX0000
  ⚡  Électricité  PRM: 12345678901234
      Statut: ACTIVE / Alimentation: LIMI
      product.code : FR_VAR_BB_2024       ← à noter pour l'intégration
      6 taux détectés → probablement un contrat OctoTempo !
```

### 3. Relevés de consommation

```bash
# Labels des 30 derniers jours
python tools/readings.py --prm 12345678901234

# 14 derniers jours
python tools/readings.py --prm 12345678901234 --days 14

# JSON brut
python tools/readings.py --prm 12345678901234 --raw
```

**Révèle les labels présents dans `metaData.statistics` :**
- Contrat BASE → `BASE`
- Contrat HP/HC → `HEURES_PLEINES`, `HEURES_CREUSES`
- Contrat OctoTempo → `TEMPO_BLEU_HP`, `TEMPO_BLEU_HC`, `TEMPO_BLANC_HP`… (à confirmer)

### 4. Index électrique Linky

```bash
# 5 entrées par défaut
python tools/index.py --account A-XXXX0000 --prm 12345678901234

# 10 entrées
python tools/index.py --account A-XXXX0000 --prm 12345678901234 --first 10

# JSON brut
python tools/index.py --account A-XXXX0000 --prm 12345678901234 --raw
```

**Révèle les codes temporels (`temporalClass.code` et `calendarTempClass` legacy) :**
- Contrat BASE → `BASE`
- Contrat HP/HC → `HP`, `HC`
- Contrat OctoTempo → codes à confirmer (ex : `BLEU_HP`, `BLEU_HC`, `ROUGE_HP`…)

> `temporalClass.code` est affiché en priorité (champ structuré avec label et registerId).
> `calendarTempClass` reste affiché comme référence legacy si présent.

### 5. Introspection du schéma GraphQL

```bash
# Liste tous les types disponibles
python tools/schema.py

# Détails d'un type précis (affiche aussi possibleTypes pour les UNION)
python tools/schema.py --type ElectricityMeterPoint
python tools/schema.py --type TemporalClassUnion      # → liste les types membres de l'union
python tools/schema.py --type ProviderTemporalClassType

# Recherche par mot-clé
python tools/schema.py --search tempo
python tools/schema.py --search consumption
python tools/schema.py --search calendar

# JSON brut du schéma complet
python tools/schema.py --raw > schema_dump.json
```

### 6. Requête GraphQL libre

```bash
# Depuis stdin
echo '{ viewer { accounts { number } } }' | python tools/query.py

# Depuis un fichier
python tools/query.py --file ma_query.graphql

# Avec variables
python tools/query.py --file ma_query.graphql --vars '{"accountNumber":"A-XXXX0000"}'

# Depuis un fichier de variables
python tools/query.py --file ma_query.graphql --vars-file variables.json

# Sortie compacte (une ligne)
python tools/query.py --query '{ viewer { accounts { number } } }' --compact

# Sauvegarder dans un fichier
python tools/query.py --file ma_query.graphql > result.json
```

---

## 🎨 Investiguer l'offre OctoTempo

Séquence recommandée pour un client ayant souscrit OctoTempo :

```bash
# Étape 1 : s'authentifier
python tools/auth.py

# Étape 2 : trouver le PRM et voir le product.code du contrat
python tools/account.py
# → noter le PRM et le product.code (ex: FR_TEMPO_XXX)

# Étape 3 : observer les labels de relevés
python tools/readings.py --prm <votre_PRM> --days 30
# → chercher TEMPO_BLEU_HP, TEMPO_ROUGE_HC, etc.

# Étape 4 : observer le calendarTempClass de l'index Linky
python tools/index.py --account <votre_compte> --prm <votre_PRM> --first 10
# → chercher BLEU, BLANC, ROUGE

# Étape 5 : explorer le schéma pour trouver de nouveaux champs
python tools/schema.py --search tempo
python tools/schema.py --type ElectricityReadingType   # voir tous les champs disponibles

# Étape 6 : tester une query personnalisée
python tools/query.py --query '
  query { electricityReading(accountNumber: "A-XXX", prmId: "12345", first: 3, calendarType: PROVIDER) {
    edges { node { calendarTempClass periodStartAt consumption } }
  }}
'
```

Ces informations permettront de **finaliser l'implémentation OctoTempo** dans
`custom_components/octopus_french/const.py` (labels et calendarTempClass réels).

---

## Fichiers générés (ignorés par git)

| Fichier | Description |
|---------|-------------|
| `tools/.env` | Vos credentials (à créer depuis `.env.example`) |
| `tools/.token` | Token JWT mis en cache (régénéré automatiquement à expiration) |

---

## Architecture des scripts

```
tools/
├── _client.py      ← Client HTTP partagé (OctopusClient, gestion du token)
├── auth.py         ← Authentification
├── account.py      ← Données du compte
├── readings.py     ← Relevés de consommation
├── index.py        ← Index Linky
├── schema.py       ← Introspection GraphQL
└── query.py        ← Requête libre
```

`_client.py` fournit :
- `OctopusClient` — client avec cache du token JWT
- `graphql_request()` — requête avec gestion des erreurs
- `decode_jwt_payload()` — décodage du payload JWT (sans PyJWT)
- `print_json()` — affichage JSON indenté
