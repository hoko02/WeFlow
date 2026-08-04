## ADDED Requirements

### Requirement: Offline authorization and fixture delivery are self-contained and deterministic
Offline mode SHALL execute the named fixture-owned Capability/Policy evaluator,
approval recorder/API, fixture-local IM delivery adapter, and all authorization/
delivery recovery boundaries from local SQLite, fixed clocks, and checked-in fixtures.
It SHALL require neither Docker, network access, model credentials, enterprise
credentials, nor a live approval/delivery service. Two equal offline baselines SHALL
produce equal authorization, approval, delivery, and safe-report facts.

#### Scenario: The full authorized fixture path runs with Docker unavailable
- **WHEN** a contributor runs the named API-503 policy/approval/delivery acceptance
  fixture with Docker unavailable and network blocked
- **THEN** it SHALL produce the declared deterministic local authorization and at most
  one fixture delivery without initializing a live dependency

#### Scenario: An authorization or delivery recovery boundary is interrupted
- **WHEN** a worker stops after policy, approval request, approval decision, delivery
  intent, execution, observation, completion, or delivery transition persistence
- **THEN** a fresh worker SHALL rebuild the same safe projection without a duplicate
  fixture delivery or external call
