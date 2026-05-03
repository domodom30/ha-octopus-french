## [3.0.2] - 2026-05-03

- Fix: GraphQL query date to retrieve dynamic tariffs instead of a static 2026 date.
- Implement local calculation for monthly costs based on real consumption and active tariffs (fixing 0€ values).
- Add 'subscribed_power' sensor (kVA) with Apparent Power device class.
- Adjust state classes for energy sensors (total_increasing) and monetary sensors (total) to fix Energy Dashboard compatibility and log errors.
- Add 'pyjwt' requirement in manifest.json for Kraken API authentication.
- Fix: long-term statistics for the 'pot_ledger' (cagnotte) sensor.

## [3.0.1] - 2026-02-23

### 🐛 Bug Fixes
- Fix: state_class": SensorStateClass.TOTAL_INCREASING

---
