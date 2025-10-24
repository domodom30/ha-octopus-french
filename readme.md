# Octopus Energy France pour Home Assistant

[![GitHub Release](https://img.shields.io/github/release/domodom30/ha-octopus-french)](https://github.com/domodom30/ha-octopus-french/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_french.total)

Une intégration complète Home Assistant pour les clients Octopus Energy France permettant de surveiller la consommation d'électricité et de gaz, les tarifs, les factures et le solde du compte.

## Fonctionnalités

### 📊 Suivi
- **Consommation électrique** (heures pleines/creuses)
- **Consommation de gaz**
- **Relevés de compteur** avec suivi des index
- **Tarifs actuels** (électricité & gaz)
- **Détection des heures creuses** avec capteur binaire

### 💰 Suivi financier
- **Solde du compte** (électricité, gaz et cagnotte)
- **Dernières factures** pour l'électricité et le gaz
- **Statut des paiements** et dates prévues

### 🏠 Appareils & Organisation
- Appareils séparés pour :
  - **Compte Octopus Energy** (soldes et factures)
  - **Compteurs Linky ou autre** (électricité)
  - **Compteurs Gazpar ou autre** (gaz)
- Toutes les entités organisées par appareil

### ⚙️ Fonctionnalités avancées
- **Intervalle de mise à jour configurable** (5 à 1440 minutes)
- **Service de mise à jour forcée** pour rafraîchir immédiatement
- **Compatible avec le tableau de bord Énergie**
- **Entités de diagnostic** pour informations détaillées
---

## Installation

### HACS (Recommandé)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domodom30&repository=ha-octopus-french&category=integration)

### Installation manuelle

1. Téléchargez la dernière version depuis [GitHub](https://github.com/domodom30/ha-octopus-french/releases)
2. Extrayez le dossier `octopus_french` dans votre répertoire `custom_components`
3. Redémarrez Home Assistant

---

## Configuration

### Configuration initiale

1. Allez dans **Paramètres** → **Appareils et services**
2. Cliquez sur **"+ Ajouter une intégration"**
3. Recherchez **"Octopus Energy France"**
4. Entrez vos identifiants Octopus Energy :
   - **E-mail**
   - **Mot de passe**
5. Cliquez sur **Soumettre**

### Options

Après l'installation, vous pouvez configurer :

- **Intervalle de mise à jour** : Fréquence de rafraîchissement (par défaut : 60 minutes, plage : 5-1440)

Pour accéder aux options :
1. Allez dans **Paramètres** → **Appareils et services**
2. Trouvez **Octopus Energy France**
3. Cliquez sur **Configurer**

---

## Entités

### Appareil Compte (Compte Octopus Energy)

| Entité | Type | Description |
|--------|------|-------------|
| Cagnotte | Capteur | Solde de la cagnotte |
| Solde électricité | Capteur | Solde actuel du compte électricité |
| Solde gaz | Capteur | Solde actuel du compte gaz |
| Facture électricité | Capteur | Montant de la dernière facture électricité |
| Facture gaz | Capteur | Montant de la dernière facture gaz |

### Appareil Compteur Électrique (Linky)

#### Capteurs principaux
| Entité | Type | Classe | Description |
|--------|------|--------|-------------|
| Consommation HP | Capteur | Énergie | Consommation HP (kWh) / mois |
| Consommation HC | Capteur | Énergie | Consommation HC (kWh) / mois |
| Heures creuses actives | Capteur binaire | Running | État de la période actuelle |

#### Capteurs de diagnostic
| Entité | Type | Description |
|--------|------|-------------|
| Index HP | Capteur | Relevé compteur heures pleines |
| Index HC | Capteur | Relevé compteur heures creuses |
| Tarif HP | Capteur | Tarif actuel heures pleines (€/kWh) |
| Tarif HC | Capteur | Tarif actuel heures creuses (€/kWh) |
| Contrat | Capteur | Détails du contrat et infos compteur |

### Appareil Compteur Gaz (Gazpar)

#### Capteurs principaux
| Entité | Type | Classe | Description |
|--------|------|--------|-------------|
| Consommation | Capteur | Énergie | Consommation actuelle de gaz (kWh) |

#### Capteurs de diagnostic
| Entité | Type | Description |
|--------|------|-------------|
| Index | Capteur | Relevé compteur gaz |
| Tarif | Capteur | Tarif actuel du gaz (€/kWh) |
| Contrat | Capteur | Détails du contrat et infos compteur |

---

## Services

### `octopus_french.force_update`

Force un rafraîchissement immédiat des données depuis l'API Octopus Energy.

**Exemple :**
```yaml
service: octopus_french.force_update
```

---

## Intégration Tableau de bord Énergie

Cette intégration est entièrement compatible avec le tableau de bord Énergie de Home Assistant.

### Instructions de configuration

1. Allez dans **Paramètres** → **Tableaux de bord** → **Énergie**
2. Cliquez sur **"Ajouter une consommation"**
3. Sélectionnez :
   - **Électricité - Heures pleines** : `sensor.linky_XXXXXX_consumption_hp`
   - **Électricité - Heures creuses** : `sensor.linky_XXXXXX_consumption_hc`
   - **Gaz** : `sensor.gazpar_XXXXXX_consumption`

### Coûts individuels

Pour chaque capteur de consommation, vous pouvez configurer le coût :
1. Cliquez sur le capteur dans le tableau de bord Énergie
2. Activez **"Utiliser un prix statique"** ou liez au capteur de tarif
3. Pour l'électricité :
   - HP : Lier à `sensor.linky_XXXXXX_tarif_hp`
   - HC : Lier à `sensor.linky_XXXXXX_tarif_hc`
4. Pour le gaz :
   - Lier à `sensor.gazpar_XXXXXX_tarif`

---

## Détails des attributs

### Attributs du capteur Contrat

#### Contrat Électricité
- `prm_id` : Identifiant Point Référence Mesure
- `ledger_id` : Numéro de registre associé
- `distributor_status` : SERVC (En service) / RESIL (Résilié)
- `meter_kind` : Type de compteur (Linky)
- `subscribed_max_power` : Puissance souscrite (kVA)
- `is_teleoperable` : Capacité de téléopération
- `off_peak_label` : Plages horaires heures creuses
- `powered_status` : État alimentation (ALIM/LIMI)

#### Contrat Gaz
- `pce_ref` : Référence PCE
- `ledger_id` : Numéro de registre associé
- `gas_nature` : Naturel/Propane
- `annual_consumption` : Consommation annuelle estimée
- `is_smart_meter` : Compteur communicant (Gazpar)
- `powered_status` : État de la connexion
- `price_level` : Niveau de prix
- `tariff_option` : Option tarifaire

### Attributs des capteurs de facture
- `payment_status` : Statut du paiement
- `total_amount` : Montant total de la facture
- `customer_amount` : Part client
- `expected_payment_date` : Date de paiement prévue

### Attributs Consommation/Index
- `period_start` : Début période de relevé
- `period_end` : Fin période de relevé
- `reliability` : Fiabilité des données (REAL)
- `status` : Statut de traitement (OK)

### Capteur binaire Heures creuses
- `hc_schedule_available` : Disponibilité de l'horaire
- `total_hc_hours` : Total heures creuses par jour
- `hc_type` : Type d'horaire
- `hc_range_1`, `hc_range_2`, etc. : Plages horaires individuelles

---

## Exemples d'automatisations

### Notification au début des heures creuses
```yaml
automation:
  - alias: "Début heures creuses"
    trigger:
      - platform: state
        entity_id: binary_sensor.linky_XXXXXX_heures_creuses_actives
        to: "on"
    action:
      - service: notify.notify
        data:
          title: "⚡ Heures creuses"
          message: "Les heures creuses ont commencé. Bon moment pour lancer les appareils énergivores !"
```

### Alerte facture élevée
```yaml
automation:
  - alias: "Alerte facture élevée"
    trigger:
      - platform: numeric_state
        entity_id: sensor.compte_octopus_energy_facture_electricite
        above: 100
    action:
      - service: notify.notify_appareil
        data:
          title: "💰 Alerte facture élevée"
          message: "Votre facture d'électricité est de {{ states('sensor.compte_octopus_energy_facture_electricite') }}€"
```

## Dépannage

### Les entités n'apparaissent pas
- Vérifiez que vos identifiants sont corrects
- Assurez-vous que votre compte a des compteurs actifs
- Redémarrez Home Assistant après l'installation

### Les données ne se mettent pas à jour
- Vérifiez l'intervalle de mise à jour dans les options
- Utilisez le service `force_update` pour forcer le rafraîchissement
- Vérifiez la connectivité API dans les logs Home Assistant

### Compteurs résiliés
- Les compteurs résiliés (statut RESIL) sont automatiquement exclus
- Seuls les compteurs actifs apparaissent dans l'intégration

### Données de consommation manquantes
- Certaines données peuvent prendre 24-48h après l'installation du compteur
- Vérifiez la disponibilité des données sur le site Octopus Energy

---

## Support

- **Problèmes** : [GitHub Issues](https://github.com/domodom30/ha-octopus-french/issues)
- **Demandes de fonctionnalités** : [GitHub Discussions](https://github.com/domodom30/ha-octopus-french/discussions)

---
