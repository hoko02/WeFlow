# fixture-outbound-delivery Specification

## Purpose
Define the named fixture-local outbound-delivery adapter, its durable evidence chain, and its non-success boundary.

## Requirements

### Requirement: Only the named fixture-local IM adapter can record outbound delivery
The outbound adapter SHALL support only the named synthetic API-503 fixture-local IM
resource. It SHALL have no network client, enterprise credential, real connector, or
customer-completion behavior. It SHALL accept a delivery only from the control kernel
after a current hash-bound approval and policy authorization; the Agent, API caller,
replay fixture, and approval record alone SHALL not execute it.

#### Scenario: A fully authorized fixture delivery is executed
- **WHEN** the control kernel reaches a current `DELIVERING` checkpoint with all gates
  valid
- **THEN** the fixture adapter SHALL record one safe local delivery outcome containing
  only stable IDs, version, redaction classification, and content hash

#### Scenario: A live or unapproved delivery adapter is requested
- **WHEN** configuration, an Agent, or a request selects a live provider, credential,
  external destination, or unapproved delivery
- **THEN** the runtime SHALL deny before contact and append no delivery effect

### Requirement: Fixture delivery has its own durable idempotency and reconciliation chain
The control kernel SHALL persist distinct append-only `OutboundDeliveryIntent`,
`OutboundDeliveryObservation`, and `OutboundDeliveryCompletion` facts. The intent
SHALL precede reconciliation/execution and bind tenant, channel/conversation, Case,
revision, workflow/checkpoint, candidate hash, authorization-binding hash, natural key,
stable idempotency key, and safe evidence references. Unknown or conflicting
observations SHALL enter reconciliation and SHALL never permit blind resend.

#### Scenario: A response is lost after fixture execution
- **WHEN** a deterministic fault drops the adapter response after its local natural-key
  operation took effect
- **THEN** a fresh worker SHALL reconcile the same natural key, persist one recovered
  outcome, and SHALL not execute a second delivery

#### Scenario: Duplicate workers process one delivery
- **WHEN** repeated or concurrent recovery attempts process the same authorized delivery
- **THEN** they SHALL converge on one intent and at most one fixture adapter execution

### Requirement: Delivery recording is not a customer-success assertion
The control kernel SHALL allow only a completed, reconciled fixture delivery chain to
advance `DELIVERING` to `DELIVERY_RECORDED`. `DELIVERY_RECORDED` SHALL mean only that the local adapter recorded
the synthetic delivery; it SHALL NOT mean customer receipt, resolution, completion,
knowledge publication, or permission for another effect.

#### Scenario: A delivery-complete fixture is reported
- **WHEN** a completed fixture delivery is inspected or exported
- **THEN** the report SHALL distinguish local delivery recording from customer outcome
  and SHALL omit raw message content
