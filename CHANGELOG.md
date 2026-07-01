## [3.3.1] - 2026-07-01

### 🐛 Correction — HTTP 400 sur la requête `getAccountData` (régression 3.3.0)

Depuis la 3.3.0, la requête principale `getAccountData` renvoyait `HTTP 400` (rejet à la validation GraphQL) et bloquait toute la récupération de données.

Cause : le bloc `temporalClass { … }` ajouté (issue #37) sur le nœud `consumptionRates` n'est pas un champ valide sur ce type — contrairement à `electricityReading` où il fonctionne.

- Suppression du bloc `temporalClass` de la requête `getAccountData`. Le mapping des tarifs Tempo reste correct via le fallback par ordre de prix (déjà corrigé pour #37) ; le code de parsing est inchangé.
- `_async_execute` journalise désormais le **corps** des réponses non‑200 (tronqué à 500 caractères) pour diagnostiquer plus vite les erreurs GraphQL.

---

## [3.3.0] - 2026-07-01

Cette version corrige deux problèmes liés aux statistiques long-terme électricité alimentant le tableau de bord Énergie (issues #45 et #46).

### 🐛 Correction — Statistiques long-terme figées jusqu'au redémarrage (issue #45)

Les statistiques long-terme d'électricité (`octopus_french:<prm>_energy_*`, `_cost_*`) n'étaient importées **qu'une seule fois par session** puis figées : les relevés quotidiens publiés par Enedis avec 2-3 jours de retard n'étaient pris en compte qu'après un redémarrage de HA, un rechargement de l'intégration ou un changement de mois. Le tableau de bord Énergie restait bloqué sur le dernier relevé connu.

Cause : `_handle_coordinator_update` ne déclenchait l'import que tant que `_statistics_imported` était `False`, flag positionné à `True` dès le premier import. Le fichier `gas.py` portait la condition inversée, fragile pour la même raison.

- Suppression du verrou « one-shot » dans `electricity.py` et `gas.py` : l'import (déjà idempotent grâce à `get_last_statistics` + dédup par jour calendaire) tourne désormais à chaque cycle du coordinator.

### 🐛 Correction — Consommation journalière doublée/quadruplée dans le tableau de bord Énergie (issue #46)

Certains jours, la statistique externe `octopus_french:<prm>_energy_*` affichait une consommation doublée voire quadruplée, notamment après un « force refresh », et le doublement restait figé en permanence.

Cause (≤ 3.2.7) : la déduplication comparait des **chaînes ISO avec des fuseaux différents** (`_last_imported_date` rendu en UTC vs `startAt` en heure locale). Autour de minuit, `"2026-06-16T00:00:00+02:00" <= "2026-06-15T22:00:00+00:00"` est `False` alors que les deux désignent le même instant : le jour n'était pas ignoré et était ré-ajouté à chaque fenêtre chevauchante (mois courant + 7 jours), gonflant le cumul.

> Pour des barres corrompues plus anciennes que la fenêtre glissante (~37 jours), une purge ponctuelle via **Outils de développement → Statistiques** reste nécessaire ; le repeuplement se fait ensuite correctement.

---

## [3.2.7] - 2026-06-23

### 🐛 Correction — Inversion des tarifs Tempo Hiver HP / Rouge HC (issue #37)

Sur les comptes OctoTempo, les tarifs **Hiver HP** et **Rouge HC** étaient permutés (ex. Hiver HP affiché à `0,1575 €/kWh` au lieu de `0,1871`, et Rouge HC à `0,1871` au lieu de `0,1575`).

Cause : la requête `consumptionRates` ne demandait pas le champ `temporalClass`, si bien que le mapping fiable par code (`HPHI`→`tempo_hiver_hp`, `HCP`→`tempo_rouge_hc`) n'était jamais emprunté.

- Ajout du bloc `temporalClass { code label registerId }` à la requête `consumptionRates` dans `octopus_french.py`

---

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
