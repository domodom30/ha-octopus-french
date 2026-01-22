# Octopus Energy France pour Home Assistant

[![GitHub Release](https://img.shields.io/github/release/domodom30/ha-octopus-french)](https://github.com/domodom30/ha-octopus-french/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_french.total)

Intégration Octopus Energy France (non officiel) pour Home Assistant.

## 🌟 Fonctionnalités

### 📊 Suivi de la consommation
- **Consommation électrique**
  - Mode BASE : consommation et coût mensuel
  - Mode HPHC : consommation et coût mensuel (heures pleines / heures creuses)
  - **Statistiques historiques** : Import automatique de l'historique dans le tableau de bord Énergie
  - **Dernier relevé** : Valeur et détails de la dernière lecture quotidienne
- **Consommation de gaz** : cumulative mensuelle
- **Abonnement** : Coût mensuel de l'abonnement électricité

### 🔢 Index des compteurs Linky
- **Index BASE** : Valeur actuelle du compteur
- **Index HP/HC** : Valeurs actuelles des compteurs heures pleines/creuses
- Suivi de la consommation entre deux relevés
- Fiabilité des données (REAL/ESTIMATED)

### 💰 Suivi financier
- **Solde de la cagnotte** (POT_LEDGER)
- **Dernières factures** avec statut de paiement :
  - Facture électricité (FRA_ELECTRICITY_LEDGER)
  - Facture gaz (FRA_GAS_LEDGER)
- **Statuts détaillés** : Scheduled, Pending, Cleared, Failed, etc.
- **Dates de paiement prévues**

### 🏠 Appareils & Organisation
Appareils séparés pour une organisation claire :
- **Compte Octopus Energy** : solde cagnotte, factures (électricité & gaz)
- **Compteur Linky** (électricité) : consommation, coûts, index, contrat
- **Compteur Gazpar** (gaz) : consommation, contrat

### ⚙️ Fonctionnalités avancées
- **Intervalle de mise à jour configurable** (5 à 1440 minutes, défaut : 60 min)
- **Service de mise à jour forcée** pour rafraîchir immédiatement
- **Compatible avec le tableau de bord Énergie** de Home Assistant
- **Gestion automatique de l'authentification** avec rafraîchissement des tokens
- **Exclusion automatique** des compteurs résiliés

---

## 📥 Installation

### HACS (Recommandé)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domodom30&repository=ha-octopus-french&category=integration)

1. Ouvrez HACS dans Home Assistant
2. Cliquez sur "Intégrations"
3. Cliquez sur les trois points en haut à droite
4. Sélectionnez "Dépôts personnalisés"
5. Ajoutez l'URL : `https://github.com/domodom30/ha-octopus-french`
6. Sélectionnez la catégorie "Integration"
7. Cliquez sur "Télécharger"
8. Redémarrez Home Assistant

### Installation manuelle

1. Téléchargez la dernière version depuis [GitHub](https://github.com/domodom30/ha-octopus-french/releases)
2. Extrayez le dossier `octopus_french` dans votre répertoire `custom_components`
3. Redémarrez Home Assistant

---

## ⚙️ Configuration

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

## 📋 Entités créées

### 🏢 Appareil Compte (Compte Octopus Energy)

| Entité | Type | Classe | Description |
|--------|------|--------|-------------|
| Solde cagnotte | Capteur | Monetary | Solde de la cagnotte (POT_LEDGER) |
| Facture électricité | Capteur | Monetary | Montant de la dernière facture électricité |
| Facture gaz | Capteur | Monetary | Montant de la dernière facture gaz |

**Attributs des factures :**
- `payment_status` : Statut du paiement (scheduled, pending, cleared, failed, etc.)
- `total_amount` : Montant total de la facture
- `customer_amount` : Part client
- `expected_payment_date` : Date de paiement prévue

---

### ⚡ Appareil Compteur Électrique (Linky)

#### Capteurs principaux

**Pour les contrats BASE :**

| Entité | Type | Classe | State Class | Description |
|--------|------|--------|-------------|-------------|
| Conso / mois en cours | Capteur | Energy | Total Increasing | Consommation BASE (kWh) du mois en cours |
| Coût / mois en cours | Capteur | Monetary | Total | Coût BASE (€) du mois en cours |
| Abonnement | Capteur | Monetary | Total | Coût mensuel de l'abonnement |
| Contrat | Capteur | - | - | Type de contrat et informations |

**Pour les contrats HPHC (Heures Pleines / Heures Creuses) :**

| Entité | Type | Classe | State Class | Description |
|--------|------|--------|-------------|-------------|
| HP / mois en cours | Capteur | Energy | Total Increasing | Consommation heures pleines (kWh) |
| HC / mois en cours | Capteur | Energy | Total Increasing | Consommation heures creuses (kWh) |
| HP / mois en cours | Capteur | Monetary | Total | Coût heures pleines (€) |
| HC / mois en cours | Capteur | Monetary | Total | Coût heures creuses (€) |
| Abonnement | Capteur | Monetary | Total | Coût mensuel de l'abonnement |
| Contrat | Capteur | - | - | Type de contrat et informations |

#### Capteurs d'index (Diagnostic)

**Pour les contrats BASE :**

| Entité | Type | Classe | Description |
|--------|------|--------|-------------|
| Index | Capteur | Energy | Index actuel du compteur BASE |

**Pour les contrats HPHC :**

| Entité | Type | Classe | Description |
|--------|------|--------|-------------|
| Index HP | Capteur | Energy | Index actuel heures pleines |
| Index HC | Capteur | Energy | Index actuel heures creuses |

**Attributs des index :**
- `prm_id` : Identifiant PRM
- `index_start` : Index de départ de la période
- `consumption` : Consommation sur la période
- `period_start` : Début de période de relevé
- `period_end` : Fin de période de relevé
- `index_reliability` : Fiabilité de l'index (REAL/ESTIMATED)

#### Capteur dernier relevé (Diagnostic)

| Entité | Type | Classe | Description |
|--------|------|--------|-------------|
| Dernier relevé | Capteur | Energy | Valeur du dernier relevé quotidien |

**Attributs du dernier relevé :**
- `date_releve` : Date du relevé
- `heures_base` : Heures en base (si applicable)
- `heures_pleines_kwh` : Consommation heures pleines (si applicable)
- `heures_creuses_kwh` : Consommation heures creuses (si applicable)
- `cout_base_euro` : Coût base (si applicable)
- `cout_heures_pleines_euro` : Coût heures pleines (si applicable)
- `cout_heures_creuses_euro` : Coût heures creuses (si applicable)
- `cout_abonnement_euro` : Coût abonnement journalier

**Attributs du contrat :**
- `prm_id` : Identifiant Point Référence Mesure
- `ledger_id` : Numéro de registre associé
- `agreement` : Type de contrat (BASE ou HPHC)
- `distributor_status` : SERVC (En service) / RESIL (Résilié)
- `meter_kind` : Type de compteur (LINKY, etc.)
- `subscribed_max_power` : Puissance souscrite (kVA)
- `is_teleoperable` : Capacité de téléopération
- `off_peak_label` : Plages horaires heures creuses
- `powered_status` : État alimentation (ALIM/LIMI)

---

### 🔥 Appareil Compteur Gaz (Gazpar)

| Entité | Type | Classe | State Class | Description |
|--------|------|--------|-------------|-------------|
| Consommation | Capteur | Energy | Total Increasing | Consommation mensuelle de gaz (kWh) |
| Contrat | Capteur | - | - | Type de contrat et informations |

**Attributs du contrat gaz :**
- `pce_ref` : Référence PCE
- `ledger_id` : Numéro de registre associé
- `gas_nature` : Type de gaz (Naturel/Propane)
- `annual_consumption` : Consommation annuelle estimée (kWh)
- `is_smart_meter` : Compteur communicant (Gazpar)
- `powered_status` : État de la connexion (En service/Coupé)

---

## 📊 Intégration Tableau de bord Énergie

Cette intégration est **entièrement compatible** avec le tableau de bord Énergie de Home Assistant et importe automatiquement l'historique des consommations.

### ✨ Nouveauté : Import automatique des statistiques

L'intégration importe automatiquement l'historique de vos consommations et coûts dans Home Assistant :
- **Import complet** lors de la première installation
- **Mise à jour incrémentale** lors des rafraîchissements suivants
- **Compatible** avec le tableau de bord Énergie

### Instructions de configuration

1. Allez dans **Paramètres** → **Tableaux de bord** → **Énergie**
2. Cliquez sur **"Ajouter une consommation"**

#### Pour un contrat BASE :
- **Consommation depuis le réseau** : `sensor.linky_XXXXXX_conso_base`
- **Coût** (optionnel) : Utilisez les statistiques importées automatiquement

#### Pour un contrat HPHC :
- **Consommation depuis le réseau** :
  - Heures pleines : `sensor.linky_XXXXXX_conso_hp`
  - Heures creuses : `sensor.linky_XXXXXX_conso_hc`
- **Coût** (optionnel) : Utilisez les statistiques importées automatiquement

#### Pour le gaz :
- **Consommation de gaz** : `sensor.gazpar_XXXXXX_consumption`

### Visualisation dans l'historique

Grâce à l'import automatique des statistiques :
- Vos **données historiques** apparaissent immédiatement dans les graphiques
- L'historique complet est disponible depuis le **début du mois en cours**
- Les **coûts** sont également importés et visibles dans le tableau de bord

---

## 🤖 Services

### `octopus_french.force_update`

Force un rafraîchissement immédiat des données depuis l'API Octopus Energy.

**Exemple :**
```yaml
service: octopus_french.force_update
```

**Utilisation recommandée :**
- Après une modification de contrat
- Pour obtenir les dernières données sans attendre l'intervalle automatique
- En cas de problème de synchronisation

---

## 💡 Exemples d'automatisations

### Notification en cas de facture élevée
```yaml
automation:
  - alias: "Alerte facture élevée"
    trigger:
      - platform: numeric_state
        entity_id: sensor.compte_octopus_energy_facture_electricite
        above: 100
    action:
      - service: notify.mobile_app_votre_telephone
        data:
          title: "💰 Alerte facture élevée"
          message: >
            Votre facture d'électricité est de
            {{ states('sensor.compte_octopus_energy_facture_electricite') }}€
```

### Suivi de consommation quotidienne
```yaml
automation:
  - alias: "Rapport consommation quotidien"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: notify.mobile_app_votre_telephone
        data:
          title: "⚡ Rapport du jour"
          message: >
            Consommation aujourd'hui :
            {{ state_attr('sensor.linky_XXXXXX_latest_reading', 'heures_pleines_kwh') | float(0) +
               state_attr('sensor.linky_XXXXXX_latest_reading', 'heures_creuses_kwh') | float(0) }} kWh

            Coût estimé :
            {{ state_attr('sensor.linky_XXXXXX_latest_reading', 'cout_heures_pleines_euro') | float(0) +
               state_attr('sensor.linky_XXXXXX_latest_reading', 'cout_heures_creuses_euro') | float(0) }} €
```

### Alerte statut de paiement
```yaml
automation:
  - alias: "Alerte paiement programmé"
    trigger:
      - platform: state
        entity_id: sensor.compte_octopus_energy_facture_electricite
        attribute: payment_status
        to: "scheduled"
    action:
      - service: notify.notify
        data:
          title: "💳 Paiement programmé"
          message: >
            Un paiement de {{ states('sensor.compte_octopus_energy_facture_electricite') }}€
            est prévu le {{ state_attr('sensor.compte_octopus_energy_facture_electricite', 'expected_payment_date') }}
```

### Surveillance de l'index du compteur
```yaml
automation:
  - alias: "Mise à jour index mensuelle"
    trigger:
      - platform: time
        at: "01:00:00"
    condition:
      - condition: template
        value_template: "{{ now().day == 1 }}"
    action:
      - service: notify.notify
        data:
          title: "📊 Index du mois"
          message: >
            Index début de mois :
            HP: {{ states('sensor.linky_XXXXXX_index_hp') }} kWh
            HC: {{ states('sensor.linky_XXXXXX_index_hc') }} kWh
```

---

## 🔧 Dépannage

### Les entités n'apparaissent pas
- ✅ Vérifiez que vos identifiants sont corrects
- ✅ Assurez-vous que votre compte a des compteurs actifs
- ✅ Redémarrez Home Assistant après l'installation
- ✅ Vérifiez les logs : `Paramètres → Système → Logs`

### Les données ne se mettent pas à jour
- ✅ Vérifiez l'intervalle de mise à jour dans les options de l'intégration
- ✅ Utilisez le service `octopus_french.force_update` pour forcer le rafraîchissement
- ✅ Vérifiez la connectivité API dans les logs Home Assistant
- ✅ Consultez l'état de l'API Octopus Energy sur leur site

### Compteurs résiliés
- ℹ️ Les compteurs résiliés (statut `RESIL` et `LIMI`) sont automatiquement exclus
- ℹ️ Seuls les compteurs actifs apparaissent dans l'intégration

### Données de consommation manquantes
- ⏱️ Certaines données peuvent prendre 24-48h après l'installation du compteur
- ⏱️ Les relevés quotidiens sont mis à jour avec un délai de 24h
- ✅ Vérifiez la disponibilité des données sur le site Octopus Energy

### Les statistiques n'apparaissent pas dans le tableau de bord Énergie
- ✅ Patientez quelques minutes après l'installation (import en cours)
- ✅ Vérifiez que les entités ont bien `state_class: total_increasing`
- ✅ Consultez les logs pour d'éventuelles erreurs d'import
- ✅ Forcez une mise à jour avec le service `force_update`

### Problèmes d'authentification
- 🔐 L'intégration gère automatiquement le rafraîchissement des tokens
- 🔐 En cas d'erreur répétée, supprimez et réinstallez l'intégration
- 🔐 Vérifiez que vous pouvez vous connecter sur le site Octopus Energy

---

## 📝 Notes techniques

### Fréquence de mise à jour
- **Données de consommation** : Selon l'intervalle configuré (défaut : 60 min)
- **Relevés Linky** : Disponibles avec ~24h de décalage
- **Index des compteurs** : Mis à jour quotidiennement
- **Factures** : Mises à jour en temps réel

### Gestion de l'historique
- L'intégration importe **tout l'historique du mois en cours** lors de la première installation
- Les mises à jour suivantes ajoutent uniquement les **nouvelles données**
- Les statistiques sont stockées avec des **IDs uniques** par capteur
- Format des statistiques : **somme cumulative** (compatible Énergie)

### Structure des données
- **Dates** : Format ISO 8601 avec timezone UTC
- **Consommations** : En kWh avec 2 décimales
- **Coûts** : En euros avec 2 décimales
- **Index** : En kWh sans décimale

---

## 🆘 Support

- 🐛 **Problèmes** : [GitHub Issues](https://github.com/domodom30/ha-octopus-french/issues)
- 💬 **Discussions** : [GitHub Discussions](https://github.com/domodom30/ha-octopus-french/discussions)
- 📖 **Documentation** : [Wiki](https://github.com/domodom30/ha-octopus-french/wiki)

---

## 📜 Note

Cette intégration n'est pas officielle et n'est pas affiliée à Octopus Energy.