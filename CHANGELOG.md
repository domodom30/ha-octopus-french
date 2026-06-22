## [3.2.6] - 2026-06-22

### 🐛 Correction — Labels Effacement HPHC

Certains comptes (offre Effacement HPHC) renvoient les labels de consommation sous la forme `CONSUMPTION_EFFACEMENT_HPHC_2_HP_*` / `..._HC_*` au lieu des `HEURES_PLEINES` / `HEURES_CREUSES` historiques. Le matching exact échouait silencieusement : capteurs HP/HC du mois en cours bloqués à `0.0`, `last_imported_date` jamais renseigné et aucune statistique importée.

- Ajout de `normalize_consumption_label()` dans `utils.py` qui remappe uniquement les labels Effacement explicites vers leur forme canonique HP/HC (les labels legacy, Tempo OctoFlex et `ABONNEMENT` restent inchangés).
- Normalisation appliquée à l'import des statistiques, au calcul du total mensuel et aux attributs du dernier relevé dans `electricity.py`.

---

## [3.2.5] - 2026-06-15

### 🔧 Corrections OctoTempo — Alignement sur les labels réels de l'API

#### 🏷️ Renommage des couleurs Tempo (BREAKING pour les entités existantes)

Les labels de consommation retournés par l'API Octopus suivent le format `CONSUMPTION_OCTOFLEX_4_V4_{code}_0.0_37.0`. La convention `BLEU/BLANC/ROUGE` était hypothétique ; les codes réels de l'API sont `ETE` (été), `HIVER` (hiver) et `ROUGE`.

- Toutes les clés de capteurs `_bleu_` / `_blanc_` sont renommées en `_ete_` / `_hiver_` :
  - `energy_tempo_bleu_hp/hc` → `energy_tempo_ete_hp/hc`
  - `energy_tempo_blanc_hp/hc` → `energy_tempo_hiver_hp/hc`
  - `cost_tempo_bleu_hp/hc` → `cost_tempo_ete_hp/hc`
  - `cost_tempo_blanc_hp/hc` → `cost_tempo_hiver_hp/hc`
  - `rate_tempo_bleu_hp/hc` → `rate_tempo_ete_hp/hc`
  - `rate_tempo_blanc_hp/hc` → `rate_tempo_hiver_hp/hc`
- Les labels de statistiques sont mis à jour vers le format `CONSUMPTION_OCTOFLEX_4_V4_*` (ex. `CONSUMPTION_OCTOFLEX_4_V4_HPE_0.0_37.0`)
- Les valeurs `tempo_color` / `tempo_color_tomorrow` passent de `BLEU`/`BLANC` à `ETE`/`HIVER`
- Les codes alternatifs legacy (`BLEU_HP`, `BLANC_HP`) sont également mappés vers les nouvelles clés

#### 🐛 Corrections

- **Dérivation de couleur Tempo depuis `temporalClass`** : la couleur ETE/HIVER/ROUGE est désormais extraite directement depuis le code (`HPE`→`ETE`, `HPHI`→`HIVER`, `HPP`→`ROUGE`) lors du parsing de l'index, sans dépendre du champ `calendarTempClass`
- Les couleurs legacy BLEU/BLANC reçues via `calendarTempClass` sont converties en ETE/HIVER avant stockage

> ⚠️ **Migration** : Les entités `energy_tempo_bleu_*` et `energy_tempo_blanc_*` créées par les versions précédentes deviendront orphelines. Supprimez-les manuellement dans **Paramètres → Appareils et services** ou via les outils de nettoyage des entités HA.

---

## [3.2.4] - 2026-06-13

### ✨ Nouveautés — Support complet OctoTempo

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A1V11ZZTPI)

#### 🟦 Nouveaux capteurs OctoTempo

- **Couleur Tempo de demain** (`tempo_color_tomorrow`) : couleur annoncée par RTE (~11h) pour anticiper les pics tarifaires ; capteur `unavailable` avant l'annonce
- **Tarif Tempo en cours** (`tempo_current_rate`) : affiche le €/kWh actif à l'instant (couleur du jour × période HC/HP), mis à jour chaque minute

#### 🐛 Corrections

- **Fix : statistiques des capteurs de coût OctoTempo** (`cost_tempo_bleu_hp`, etc.) : les statistiques n'étaient pas importées dans la base de données HA (condition codée en dur dans `_async_import_statistics`). La constante `_COST_TO_CONSUMPTION_LABEL` est maintenant partagée entre l'import de statistiques et le calcul mensuel.

#### 🔧 Améliorations

- **Capteur `latest_reading`** : les attributs exposent désormais le détail Tempo du dernier relevé (kWh par couleur-période et coût estimé, ex: `tempo_bleu_hp`, `cout_tempo_rouge_hc_euro`)
- **Capteur couleur du jour** : paramétré pour supporter indifféremment aujourd'hui et demain (un seul code, `is_tomorrow`)
- **Capteur binaire HC** : fonctionne maintenant pour les contrats Tempo (détection de la période HC via les plages horaires du contrat)

---

## [3.2.3] - 2026-06-08

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A1V11ZZTPI)

### 🐛 Corrections

- Fix: `AttributeError` lors de l'ajout de l'intégration avec des credentials invalides & non capturée dans le config flow ([#41](https://github.com/domodom30/ha-octopus-french/issues/41))

---

## [3.2.2] - 2026-05-14

### 🐛 Corrections

- Fix: erreur d'authentification (réseau, API indisponible) traitée comme `UpdateFailed` → l'intégration réessaie automatiquement sans bloquer ni demander une reconfiguration
- Fix: message d'erreur dupliqué `Authentication failed: Authentication failed: invalid credentials` réduit à un seul préfixe
- Fix: log debug `First reading` déclenché pour chaque lecture au lieu d'une seule fois par cycle d'import de statistiques

---

## [3.2.0] - 2026-05-05

### ✨ Nouveautés

#### 🚗 Support complet Octopus Intelligent

> **Contributeur** : [@jeremygovi](https://github.com/jeremygovi) via [PR #31](https://github.com/domodom30/ha-octopus-french/pull/31)

- **Interrupteur Recharge Rapide** (`switch`) : Active/désactive la recharge immédiate (boost charge)
  - Gestion automatique des états (BOOSTING, SMART_CONTROL_IN_PROGRESS, etc.)
  - Attributs avec raisons de refus en cas d'échec (BC_DEVICE_DISCONNECTED, BC_DEVICE_FULLY_CHARGED, etc.)

- **Entité Number** : Cible SOC (State of Charge) pour la recharge
  - Plage : 0-100% par pas de 5%
  - Configuration séparée semaine/weekend

- **Entité Select** : Heure cible de recharge
  - Créneaux de 30 minutes (00:00 à 23:30)
  - Permet de définir l'heure de fin de charge souhaitée

- **Capteurs de monitoring** :
  - Statut du dispositif VE (SMART_CONTROL_CAPABLE, BOOSTING, etc.)
  - Cible SOC semaine/weekend
  - Heure cible semaine/weekend
  - Fenêtres de recharge planifiées (dispatches flex)

#### 🏗️ Architecture améliorée
- Nouveau coordinateur dédié (`OctopusIntelligentDataUpdateCoordinator`)
- Client API Intelligent séparé (`api/intelligent.py`)
- Support GraphQL pour l'API Kraken
- Création automatique d'appareils pour les véhicules électriques

### 🐛 Corrections
- Fix: GraphQL query date to retrieve dynamic tariffs instead of a static 2026 date
- Implement local calculation for monthly costs based on real consumption and active tariffs (fixing 0€ values)
- Add 'subscribed_power' sensor (kVA) with Apparent Power device class
- Adjust state classes for energy sensors (total_increasing) and monetary sensors (total) to fix Energy Dashboard compatibility and log errors
- Fix: long-term statistics for the 'pot_ledger' (cagnotte) sensor

### ⚙️ Technique
- Ajout dépendance `PyJWT==2.10.1` pour authentification Kraken API
- Structure modulaire avec support multi-plateformes (binary_sensor, number, select, sensor, switch)
- Gestion robuste des erreurs avec codes de refus spécifiques

---

## [3.0.2] - 2026-05-03

### 🐛 Bug Fixes
- Fix: GraphQL query date to retrieve dynamic tariffs instead of a static 2026 date
- Implement local calculation for monthly costs based on real consumption and active tariffs (fixing 0€ values)
- Add 'subscribed_power' sensor (kVA) with Apparent Power device class
- Adjust state classes for energy sensors (total_increasing) and monetary sensors (total) to fix Energy Dashboard compatibility and log errors
- Add 'pyjwt' requirement in manifest.json for Kraken API authentication
- Fix: long-term statistics for the 'pot_ledger' (cagnotte) sensor

## [3.0.1] - 2026-02-23

### 🐛 Bug Fixes
- Fix: state_class": SensorStateClass.TOTAL_INCREASING

---
