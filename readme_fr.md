# Intégration Octopus Energy France pour Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/domodom30/octopus_french)](https://github.com/domodom30/octopus_french/releases)
[![License](https://img.shields.io/github/license/domodom30/octopus_french)](LICENSE)

Cette intégration personnalisée vous permet de surveiller votre compte Octopus Energy France directement dans Home Assistant. Suivez votre consommation d'électricité et de gaz, vos relevés de compteur, vos coûts et vos heures creuses.

## Fonctionnalités

- **Solde du compte** : Surveillez le solde de votre cagnotte
- **Informations du contrat** : Consultez les détails de votre compte et de vos compteurs
- **Suivi de l'électricité** :
  - Capteurs séparés pour les périodes HC (Heures Creuses) et HP (Heures Pleines)
  - Relevés d'index en temps réel
  - Suivi de la consommation
  - Calcul des coûts basé sur les tarifs actuels
  - Capteur binaire indiquant les périodes creuses actives
- **Suivi du gaz** :
  - Relevés d'index
  - Suivi de la consommation en m³
  - Calcul des coûts avec conversion automatique en kWh
- **Mises à jour automatiques** : Données actualisées toutes les 30 minutes
- **Planning HC** : Planning détaillé des heures creuses avec plages horaires et durées

## Installation

### HACS (Recommandé)

1. Ouvrez HACS dans Home Assistant
2. Allez dans "Intégrations"
3. Cliquez sur les trois points en haut à droite
4. Sélectionnez "Dépôts personnalisés"
5. Ajoutez l'URL de ce dépôt : `https://github.com/domodom30/octopus_french`
6. Sélectionnez la catégorie : "Intégration"
7. Cliquez sur "Ajouter"
8. Recherchez "Octopus Energy France"
9. Cliquez sur "Télécharger"
10. Redémarrez Home Assistant

### Installation manuelle

1. Téléchargez le dossier `custom_components/octopus_french` depuis ce dépôt
2. Copiez-le dans votre répertoire `custom_components` de votre configuration Home Assistant
3. Redémarrez Home Assistant

## Configuration

1. Allez dans Paramètres → Appareils et services
2. Cliquez sur "+ Ajouter une intégration"
3. Recherchez "Octopus Energy France"
4. Entrez vos identifiants Octopus Energy France :
   - Email
   - Mot de passe
5. Si vous avez plusieurs comptes, sélectionnez le compte que vous souhaitez surveiller
6. Cliquez sur "Soumettre"

## Capteurs

### Capteur Solde
- **Nom** : Cagnotte
- **Unité** : EUR (€)
- **Description** : Le solde de votre compte/cagnotte
- **Attributs** : Type de registre, nom et numéro

### Capteur Contrat
- **Nom** : Contrat
- **Description** : Informations sur le contrat et les compteurs
- **Attributs** :
  - Numéro de compte
  - Détails du compteur électrique (PRM ID, puissance max, label HC, statut téléopération)
  - Détails du compteur gaz (référence PCE, consommation annuelle, statut compteur intelligent)

### Capteurs Électricité

#### Capteurs d'Index
- **Index Électricité HC** : Relevé du compteur électrique heures creuses (kWh)
- **Index Électricité HP** : Relevé du compteur électrique heures pleines (kWh)

#### Capteurs de Consommation
- **Électricité HC** : Consommation électrique heures creuses (kWh)
- **Électricité HP** : Consommation électrique heures pleines (kWh)

#### Capteurs de Coût
- **Coût Électricité HC** : Coût de l'électricité heures creuses (€)
- **Coût Électricité HP** : Coût de l'électricité heures pleines (€)

**Attributs** : PRM ID, dates de période, consommation, prix au kWh, statut

### Capteurs Gaz

#### Capteur d'Index
- **Index Gaz** : Relevé du compteur de gaz (m³)

#### Capteur de Consommation
- **Gaz** : Consommation de gaz (m³)

#### Capteur de Coût
- **Coût Gaz** : Coût du gaz (€)

**Attributs** : Référence PCE, dates de période, consommation en m³ et kWh, prix au kWh

### Capteur Binaire

#### Heures Creuses Actives
- **État** : ON pendant les heures creuses, OFF le reste du temps
- **Icône** : Horloge avec coche quand actif, horloge vide sinon
- **Attributs** :
  - `hc_schedule_available` : Booléen indiquant si un planning HC est configuré
  - `total_hc_hours` : Nombre total d'heures creuses par jour
  - `hc_type` : Type de planning heures creuses
  - `hc_range_X` : Plages horaires individuelles (ex: "22:00 - 06:00")

## Exemples d'Automatisations

### Allumer le chauffe-eau pendant les heures creuses

```yaml
automation:
  - alias: "Chauffe-eau - Heures Creuses"
    trigger:
      - platform: state
        entity_id: binary_sensor.heures_creuses_actives
        to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.chauffe_eau
```

### Éteindre le chauffe-eau pendant les heures pleines

```yaml
automation:
  - alias: "Chauffe-eau - Heures Pleines"
    trigger:
      - platform: state
        entity_id: binary_sensor.heures_creuses_actives
        to: "off"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.chauffe_eau
```

### Notification quand le solde est faible

```yaml
automation:
  - alias: "Alerte Solde Faible"
    trigger:
      - platform: numeric_state
        entity_id: sensor.cagnotte
        below: 10
    action:
      - service: notify.mobile_app
        data:
          title: "Octopus Energy"
          message: "Votre solde est faible : {{ states('sensor.cagnotte') }}€"
```

### Rapport quotidien de consommation énergétique

```yaml
automation:
  - alias: "Rapport Quotidien Énergie"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Rapport Quotidien Énergie"
          message: >
            HC: {{ states('sensor.electricite_hc') }} kWh ({{ states('sensor.cout_electricite_hc') }}€)
            HP: {{ states('sensor.electricite_hp') }} kWh ({{ states('sensor.cout_electricite_hp') }}€)
            Gaz: {{ states('sensor.gaz') }} m³ ({{ states('sensor.cout_gaz') }}€)
```

## Exemple de Carte Lovelace

```yaml
type: entities
title: Octopus Energy France
entities:
  - entity: sensor.cagnotte
  - entity: binary_sensor.heures_creuses_actives
  - entity: sensor.electricite_hc
  - entity: sensor.electricite_hp
  - entity: sensor.cout_electricite_hc
  - entity: sensor.cout_electricite_hp
  - entity: sensor.gaz
  - entity: sensor.cout_gaz
```

## Intégration au Tableau de Bord Énergie

Cette intégration est compatible avec le Tableau de Bord Énergie de Home Assistant :

1. Allez dans Paramètres → Tableaux de bord → Énergie
2. Cliquez sur "Ajouter une consommation" sous Consommation du réseau électrique
3. Sélectionnez :
   - `sensor.electricite_hc` pour la consommation heures creuses
   - `sensor.electricite_hp` pour la consommation heures pleines
4. Pour la consommation de gaz, sélectionnez `sensor.gaz`

## Dépannage

### Les capteurs n'apparaissent pas
- Vérifiez que votre compte a des contrats électricité et/ou gaz actifs
- Vérifiez que vos identifiants sont corrects
- Consultez les journaux Home Assistant : Paramètres → Système → Journaux

### Les données ne se mettent pas à jour
- L'intégration se met à jour toutes les 30 minutes par défaut
- Vous pouvez forcer une mise à jour en cliquant sur "Recharger" dans les paramètres de l'intégration
- Vérifiez votre connexion internet

### Erreurs d'authentification
- Vérifiez que votre email et mot de passe sont corrects
- Essayez de vous connecter au site web Octopus Energy France avec les mêmes identifiants
- Si vous avez récemment changé votre mot de passe, reconfigurez l'intégration

### Le capteur binaire ne fonctionne pas
- Assurez-vous que votre contrat électrique a un planning heures creuses configuré
- Vérifiez l'attribut `hc_schedule_available`
- Vérifiez que les heures creuses dans les attributs du capteur correspondent à votre contrat

## Journalisation de Débogage

Pour activer les journaux de débogage :

```yaml
logger:
  default: info
  logs:
    custom_components.octopus_french: debug
```

## Limitation du Débit API

L'intégration respecte les limites de l'API Octopus Energy :
- Rafraîchissement automatique du token avant expiration
- Logique de réessai avec backoff exponentiel
- Intervalle de mise à jour de 30 minutes

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à soumettre une Pull Request.

## Support

Si vous rencontrez des problèmes ou avez des questions :
- Consultez la page [Issues](https://github.com/domodom30/octopus_french/issues)
- Créez un nouveau ticket avec des informations détaillées et les journaux

## Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.

## Avertissement

Cette intégration n'est pas officiellement affiliée ou approuvée par Octopus Energy France. À utiliser à vos propres risques.
