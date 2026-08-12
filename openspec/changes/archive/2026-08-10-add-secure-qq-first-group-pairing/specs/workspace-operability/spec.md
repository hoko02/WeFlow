## ADDED Requirements

### Requirement: QQ pairing commands are isolated and reproducible
The repository SHALL expose dedicated cross-platform development commands for offline
pairing acceptance, pairing-report verification, explicitly confirmed live pairing,
and bounded local revoke/expiry handling. Offline pairing checks SHALL require no
network, QQ/model/enterprise credential, Docker, or external write. Ordinary startup,
health, tests, Replay, benchmarks, investigation, live-model evaluation, and retained
acceptance commands SHALL reject visible pairing configuration or activation before
their handlers run and SHALL not import the real pairing adapter.

#### Scenario: CI runs pairing acceptance offline
- **WHEN** the normal test/contract/security command surface executes without QQ
  configuration
- **THEN** deterministic fakes and pairing report verification SHALL pass without
  network or credentials while real pairing remains unverified

#### Scenario: An ordinary command sees pairing configuration
- **WHEN** a non-pairing command observes pairing credentials, confirmation, pairing
  capability, challenge, or pairing selector configuration
- **THEN** it SHALL fail before command work, provider contact, or runtime registration
  and SHALL output only a redacted stable reason

#### Scenario: The live pairing command is run without confirmation
- **WHEN** an operator invokes live pairing without the exact confirmation flag or with
  missing/expanded configuration
- **THEN** it SHALL fail before HTTP/WebSocket client construction and SHALL not create
  a challenge or pairing record
