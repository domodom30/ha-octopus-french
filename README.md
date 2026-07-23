# Octopus Energy France pour Home Assistant

[![GitHub Release](https://img.shields.io/github/release/domodom30/ha-octopus-french)](https://github.com/domodom30/ha-octopus-french/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![installation_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.octopus_french.total)

Intégration Octopus Energy France (non officiel) pour Home Assistant.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A1V11ZZTPI)

---

## 🌟 Fonctionnalités

### 📊 Suivi de la consommation

- **Consommation électrique**
  - Mode BASE : consommation et coût mensuel
  - Mode HPHC : consommation et coût mensuel (heures pleines / heures creuses)
  - **Mode OctoTempo** : consommation et coût mensuel par couleur × période (6 capteurs : Été HP/HC, Hiver HP/HC, Rouge HP/HC)
  - **Statistiques historiques** : Import automatique de l'historique dans le tableau de bord Énergie
  - **Dernier relevé** : Valeur et détails de la dernière lecture quotidienne (avec ventilation Tempo si applicable)
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

### ⚡ Recharge Intelligente (Octopus Intelligent)

Octopus Energy propose un service « [Intelligent Recharge](https://octopusenergy.fr/intelligent-octopus) » permettant de planifier la recharge d'un véhicule électrique à tarif réduit (8 cts/kWh).

Cette intégration ajoute le support complet de cette fonctionnalité dans Home Assistant :

- **Interrupteur Recharge Rapide** : déclenche ou annule une recharge immédiate hors planning
- **Interrupteur Contrôle Intelligent** : suspend ou rétablit le pilotage automatique Octopus. Suspendre empêche Octopus d'interrompre une session de charge qu'il n'a pas planifiée, sans le coût d'un boost.
- **Capteur État du Dispositif VE** : affiche le statut courant du véhicule (SMART_CONTROL_CAPABLE, BOOSTING, SMART_CONTROL_IN_PROGRESS, etc.).
- **Capteurs** : cible SOC semaine/weekend, heure cible, fenêtres de dispatch planifiées.

> **Contributeur** : [@jeremygovi](https://github.com/jeremygovi) via [PR #31](https://github.com/domodom30/ha-octopus-french/pull/31)

### ⚙️ Fonctionnalités avancées

- **Mise à jour automatique** toutes les 60 minutes (5 minutes pour les données Intelligent)
- **Service de mise à jour forcée** pour rafraîchir immédiatement
- **Compatible avec le tableau de bord Énergie** de Home Assistant
- **Gestion automatique de l'authentification** : rafraîchissement des tokens, conservés entre les redémarrages
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

### Fréquence de rafraîchissement

Les données sont rafraîchies automatiquement toutes les **60 minutes** (5 minutes pour Octopus Intelligent). Le service `octopus_french.force_update` permet un rafraîchissement immédiat.

---

## 📋 Entités créées

### 🏢 Appareil Compte (Compte Octopus Energy)

| Entité              | Type    | Classe   | Description                                |
| ------------------- | ------- | -------- | ------------------------------------------ |
| Solde cagnotte      | Capteur | Monetary | Solde de la cagnotte (POT_LEDGER)          |
| Facture électricité | Capteur | Monetary | Montant de la dernière facture électricité |
| Facture gaz         | Capteur | Monetary | Montant de la dernière facture gaz         |

**Attributs des factures :**

- `payment_status` : Statut du paiement (scheduled, pending, cleared, failed, etc.)
- `total_amount` : Montant total de la facture
- `customer_amount` : Part client
- `expected_payment_date` : Date de paiement prévue

---

### ⚡ Appareil Compteur Électrique (Linky)

#### Capteurs principaux

**Pour les contrats BASE :**

| Entité       | Type    | Classe   | State Class | Description                              |
| ------------ | ------- | -------- | ----------- | ---------------------------------------- |
| Consommation | Capteur | Energy   | Total       | Consommation BASE (kWh) du mois en cours |
| Coût         | Capteur | Monetary | Total       | Coût BASE (€) du mois en cours           |
| Abonnement   | Capteur | Monetary | Total       | Coût mensuel de l'abonnement             |
| Contrat      | Capteur | -        | -           | Type de contrat et informations          |

**Pour les contrats HPHC (Heures Pleines / Heures Creuses) :**

| Entité          | Type    | Classe   | State Class | Description                       |
| --------------- | ------- | -------- | ----------- | --------------------------------- |
| Consommation HP | Capteur | Energy   | Total       | Consommation heures pleines (kWh) |
| Consommation HC | Capteur | Energy   | Total       | Consommation heures creuses (kWh) |
| Coût HP         | Capteur | Monetary | Total       | Coût heures pleines (€)           |
| Coût HC         | Capteur | Monetary | Total       | Coût heures creuses (€)           |
| Abonnement      | Capteur | Monetary | Total       | Coût mensuel de l'abonnement      |
| Contrat         | Capteur | -        | -           | Type de contrat et informations   |

**Pour les contrats OctoTempo :**

| Entité                | Type    | Classe   | State Class | Description                                  |
| --------------------- | ------- | -------- | ----------- | -------------------------------------------- |
| Consommation été HP   | Capteur | Energy   | Total       | Consommation jours Été Heures Pleines (kWh)  |
| Consommation été HC   | Capteur | Energy   | Total       | Consommation jours Été Heures Creuses (kWh)  |
| Consommation hiver HP | Capteur | Energy   | Total       | Consommation jours Hiver Heures Pleines (kWh)|
| Consommation hiver HC | Capteur | Energy   | Total       | Consommation jours Hiver Heures Creuses (kWh)|
| Consommation rouge HP | Capteur | Energy   | Total       | Consommation jours Rouge Heures Pleines (kWh)|
| Consommation rouge HC | Capteur | Energy   | Total       | Consommation jours Rouge Heures Creuses (kWh)|
| Coût été HP           | Capteur | Monetary | Total       | Coût jours Été HP (€)                        |
| Coût été HC           | Capteur | Monetary | Total       | Coût jours Été HC (€)                        |
| Coût hiver HP         | Capteur | Monetary | Total       | Coût jours Hiver HP (€)                      |
| Coût hiver HC         | Capteur | Monetary | Total       | Coût jours Hiver HC (€)                      |
| Coût rouge HP         | Capteur | Monetary | Total       | Coût jours Rouge HP (€)                      |
| Coût rouge HC         | Capteur | Monetary | Total       | Coût jours Rouge HC (€)                      |
| Abonnement            | Capteur | Monetary | Total       | Coût mensuel de l'abonnement                 |
| Contrat               | Capteur | -        | -           | Type de contrat et informations              |

**Capteurs de diagnostic OctoTempo :**

| Entité                   | Type    | Classe | Description                                                                              |
| ------------------------ | ------- | ------ | ---------------------------------------------------------------------------------------- |
| Tarif été HP             | Capteur | -      | Tarif Été Heures Pleines (€/kWh)                                                         |
| Tarif été HC             | Capteur | -      | Tarif Été Heures Creuses (€/kWh)                                                         |
| Tarif hiver HP           | Capteur | -      | Tarif Hiver Heures Pleines (€/kWh)                                                       |
| Tarif hiver HC           | Capteur | -      | Tarif Hiver Heures Creuses (€/kWh)                                                       |
| Tarif rouge HP           | Capteur | -      | Tarif Rouge Heures Pleines (€/kWh)                                                       |
| Tarif rouge HC           | Capteur | -      | Tarif Rouge Heures Creuses (€/kWh)                                                       |
| Couleur Tempo aujourd'hui| Capteur | -      | Couleur du jour (ETE / HIVER / ROUGE)                                                    |
| Couleur Tempo demain     | Capteur | -      | Couleur de demain — disponible après ~11h (annonce RTE) ; `unavailable` avant l'annonce  |
| Tarif Tempo en cours     | Capteur | -      | €/kWh actif à l'instant (couleur du jour × HC/HP), mis à jour chaque minute              |

---

#### Capteurs d'index (Diagnostic)

**Pour les contrats BASE :**

| Entité | Type    | Classe | Description                   |
| ------ | ------- | ------ | ----------------------------- |
| Index  | Capteur | Energy | Index actuel du compteur BASE |

**Pour les contrats HPHC :**

| Entité   | Type    | Classe | Description                 |
| -------- | ------- | ------ | --------------------------- |
| Index HP | Capteur | Energy | Index actuel heures pleines |
| Index HC | Capteur | Energy | Index actuel heures creuses |

**Attributs des index :**

- `prm_id` : Identifiant PRM
- `index_start` : Index de départ de la période
- `consumption` : Consommation sur la période
- `period_start` : Début de période de relevé
- `period_end` : Fin de période de relevé
- `index_reliability` : Fiabilité de l'index (REAL/ESTIMATED)

#### Capteur binaire Heures Creuses (HPHC et OctoTempo)

| Entité                  | Type           | Description                                                 |
| ----------------------- | -------------- | ----------------------------------------------------------- |
| HC Active               | Capteur binaire | Indique si l'heure actuelle est en période heures creuses   |

**États :**
- `ON` : Période heures creuses en cours
- `OFF` : Période heures pleines en cours

**Attributs :**
- `hc_source` : Source des horaires (`contract` = timeSlots du contrat, `linky` = label du compteur)
- `hc_type` : Type de période (HC par exemple)
- `total_hc_hours` : Nombre total d'heures creuses par jour
- `hc_schedule_available` : Horaires HC disponibles (true/false)
- `hc_range_X` : Plage horaire X (format `HH:MM - HH:MM`)
- `hc_range_X_duration_h` : Durée de la plage X (heures)

**Exemple d'utilisation :**
```yaml

  # Chauffe-eau allumé pendant les HC, éteint en HP
  # Remplacez switch.chauffe_eau par votre entité

  automation:
    - alias: "Octopus — Chauffe-eau ON en heures creuses"
      description: >
        Allume le chauffe-eau dès que les HC commencent,
        l'éteint dès qu'elles se terminent.
      triggers:
        - trigger: state
          entity_id: binary_sensor.octopus_french_hc_active
          to: "on"
          id: hc_debut
        - trigger: state
          entity_id: binary_sensor.octopus_french_hc_active
          to: "off"
          id: hc_fin
      conditions: []
      actions:
        - choose:
            - conditions:
                - condition: trigger
                  id: hc_debut
              sequence:
                - action: switch.turn_on
                  target:
                    entity_id: switch.chauffe_eau
                - action: notify.mobile_app_votre_telephone
                  data:
                    title: "⚡ Heures Creuses"
                    message: >
                      HC actives jusqu'à {{ state_attr('binary_sensor.octopus_french_hc_active', 'hc_range_1') }}.
                      Total : {{ state_attr('binary_sensor.octopus_french_hc_active', 'total_hc_hours') }} h
            - conditions:
                - conditions:
                  - condition: trigger
                    id: hc_fin
              sequence:
                - action: switch.turn_off
                  target:
                    entity_id: switch.chauffe_eau
```

#### Capteur dernier relevé (Diagnostic)

| Entité         | Type    | Classe | Description                        |
| -------------- | ------- | ------ | ---------------------------------- |
| Dernier relevé | Capteur | Energy | Valeur du dernier relevé quotidien |

**Attributs du dernier relevé :**

- `date_releve` : Date du relevé
- `heures_base` : Heures en base (contrat BASE)
- `heures_pleines_kwh` : Consommation heures pleines (contrat HPHC)
- `heures_creuses_kwh` : Consommation heures creuses (contrat HPHC)
- `cout_base_euro` : Coût base
- `cout_heures_pleines_euro` : Coût heures pleines
- `cout_heures_creuses_euro` : Coût heures creuses
- `cout_abonnement_euro` : Coût abonnement journalier
- `tempo_ete_hp` / `tempo_ete_hc` : kWh Été HP/HC (contrat OctoTempo)
- `tempo_hiver_hp` / `tempo_hiver_hc` : kWh Hiver HP/HC
- `tempo_rouge_hp` / `tempo_rouge_hc` : kWh Rouge HP/HC
- `cout_tempo_ete_hp_euro` … `cout_tempo_rouge_hc_euro` : coûts estimés par couleur-période

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

| Entité       | Type    | Classe   | State Class | Description                          |
| ------------ | ------- | -------- | ----------- | ------------------------------------ |
| Consommation | Capteur | Energy   | Total       | Consommation mensuelle de gaz (kWh)  |
| Coût         | Capteur | Monetary | Total       | Coût mensuel du gaz (€)              |
| Abonnement   | Capteur | Monetary | Total       | Coût mensuel de l'abonnement gaz     |
| Tarif        | Capteur | -        | -           | Prix du kWh gaz (€/kWh, diagnostic)  |
| Contrat      | Capteur | -        | -           | Type de contrat et informations      |

**Attributs du contrat gaz :**

- `pce_ref` : Référence PCE
- `ledger_id` : Numéro de registre associé
- `gas_nature` : Type de gaz (Naturel/Propane)
- `annual_consumption` : Consommation annuelle estimée (kWh)
- `is_smart_meter` : Compteur communicant (Gazpar)
- `powered_status` : État de la connexion (En service/Coupé)

---

### 🚗 Appareil Véhicule Électrique (Octopus Intelligent)

> **Note :** Ces entités ne sont créées que si vous êtes abonné au service Octopus Intelligent et qu'un véhicule électrique est enregistré sur votre compte.
>
> **Contributeur** : [@jeremygovi](https://github.com/jeremygovi) via [PR #31](https://github.com/domodom30/ha-octopus-french/pull/31)

#### Interrupteur

| Entité          | Type         | Description                                                               |
| --------------- | ------------ | ------------------------------------------------------------------------- |
| Recharge rapide | Interrupteur | Active/désactive la recharge rapide immédiate (mode BOOSTING) hors planning |
| Contrôle intelligent | Interrupteur | Suspend/rétablit le pilotage automatique Octopus (empêche l'interruption d'une charge non planifiée, sans coût de boost) |

**Attributs de l'interrupteur :**
- `current` : État de connexion du véhicule (LIVE/autre)
- `current_state` : État actuel de charge détaillé (BOOSTING, SMART_CONTROL_IN_PROGRESS, etc.)
- `refusal_reasons` : Liste des raisons de refus si l'action a échoué
  - `BC_DEVICE_DISCONNECTED` : Véhicule non connecté
  - `BC_DEVICE_FULLY_CHARGED` : Batterie déjà pleine
  - `BC_DEVICE_NOT_READY` : Dispositif non prêt
  - Autres codes d'erreur API

#### Entités de configuration

| Entité                  | Type   | Plage        | Description                                                |
| ----------------------- | ------ | ------------ | ---------------------------------------------------------- |
| Cible SOC               | Number | 0-100% (5%)  | Niveau de charge souhaité pour la batterie                 |
| Heure cible de recharge | Select | 00:00-23:30  | Heure à laquelle la charge doit être terminée              |

**Fonctionnement :**
- Les valeurs sont appliquées à tous les jours de la semaine
- Le système Octopus Intelligent calcule automatiquement l'heure de début de charge optimale
- Les modifications sont envoyées immédiatement à l'API Octopus

#### Capteurs de monitoring

| Entité                       | Type    | Description                                                         |
| ---------------------------- | ------- | ------------------------------------------------------------------- |
| Statut de charge             | Capteur | État actuel du véhicule et de la charge                             |
| Cible SOC semaine            | Capteur | Niveau de charge cible configuré pour les jours de semaine (%)      |
| Heure cible semaine          | Capteur | Heure de fin de charge cible pour les jours de semaine              |
| Cible SOC weekend            | Capteur | Niveau de charge cible configuré pour le weekend (%)                |
| Heure cible weekend          | Capteur | Heure de fin de charge cible pour le weekend                        |
| Fenêtres dispatch planifiées | Capteur | Créneaux de recharge intelligente planifiés (format JSON)           |

**États possibles du capteur de statut :**
- `SMART_CONTROL_CAPABLE` : Véhicule prêt, contrôle intelligent disponible
- `BOOSTING` : Recharge rapide (boost) en cours
- `SMART_CONTROL_IN_PROGRESS` : Recharge intelligente planifiée en cours
- `CHARGING` : En charge
- `NOT_CONNECTED` : Véhicule non connecté
- `READY` : Prêt à charger
- Et autres états spécifiques API

**Attributs des capteurs :**
- `device_id` : Identifiant unique du véhicule
- `name` : Nom du véhicule configuré dans Octopus
- `current` : État de connexion actuel
- `planned_dispatches` : Liste des créneaux de charge (start/end)

#### 🎯 Cas d'usage

**Automatisation : Boost avant départ**
```yaml
automation:
  - alias: "Recharge rapide avant 8h"
    trigger:
      - platform: time
        at: "07:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.vehicule_weekday_target_soc
        below: 80
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.vehicule_bump_charge
```

**Notification si recharge refusée**
```yaml
automation:
  - alias: "Alerte boost refusé"
    trigger:
      - platform: state
        entity_id: switch.vehicule_bump_charge
        attribute: refusal_reasons
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.refusal_reasons | length > 0 }}"
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Recharge refusée"
          message: >
            Raison : {{ trigger.to_state.attributes.refusal_reasons | join(', ') }}
```

---

## 📊 Intégration Tableau de bord Énergie

Cette intégration est **entièrement compatible** avec le tableau de bord Énergie de Home Assistant et importe automatiquement l'historique des consommations.

### ✨ Import automatique des statistiques

L'intégration importe automatiquement l'historique de vos consommations et coûts dans Home Assistant :

- **Import complet** lors de la première installation
- **Mise à jour incrémentale** lors des rafraîchissements suivants
- **Coûts basés sur les montants réels de l'API** (exacts même après un changement de tarif)
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

#### Pour un contrat OctoTempo :

- **Consommation depuis le réseau** (6 capteurs) :
  - `sensor.linky_XXXXXX_energy_tempo_ete_hp`
  - `sensor.linky_XXXXXX_energy_tempo_ete_hc`
  - `sensor.linky_XXXXXX_energy_tempo_hiver_hp`
  - `sensor.linky_XXXXXX_energy_tempo_hiver_hc`
  - `sensor.linky_XXXXXX_energy_tempo_rouge_hp`
  - `sensor.linky_XXXXXX_energy_tempo_rouge_hc`
- **Coût** (optionnel) : Statistiques importées automatiquement pour chaque couleur-période

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

### OctoTempo — Alerte jour rouge demain

```yaml
automation:
  - alias: "OctoTempo — Alerte jour rouge demain"
    trigger:
      - platform: state
        entity_id: sensor.linky_XXXXXX_tempo_color_tomorrow
        to: "ROUGE"
    action:
      - service: notify.mobile_app_votre_telephone
        data:
          title: "🔴 Jour Rouge demain !"
          message: >
            Demain est un jour Rouge OctoTempo.
            Tarif HP : {{ states('sensor.linky_XXXXXX_rate_tempo_rouge_hp') }} €/kWh.
            Pensez à décaler vos usages énergivores.
```

### OctoTempo — Suivi du tarif en cours

```yaml
automation:
  - alias: "OctoTempo — Notification passage en Rouge HP"
    trigger:
      - platform: template
        value_template: >
          {{ states('sensor.linky_XXXXXX_tempo_color_today') == 'ROUGE'
             and is_state('binary_sensor.linky_XXXXXX_hc_active', 'off') }}
    action:
      - service: notify.mobile_app_votre_telephone
        data:
          title: "🔴 Rouge HP en cours"
          message: >
            Tarif actif : {{ states('sensor.linky_XXXXXX_tempo_current_rate') }} €/kWh.
            Limitez votre consommation.
```

### OctoTempo — Délestage automatique les jours rouges HP

```yaml
automation:
  - alias: "OctoTempo — Délestage chauffe-eau Rouge HP"
    trigger:
      - trigger: state
        entity_id: sensor.linky_XXXXXX_tempo_color_today
        to: "ROUGE"
      - trigger: state
        entity_id: binary_sensor.linky_XXXXXX_hc_active
        to: "off"
    condition:
      - condition: state
        entity_id: sensor.linky_XXXXXX_tempo_color_today
        state: "ROUGE"
      - condition: state
        entity_id: binary_sensor.linky_XXXXXX_hc_active
        state: "off"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.chauffe_eau
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

## ⚡ Recharge Intelligente Octopus Intelligent (Détails)

> **Contributeur** : [@jeremygovi](https://github.com/jeremygovi) via [PR #31](https://github.com/domodom30/ha-octopus-french/pull/31)

### 📋 Présentation

Octopus Energy propose un service « [Intelligent Octopus](https://octopusenergy.fr/intelligent-octopus) » permettant de planifier la recharge d'un véhicule électrique à tarif réduit (8 cts/kWh).

Cette intégration ajoute le **support complet** de cette fonctionnalité dans Home Assistant avec contrôles, capteurs et automatisations.

### 🎛️ Contrôles

#### Interrupteur Recharge Rapide (`switch.bump_charge`)

Déclenche ou annule une recharge immédiate hors planning.

- **ON** : Active le mode BOOSTING pour une recharge instantanée
- **OFF** : Désactive pour reprendre le planning intelligent
- **Attributs** : Affiche les raisons de refus en cas d'échec (`refusal_reasons`)

#### Number : Cible SOC (`number.target_soc`)

Définit le niveau de charge souhaité (State of Charge).

- **Plage** : 0-100%
- **Pas** : 5% pour un ajustement précis
- **Application** : Appliqué à tous les jours de la semaine

#### Select : Heure Cible (`select.target_time`)

Définit l'heure de fin de charge souhaitée.

- **Créneaux** : 30 minutes (00:00, 00:30, 01:00, ..., 23:30)
- **Planification** : Le système Octopus calcule automatiquement l'heure de début optimale

### 📊 Capteurs de Monitoring

| Capteur | ID | Description |
|---------|----|-----------  |
| **Statut du Dispositif VE** | `sensor.vehicle_status` | État courant du véhicule |
| **Cible SOC Semaine** | `sensor.weekday_target_soc` | Niveau de charge cible (%) pour les jours de semaine |
| **Heure Cible Semaine** | `sensor.weekday_target_time` | Heure de fin de charge pour les jours de semaine |
| **Cible SOC Weekend** | `sensor.weekend_target_soc` | Niveau de charge cible (%) pour le weekend |
| **Heure Cible Weekend** | `sensor.weekend_target_time` | Heure de fin de charge pour le weekend |
| **Fenêtres de Dispatch** | `sensor.planned_dispatches` | Créneaux de recharge planifiés (format JSON) |

### 🔌 Codes d'État

**États du véhicule (`sensor.vehicle_status`) :**

| Code | Signification |
|------|--------------|
| `SMART_CONTROL_CAPABLE` | Véhicule prêt pour le contrôle intelligent |
| `BOOSTING` | Recharge rapide en cours (bump charge actif) |
| `SMART_CONTROL_IN_PROGRESS` | Recharge intelligente en cours |
| `CHARGING` | Recharge en cours |
| `NOT_CONNECTED` | Véhicule non connecté |

**Raisons de refus (attribut `refusal_reasons` du switch) :**

| Code | Signification |
|------|--------------|
| `BC_DEVICE_DISCONNECTED` | Véhicule non connecté à la borne |
| `BC_DEVICE_FULLY_CHARGED` | Véhicule déjà pleinement chargé |
| `BC_DEVICE_NOT_READY` | Dispositif non prêt à charger |

### 💡 Exemples d'Utilisation

#### Activer une recharge rapide

```yaml
service: switch.turn_on
target:
  entity_id: switch.vehicule_bump_charge
```

#### Définir une cible de 80%

```yaml
service: number.set_value
target:
  entity_id: number.vehicule_target_soc
data:
  value: 80
```

#### Planifier une charge pour 7h30

```yaml
service: select.select_option
target:
  entity_id: select.vehicule_target_time
data:
  option: "07:30"
```

#### Automatisation complète

```yaml
automation:
  - alias: "Charge VE à 80% pour 7h chaque soir"
    trigger:
      - platform: time
        at: "22:00:00"
    condition:
      - condition: state
        entity_id: binary_sensor.workday_sensor
        state: "on"
    action:
      - service: number.set_value
        target:
          entity_id: number.vehicule_target_soc
        data:
          value: 80
      - service: select.select_option
        target:
          entity_id: select.vehicule_target_time
        data:
          option: "07:00"
```

#### Notifications de statut

```yaml
automation:
  - alias: "Notifier quand la recharge boost démarre"
    trigger:
      - platform: state
        entity_id: sensor.vehicle_status
        to: "BOOSTING"
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Recharge rapide activée"
          message: "Votre véhicule est en mode BOOSTING"
```

---

## 🗑️ Désinstallation

1. Allez dans **Paramètres** → **Appareils et services**
2. Trouvez **Octopus Energy France**, ouvrez le menu (⋮) de l'entrée et choisissez **Supprimer**
3. Si installée via HACS : ouvrez **HACS**, recherchez l'intégration, menu (⋮) → **Supprimer**, puis redémarrez Home Assistant

> **Note** : les statistiques long-terme importées (identifiants `octopus_french:*`) restent dans la base du recorder après la désinstallation. Pour les purger, allez dans **Outils de développement** → **Statistiques** et cliquez sur **Corriger** (ou l'icône de suppression) en face des entrées `octopus_french` orphelines.

---

## 🔧 Dépannage

### Les entités n'apparaissent pas

- ✅ Vérifiez que vos identifiants sont corrects
- ✅ Assurez-vous que votre compte a des compteurs actifs
- ✅ Redémarrez Home Assistant après l'installation
- ✅ Vérifiez les logs : `Paramètres → Système → Logs`

### Les données ne se mettent pas à jour

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
- ✅ Consultez les logs pour d'éventuelles erreurs d'import
- ✅ Forcez une mise à jour avec le service `force_update`

### Problèmes d'authentification

- 🔐 L'intégration gère automatiquement le rafraîchissement des tokens
- 🔐 En cas d'erreur répétée, supprimez et réinstallez l'intégration
- 🔐 Vérifiez que vous pouvez vous connecter sur le site Octopus Energy

---

## 📝 Notes techniques

### Fréquence de mise à jour

- **Données de consommation** : Toutes les 60 minutes (Intelligent : 5 minutes)
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

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A1V11ZZTPI)

---

## 📜 Note

Cette intégration n'est pas officielle et n'est pas affiliée à Octopus Energy.

## Don

[![Support me on Liberapay](https://liberapay.com/assets/widgets/donate.svg)](https://liberapay.com/Domodom/donate)
