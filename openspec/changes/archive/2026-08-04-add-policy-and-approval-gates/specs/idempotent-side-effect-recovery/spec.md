## ADDED Requirements

### Requirement: Fixture-local outbound delivery has a distinct immutable recovery chain
Before a named fixture-local IM delivery is attempted, the control kernel SHALL persist
one tenant-scoped immutable OutboundDeliveryIntent containing Case, CaseRevision,
workflow/checkpoint, channel/conversation resource, candidate hash, authorization
binding hash, operation, natural key, stable idempotency key, safe evidence references,
and correlation metadata. It SHALL reconcile, execute, observe, and complete only that
same intent through distinct append-only delivery facts. Ticket `SideEffect*` records
and their natural keys SHALL remain unchanged.

#### Scenario: A worker stops immediately after delivery intent persistence
- **WHEN** fault injection stops a worker after an authorized delivery intent commits
  but before reconciliation or execution
- **THEN** recovery SHALL find the same intent by stable identity, reconcile before
  executing, and SHALL not create a second intent or delivery

#### Scenario: Delivery confirmation is lost after execution
- **WHEN** the fixture-local adapter has executed one natural-key operation but its
  response is lost
- **THEN** recovery SHALL observe/reconcile the existing local outcome and SHALL not
  execute a second delivery

#### Scenario: Delivery is unauthorized during recovery
- **WHEN** a recovered intent no longer has a current matching policy, Capability
  Grant, approval, candidate, evidence, or authorization binding
- **THEN** recovery SHALL append no execution or completion and SHALL preserve the
  existing immutable facts for safe handling
