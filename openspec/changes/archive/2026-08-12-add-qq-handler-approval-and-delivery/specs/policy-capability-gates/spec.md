## ADDED Requirements

### Requirement: Stage 2 capabilities SHALL be explicit, least-privilege, and command-scoped

The policy engine SHALL distinguish group reads, C2C reads, one minimal active C2C notification, passive C2C replies, handler approval decisions, and final passive group delivery. A grant for one capability MUST NOT imply another, and no capability SHALL enable a general-purpose C2C or group sender.

#### Scenario: Private read is granted without write

- **WHEN** policy grants `qq.c2c.read` but not a C2C write capability
- **THEN** the event may be classified but no notification or reply is executed

#### Scenario: Active notification scope is granted

- **WHEN** policy grants the exact Case-scoped notification capability
- **THEN** only the minimal Case reference and pull instruction may be attempted once for the bound C2C user

### Requirement: Every privileged action SHALL be gated by identity, state, version, and content policy

Before a notification, passive private reply, approval decision, or final group write, policy SHALL verify the paired tenant/group, active dual-surface binding, author surface, Case/revision, workflow version, content classification, retention state, capability profile, budget, and action-specific expiry.

#### Scenario: Group approval comes from the C2C handler's unlinked group identity

- **WHEN** the `WF-APPROVE` author does not resolve to the same dual-surface binding as the private candidate author
- **THEN** policy denies the decision and no external write is attempted

#### Scenario: Artifact has expired

- **WHEN** the customer issue or candidate artifact is expired or deleted
- **THEN** pull, preview, approval, and delivery fail closed

### Requirement: Notification ambiguity SHALL not authorize retries

Policy SHALL allow no more than one active C2C transport attempt for a notification natural key. An accepted, rejected, timed-out, disconnected, or unknown first attempt SHALL close the active-attempt budget.

#### Scenario: Operator repeats the command after a timeout

- **WHEN** a notification for the same Case and binding already has an ambiguous attempt
- **THEN** policy denies another active attempt and permits only the non-sensitive recovery path

### Requirement: Models and unrelated external writes SHALL remain disabled

No Stage 2 path SHALL invoke a model, QQ mail, attachment upload, business-system integration, arbitrary provider tool, or external write outside the declared QQ capabilities.

#### Scenario: Candidate generation is requested from a model

- **WHEN** any path attempts to invoke a model for drafting, approval, or completion
- **THEN** the capability gate rejects it and records a safe denial reason
