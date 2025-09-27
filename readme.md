# Intégration Octopus Energy French pour Home Assistant

Cette intégration permet de récupérer les données de votre compte Octopus Energy France dans Home Assistant, incluant les soldes de vos compteurs, la consommation électrique et gaz par mois, ainsi que le solde de votre cagnotte.

## Fonctionnalités

- **Sensors de solde** : Affiche la consommation de vos compteurs électrique et gaz / mois
- **Sensor de cagnotte** : Montre le solde de votre cagnotte Octopus
- **Détails de consommation** : Ventilation mensuelle HP/HC pour l'électricité
- **Multi-comptes** : Support de plusieurs comptes Octopus

## Installation

### Via HACS (recommandé)

1. Ajoutez ce dépôt comme dépôt personnalisé dans HACS
2. Recherchez "Octopus Energy French" dans HACS
3. Installez l'intégration
4. Redémarrez Home Assistant


[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domodom30&repository=ha-octopus-french&category=integration)

### Manuellement

1. Copiez le dossier `octopus_french` dans votre dossier `custom_components`
2. Redémarrez Home Assistant
3. Ajoutez l'intégration via l'interface Configuration → Intégrations

## Configuration

1. Allez dans Configuration → Intégrations
2. Cliquez sur "+ Ajouter une intégration"
3. Recherchez "Octopus Energy French"
4. Entrez vos identifiants Octopus Energy :
   - Email
   - Mot de passe
5. Sélectionnez le numéro de compte à suivre
6. Configurez les options (intervalle de mise à jour, etc.)

## Capteurs disponibles

### Octopus Energy Cagnotte
- **Type** : Monétaire (€)
- **Attributs** : 
  - Solde brut (centimes)
  - Solde en euros
  - Numéro de compte

### Electricity Energy
- **Type** : Énergie (kWh)
- **Attributs** :
  - Consommation totale
  - Ventilation mensuelle HP/HC
  - Dernière mise à jour
  - Identifiant du point de mesure

### Gas Energy  
- **Type** : Énergie (kWh)
- **Attributs** :
  - Consommation totale mensuelle
  - Dernière mise à jour
  - Dates des premières/dernières lectures
  - Identifiant du point de mesure

## Options de configuration

- **Intervalle de mise à jour** : 1 à 24 heures (par défaut : 4h)

## Dépannage

### Problèmes d'authentification
- Vérifiez vos identifiants Octopus Energy
- Assurez-vous que votre compte est actif

### Données manquantes
- Les compteurs sans consommation peuvent ne pas apparaître

### Dashboard

![graph.png](imgs/graph.png) ![dashboard.png](imgs/dashboard.png)

### Logs
Les logs détaillés sont disponibles dans les logs Home Assistant avec le filtre :
```yaml
logger:
  logs:
    custom_components.octopus_energy_french: debug
