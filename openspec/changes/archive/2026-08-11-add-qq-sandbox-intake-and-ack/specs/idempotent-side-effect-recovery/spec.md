## ADDED Requirements

### Requirement: QQ sandbox acknowledgement has a distinct immutable recovery chain
Before the bounded QQ executor is contacted, the control kernel SHALL persist one
tenant-scoped immutable QQAcknowledgementIntent containing the Case, CaseRevision,
source QQ message reference, configured group resource, fixed template hash, passive
reply deadline, operation, natural key, stable idempotency key, original provider
`msg_id`, deterministic positive reply `msg_seq`, safe evidence references, and
correlation metadata. It SHALL reconcile, execute, observe, and complete only that same
intent through distinct append-only QQ acknowledgement facts. Ticket SideEffect and
approved final OutboundDelivery records and their natural keys SHALL remain unchanged.

#### Scenario: A worker stops immediately after acknowledgement intent persistence
- **WHEN** fault injection stops the worker after the QQ intent commits but before
  reconciliation or execution
- **THEN** recovery SHALL find the same intent, deadline, and provider deduplication
  tuple and SHALL not create a second intent or reply identity

#### Scenario: Concurrent runners encounter the same acknowledgement
- **WHEN** two workers race on the same tenant, Case revision, fixed template, and QQ
  source message
- **THEN** durable uniqueness/claim rules SHALL yield one logical intent and at most one
  provider-deduplicated acknowledgement outcome

### Requirement: QQ acknowledgement reconciliation is mandatory and truthful
The QQ recovery boundary SHALL reconcile local durable facts before every execution and
after interruption, timeout, disconnect, restart, lost response, duplicate response,
or conflict. It SHALL execute/retry only with the original `msg_id` and deterministic
`msg_seq`, only while the deadline and exact command capability remain valid. A
validated accepted or duplicate/present provider observation MAY append one immutable
completion. Unknown, unreadable, conflicting, unauthorized, or expired outcomes SHALL
append safe recovery evidence and remain incomplete; they MUST NOT generate a new
reply sequence, arbitrary resend, customer-receipt claim, final-delivery completion,
or Case/customer completion.

#### Scenario: Execution succeeds but its response is lost
- **WHEN** fault injection records that the fake provider accepted the original
  deduplication tuple but drops the response before observation/completion persistence
- **THEN** recovery SHALL reuse the same tuple, reconcile a present/duplicate result,
  and append at most one completion without a second logical send

#### Scenario: Reconciliation times out without proof
- **WHEN** neither local evidence nor the bounded provider response proves accepted,
  duplicate/present, absent-and-retryable, or conflicting state
- **THEN** recovery SHALL record an unknown safe reason, enter
  `NEEDS_RECONCILIATION`, and SHALL not blindly send or mark the acknowledgement
  complete

#### Scenario: Recovery observes an expired or unauthorized intent
- **WHEN** the passive reply deadline has elapsed or the exact QQ command capability,
  tenant/group mapping, template hash, or source binding no longer matches
- **THEN** recovery SHALL make no provider call, append no completion, and preserve the
  immutable intent for safe inspection
