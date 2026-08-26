## [4.1.6] - 2026-08-26

### 🐛 Correction — Consommation et coût gaz bloqués à 0 (issue [#79](https://github.com/domodom30/ha-octopus-french/issues/79))

Les relevés gaz n'étaient demandés qu'à `property.measurements`. Cette source ne renvoie de mesures que pour les compteurs Gazpar qui en publient : ailleurs elle répond une liste vide, sans erreur, et la consommation comme le coût restaient à `0` — alors que le compteur, le contrat, l'abonnement et le tarif s'affichaient normalement, ce qui rendait le diagnostic trompeur. La requête `gasReading`, qui expose les relevés d'index de tous les compteurs, existait depuis la 1.6.0 mais n'était plus appelée depuis la 2.0.1.

Elle redevient la source de repli : quand `measurements` ne renvoie rien, les relevés d'index prennent le relais et leur consommation est répartie sur les jours de leur période. Une absence totale de relevé est désormais signalée au journal au lieu d'afficher un zéro silencieux, et l'attribut `source` des capteurs Consommation et Coût indique quelle source alimente la valeur. Merci à [@gregory-03](https://github.com/gregory-03).

### ✨ Amélioration — Statistiques gaz au jour le jour

Les relevés quotidiens des compteurs communicants sont maintenant collectés en plus des cumuls mensuels : la statistique `octopus_french:<PCE>_consumption` porte donc une courbe journalière au lieu d'un unique point au 1er du mois. Les compteurs sans relevé quotidien conservent une répartition calculée sur leurs périodes.

Les jours mesurés à 0 kWh sont conservés au lieu d'être écartés : ils laissaient autant de trous dans la courbe — 52 relevés ne donnaient que 41 points sur un mois et demi — et empêchaient l'import de recalculer ses sommes cumulées sur une série continue.

### ✨ Nouveau capteur — Dernier relevé gaz

Les relevés journaliers n'étaient lisibles que dans les statistiques long terme, sans entité pour les exposer. Le compteur Gazpar dispose maintenant d'un capteur **Dernier relevé**, équivalent de celui du Linky : valeur du dernier relevé réel, avec sa période, sa source (mesure quotidienne, relevé d'index ou cumul mensuel), son coût et, pour les relevés d'index, les index de début et de fin. La valeur affichée est toujours un relevé réel, jamais une moyenne.

Le README indique désormais quelle statistique choisir dans le tableau de bord Énergie pour obtenir une courbe journalière plutôt qu'un point par mois.

### 🚨 Correction — Statistiques gaz faussées au changement de granularité

Les relevés gaz n'étaient exposés que sous une seule granularité à la fois : les points déjà écrits sous l'ancienne restaient en base, la série n'était plus continue, et l'import prolongeait le cumul au lieu de le recalculer — en recomptant des périodes déjà importées. Sur un compte de test, la somme cumulée atteignait **67 402 kWh pour un compteur à 9 075 kWh/an**, avec un bond de 55 911 kWh sur un seul point. Le tableau de bord Énergie affichant des différences de somme, ce pic écrasait les consommations réelles, qui devenaient illisibles.

Les sources se superposent désormais du moins précis au plus précis — cumuls mensuels, relevés d'index, puis mesures quotidiennes qui remplacent l'estimation sur les jours qu'elles couvrent — et la série ne s'étend jamais au-delà de la dernière mesure connue. Continue, elle permet à l'import de recalculer ses sommes : **les bases déjà faussées se corrigent d'elles-mêmes au premier rafraîchissement**, sans intervention.

Deux défauts associés sont corrigés : le champ `endAt` n'était pas demandé à l'API, si bien qu'un cumul mensuel se retrouvait entièrement sur le 1er du mois au lieu d'être réparti ; et une erreur pendant l'import de l'électricité empêchait celui du gaz de démarrer.

### 🐛 Correction — Jours à 0 kWh écartés des statistiques électricité

Le même défaut que celui corrigé côté gaz existait sur l'électricité : un jour mesuré à 0 kWh — absence, coupure, véhicule non rechargé — était écarté de la série au lieu d'y figurer. Chaque zéro laissait donc un trou, et une série trouée fait basculer l'import sur son cumul incrémental au lieu de recalculer ses sommes : les valeurs déjà écrites, même fausses, n'étaient plus corrigées.

Les jours à 0 sont désormais conservés, pour l'énergie comme pour le coût. La série redevenue continue, **les sommes déjà faussées se corrigent d'elles-mêmes au premier rafraîchissement**. Un relevé sans valeur, lui, reste écarté : c'est une absence de mesure, pas une mesure à zéro.

### 🐛 Correction — Faux avertissement de label non reconnu sur les comptes Tempo

L'avertissement introduit en 4.1.5 pour signaler un label de consommation inconnu se déclenchait aussi sur les labels Tempo courts (`TEMPO_ETE_HP`, `TEMPO_ROUGE_HC`, …), alors qu'ils sont bien pris en charge et alimentent les attributs du capteur *dernier relevé*. Le message invitait donc à signaler un label qui fonctionne, et jetait le doute sur des capteurs corrects.

Ces labels sont maintenant reconnus explicitement, et leur liste — jusqu'ici dupliquée entre la normalisation et les capteurs — est centralisée.

### 🔍 Journalisation de l'import des statistiques

L'import ne laissait qu'une ligne de succès. Il journalise maintenant, en `debug`, la série calculée (nombre de jours, période, total, tarif appliqué et détail des dix derniers jours), la stratégie retenue — réécriture complète ou cumul incrémental — et les sommes d'ancrage et finale. Les sorties silencieuses (passe déjà en cours, série vide) laissent également une trace.

```yaml
logger:
  logs:
    custom_components.octopus_french: debug
```

### 🐛 Correction — Comptes à plusieurs compteurs gaz

Seul le premier PCE était interrogé, alors que des entités étaient créées pour chacun : les compteurs suivants restaient à 0. Chaque PCE récupère désormais ses propres relevés et ses propres statistiques, sur sa propre propriété — comme l'électricité depuis la 4.0.1.

### 🔒 Diagnostics

Les identifiants de compteur (PRM, PCE) servaient de clés de dictionnaire et échappaient donc à l'anonymisation du fichier de diagnostic. Ils sont maintenant masqués.

---

## [4.1.5] - 2026-08-25

### 🐛 Correction — Électricité absente quand le distributeur déclare le compteur résilié (issue [#75](https://github.com/domodom30/ha-octopus-french/issues/75))

`distributorStatus` décrit le contrat d'accès distributeur (Enedis), pas le contrat de fourniture : il reste à `RESIL` après un changement de fournisseur ou un déménagement, alors que le compteur est bel et bien alimenté et sous contrat. Tout point de livraison marqué `RESIL` était pourtant écarté, faisant disparaître **l'intégralité des entités électricité** de comptes actifs — sur un compte électricité + gaz, seul le gaz remontait.

Un `RESIL` n'est désormais retenu que s'il est confirmé par un `poweredStatus` à `LIMI` (puissance limitée). Le filtre était appliqué à deux endroits — points de livraison et registres comptables — les deux sont corrigés et la règle est centralisée en un seul point. Merci à [@Payou6994](https://github.com/Payou6994).

### 🐛 Correction — Cumul mensuel HP/HC bloqué à 0 (issue [#70](https://github.com/domodom30/ha-octopus-french/issues/70))

Le nom de l'offre est interpolé dans le label de consommation renvoyé par l'API (`CONSUMPTION_<OFFRE>_HP_…`). Le mappage ne reconnaissait que l'offre Effacement : sur toute autre offre, les cumuls mensuels restaient à 0 alors que les relevés étaient correctement collectés — `readings_count` juste et capteur « dernier relevé » fonctionnel, ce qui rendait le diagnostic difficile.

Le segment `HP` / `HC` est maintenant reconnu quelle que soit l'offre ; les labels OctoTempo conservent leur traitement propre. Un label non reconnu est désormais signalé au journal au lieu de laisser silencieusement un cumul à zéro. Merci à [@Maxxouille44](https://github.com/Maxxouille44).

### 🐛 Correction — Heure et charge cibles identiques sur plusieurs véhicules (issue [#77](https://github.com/domodom30/ha-octopus-french/issues/77))

Les préférences de recharge étaient lues via `vehicleChargingPreferences`, qui ne renvoie qu'un seul jeu **par compte**, alors que leur écriture se fait bien par appareil. Avec deux véhicules, l'heure cible et la charge cible affichées étaient donc les mêmes pour les deux.

Elles proviennent maintenant du champ `preferences` de chaque appareil — un créneau par jour, converti en cibles semaine et week-end. Les comptes dont les appareils n'exposent pas de créneaux conservent les préférences du compte. Merci à [@Vincenzoz59](https://github.com/Vincenzoz59).

---

## [4.1.4] - 2026-08-03

### 🚨 Correction bloquante — Plus aucune donnée récupérée en 4.1.3

La 4.1.3 demandait le champ `temporalClass` sur le nœud `consumptionRates`, où il n'existe pas. L'API rejetait **toute** la requête `getAccountData` :

```
HTTP 400 — Cannot query field 'temporalClass' on type 'SupplyConsumptionRateType'
```

Comptes, contrats, tarifs et points de livraison devenaient inaccessibles. Le champ est retiré, un commentaire de garde-fou est posé dans la requête et un test dédié empêche sa réintroduction — la même régression était déjà survenue en 3.3.0, corrigée en 3.3.1.

### 🐛 Correction — Inversion des tarifs Tempo Hiver HP / Rouge HC (issue [#37](https://github.com/domodom30/ha-octopus-french/issues/37))

Le correctif annoncé en 3.2.7 était **inopérant depuis son annulation en 3.3.1** : le bloc `temporalClass` ayant été retiré de `consumptionRates` pour lever le HTTP 400, le mapping des taux reposait depuis lors uniquement sur le tri par ordre de prix — juste tant que la grille conserve l'ordre `ete_hc < hiver_hc < rouge_hc < ete_hp < hiver_hp < rouge_hp`, faux dès qu'elle en dévie.

Le mapping par code est désormais réellement emprunté : les taux sont lus via `energySupplyRate.rates`, le seul champ dont les membres électricité (`ElectricitySupplyConsumptionRateType`) exposent `temporalClass`. Le tri par ordre de prix ne sert plus que de secours pour les comptes qui ne renvoient aucun code. Merci à [@harty911](https://github.com/harty911).

### ✨ Plages heures creuses OctoTempo lues sur l'API (issue [#68](https://github.com/domodom30/ha-octopus-french/issues/68))

Les horaires HC proviennent maintenant de `providerCalendar.temporalClasses[].description`, qui expose **une plage par classe temporelle** — donc par couleur sur un contrat OctoTempo (`HCE` / `HCHI` / `HCP`). Cela remplace les plages codées en dur introduites en 4.1.3, qui supposaient une souscription particulière et donnaient un état HC/HP faux pour toute autre.

Les sources sont désormais hiérarchisées et traçables :

1. `contract` — créneaux horaires du taux souscrit
2. `calendar` — description de la classe temporelle du calendrier fournisseur
3. `linky` — `offPeakLabel` du compteur, qui ne connaît qu'un seul jeu de plages
4. `none` — aucune plage exploitable, l'entité reste indisponible

Un nouvel attribut `hc_source` sur le binaire « Heures creuses actives » et sur le capteur « Tarif Tempo en cours » indique laquelle a été retenue. Un contrat Tempo contraint de se rabattre sur `offPeakLabel` le signale désormais au journal au lieu de le faire silencieusement. Merci à [@gaby49100](https://github.com/gaby49100).

---

## [4.1.3] - 2026-08-02

### 🐛 Corrections

Fix : [68](https://github.com/domodom30/ha-octopus-french/issues/68)

> ⚠️ Version à ne pas utiliser : elle empêche toute récupération de données (voir 4.1.4).

---

## [4.1.2] - 2026-07-26

### ✨ Conformité HA — Catégories d'entités

Les entités Octopus Intelligent sont désormais rangées dans les sections standard de la fiche appareil :

- **Configuration** : Charge cible, Heure cible, Contrôle intelligent
- **Diagnostic** : Statut de charge, Fenêtres de charge

Elles n'encombrent plus la vue principale ni les dashboards auto-générés. « Recharge rapide » reste en contrôle principal.

---

## [4.1.1] - 2026-07-23

### 🐛 Corrections

- **Interrupteur « Recharge rapide » (boost)** : le switch est désormais rattaché à l'appareil du **véhicule Octopus Intelligent** (via `via_device`) au lieu d'apparaître comme entité isolée. Il est ainsi regroupé avec les autres entités du véhicule. Merci à [@jeremygovi](https://github.com/jeremygovi).

---

## [4.1.0] - 2026-07-23

### ✨ Nouveautés

- **Interrupteur « Contrôle intelligent » (Octopus Intelligent)** : un nouveau switch par véhicule permet de **suspendre ou rétablir le pilotage automatique Octopus**. Contrairement au boost, suspendre le contrôle intelligent n'entraîne pas de coût — cela empêche simplement Octopus d'interrompre une session de charge qu'il n'a pas planifiée. Merci à [@Mathieu-Pasco-Breillot](https://github.com/Mathieu-Pasco-Breillot) pour la proposition initiale de cette fonctionnalité (PR #58).

---

## [4.0.1] - 2026-07-23

### 🐛 Corrections

- **Comptes multi-Linky (issue #56)** : sur un compte à plusieurs contrats/logements, les relevés de consommation sont désormais récupérés sur la **bonne propriété** pour chaque point de livraison. Les données ne sont plus mélangées ni dupliquées entre les deux compteurs.
- **Recharge Intelligent / charge cible (issue #55)** : la mutation `setDevicePreferences` déclarait des types GraphQL erronés (`String!`/`Int!`), rejetés par l'API (HTTP 400) et masqués en « endpoint injoignable ». Les types corrects (`ID!`/`Time!`/`Decimal!`) sont désormais utilisés — la charge cible, l'heure cible et la recharge rapide refonctionnent.

---

## [4.0.0] - 2026-07-22

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A1V11ZZTPI)

Version majeure : audit complet de l'intégration (fiabilité, authentification, statistiques). Aucune migration nécessaire — identifiants d'entités et de statistiques inchangés.

### 🐛 Corrections

- **OctoTempo** : les capteurs Contrat / Abonnement / Puissance souscrite étaient créés en double à chaque démarrage (collision d'`unique_id` dans les logs).
- **Ré-authentification** : des identifiants invalides au chargement déclenchent désormais le flux de reauth, au lieu de réessayer indéfiniment.
- **Comptes multiples** : si le compte configuré n'existe plus côté Octopus, le setup échoue explicitement au lieu de basculer en silence sur un autre compte.
- **Couleur Tempo de demain** : calculée en date locale (plus de décalage possible en soirée).
- Cohérence des identifiants de compteurs (PRM) entre toutes les plateformes ; le capteur HC et les attributs de contrat ne peuvent plus se retrouver orphelins.

### 🔐 Authentification & rate-limit Kraken

- Le **refresh token est conservé entre les redémarrages** de Home Assistant : plus de login e-mail/mot de passe complet à chaque restart, principale cause du rate-limit `KT-CT-1199`.
- Polling Octopus Intelligent ramené de 1 à **5 minutes**, requêtes parallélisées.

### 📊 Statistiques & coûts

- **Import des statistiques centralisé** : une seule passe par cycle au lieu d'une tâche par capteur — moins de charge sur le recorder, comportement identique (idempotence, réparation des sommes corrompues).
- **Coûts électricité** : utilisation des montants réels de l'API (`costInclTax`) — les coûts historiques restent exacts après un changement de tarif ; repli sur kWh × tarif si absent.

### 🔧 Interne

- `recorder` déclaré comme dépendance dans le manifest.
- Retries HTTP limités aux erreurs transitoires (5xx/429) ; pagination API plafonnée.
- `octopus_french.force_update` rafraîchit aussi les données Intelligent.
- Traductions et `services.yaml` nettoyés.

---

## [3.4.0] - 2026-07-22

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A1V11ZZTPI)

### ✨ Conformité HA — Noms d'entités normalisés

Les libellés des capteurs suivent désormais les conventions Home Assistant :

- **Sentence case** : « Jours Été HP » → « Consommation été HP », « Tarif Rouge HP » → « Tarif rouge HP ».
- **Suppression du suffixe non standard `/ mois en cours`** sur tous les capteurs concernés (la période reste disponible via les attributs).
- **énergie / coût** : `energy_peak_hours` et `cost_peak_hours` affichaient le même libellé (« HP / mois en cours ») ; ils deviennent « Consommation HP » et « Coût HP ».
- Abréviation « Conso » remplacée par « Consommation ».
- `en.json` complété (clés `tempo_color_tomorrow` et `tempo_current_rate` manquantes).


### 🔧 Uniformisation des `unique_id` Intelligent

Les entités Octopus Intelligent (véhicule) utilisaient un `unique_id` sans `DOMAIN`. Elles sont désormais préfixées de manière cohérente, avec une **migration automatique du registre** : l'historique et les personnalisations des entités existantes sont conservés.

---

## [3.3.5] - 2026-07-22

### 🐛 Correction — Conflit de dépendance

Rétablissement de `PyJWT==2.10.1`.

### 🐛 Correction — OctoTempo : plantage sur `periodStartAt: null` (issue #57)

Une entrée d'index provisoire renvoyée avec `periodStartAt: null` provoquait `'NoneType' object is not subscriptable` et faisait échouer le fetch initial pour les utilisateurs OctoTempo.

### 🐛 Correction — Comptes multi-Linky : données du mauvais contrat

Un compte à 2+ points de livraison ne récupérait que le premier PRM ; toutes les entités lisaient le même bloc. Les relevés et l'index sont désormais récupérés et stockés **par PRM** (`electricity_by_prm`).

---

## [3.3.4] - 2026-07-14

Corrections des deux problèmes remontés dans l'issue #51 (« Invalid credentials & no attribute 'get' »).

### 🔐 Correction — « Invalid credentials » alors que les identifiants sont bons

À chaque erreur d'autorisation, l'intégration refaisait un **login e-mail/mot de passe complet**. Répétés, ces logins déclenchent le rate-limit dynamique de Kraken (`KT-CT-1199`), qui finit par refuser le login lui-même — l'intégration interprétait alors ce refus comme des identifiants invalides et demandait une ré-authentification, en pure perte.

- Le token d'accès (60 min) est désormais renouvelé via le **refresh token** (7 j), sans renvoyer le mot de passe. Le login complet n'est refait que si le refresh échoue ou expire.
- Le rate-limit est détecté et traité comme une erreur **temporaire** : Home Assistant patiente et réessaie, au lieu d'afficher « Authentication failed - invalid credentials ».

---

## [3.3.3] - 2026-07-09

Cette version est une **mise en conformité aux standards Home Assistant** accompagnée de deux corrections côté utilisateur (comptes multiples et capteur de contrat).

### 🐛 Correction — Comptes multiples : mauvais compte associé / second compte impossible

Lors de l'ajout d'un compte quand le login Octopus en expose plusieurs, l'`unique_id` de l'intégration était toujours figé sur le **premier** compte de la liste, avant même le choix de l'utilisateur. Conséquences : l'entrée créée pour le compte B portait l'identifiant du compte A, et il devenait **impossible d'ajouter un second compte** (abandon « déjà configuré »).

- L'`unique_id` est désormais fixé sur le compte **réellement sélectionné**, au moment de créer l'entrée (`config_flow.py`).

### 🐛 Correction — Capteur « contrat » affichant `EFFACEMENT_HPHC_2`

Sur certaines offres, le capteur de type de contrat affichait l'identifiant brut du calendrier fournisseur (ex. `EFFACEMENT_HPHC_2`) au lieu du type tarifaire normalisé.

- Normalisation vers `BASE` / `HPHC` / `TEMPO` ; l'identifiant brut reste disponible dans l'attribut `agreement` (`utils.py`, `sensors/electricity.py`).

### 🔧 Conformité Home Assistant

- **Reauth** : le flux de ré-authentification se déclenche désormais correctement en cas de token invalide (mapping `ConfigEntryAuthFailed`), au lieu de laisser des capteurs vides.
- **Erreurs de config flow** : identifiants erronés → `invalid_auth`, réseau indisponible → `cannot_connect` (plus de traceback dans les logs).
- **Actions véhicule Intelligent** (SOC cible, heure, boost) : remontée d'erreur propre via `HomeAssistantError` avec messages traduits, au lieu d'échecs silencieux.
- **Capteurs de tarif `€/kWh`** : retrait de la `device_class` monétaire invalide (supprime les avertissements HA sur l'unité).
- **Requêtes GraphQL** : passage par des variables typées plutôt que de l'interpolation de chaînes.
- Ajout du support **diagnostics** (téléchargement des diagnostics de l'entrée, données sensibles expurgées).
- Traductions ajoutées pour les étapes `account` et `reauth_confirm`.
- Journalisation alignée sur les conventions HA (les erreurs attendues ne polluent plus les logs en niveau `error`).

---

## [3.3.2] - 2026-07-03

### 🐛 Correction — Avertissement pour des classes temporelles non standard (issue #48)

Chez certains utilisateurs, l'API Octopus renvoie sur des `electricityReading` des valeurs de `calendarTempClass` non standard (ex. `'P1'` / `'P2'`) qui ne correspondent à **aucune classe tarifaire réelle** (un HP/HC normal renvoie `HP` / `HC`). Le journal se remplissait alors de messages `Code temporalClass inconnu … — mettez à jour _TEMPORAL_CLASS_TO_KEY`.

---

## [3.3.1] - 2026-07-01

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
