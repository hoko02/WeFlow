## ADDED Requirements

### Requirement: QQ sandbox boundary contracts are versioned and payload-safe
WeFlow SHALL maintain compatible language-neutral schemas for QQSandboxInboundEvent,
QQGatewayCursor, QQAcknowledgementIntent, QQAcknowledgementObservation, and
QQAcknowledgementCompletion. Each contract SHALL declare stable schema identity and
version, bind its effective tenant and safe QQ application/group/source identities,
forbid undeclared properties, and contain only allowlisted opaque identifiers, hashes,
sequence/timestamp metadata, classification, correlation, status, and reason codes.
The contracts MUST reject raw message text, group transcripts, attachment bytes,
display names, credentials, access tokens, unrestricted provider bodies,
caller-selected authority/destination/content, customer-receipt claims, resolution
claims, and Case-completion claims.

#### Scenario: Valid QQ boundary fixtures validate cross-language
- **WHEN** valid inbound, gateway-cursor, acknowledgement intent, observation, and
  completion fixtures are consumed by Python and TypeScript validators
- **THEN** both packages SHALL accept the same schema identities and versions without
  requiring a QQ credential, raw chat payload, or network request

#### Scenario: A QQ boundary fixture contains unsafe data or authority
- **WHEN** a fixture contains raw text, transcript data, an undeclared credential,
  caller-selected tenant/group/content, foreign Case reference, invalid sequence/hash,
  or customer-success assertion
- **THEN** both validators SHALL reject it before intake or execution

### Requirement: QQ contract evolution preserves all retained v1 fixtures
QQ sandbox contracts SHALL be additive to the existing synthetic inbound, workflow,
delivery, evidence, benchmark, operator, and live-model contracts. The compatibility
command SHALL validate valid/invalid QQ fixtures in both languages alongside every
retained v1 fixture and SHALL reject any silent semantic change to an existing schema.

#### Scenario: The QQ corpus is added to compatibility checks
- **WHEN** cross-language compatibility runs after the QQ schemas and fixtures are
  introduced
- **THEN** all retained valid fixtures SHALL remain valid, retained invalid fixtures
  SHALL remain invalid, and the new QQ corpus SHALL agree across languages

#### Scenario: A QQ edit breaks a retained contract
- **WHEN** a QQ-related schema change invalidates a retained compatible fixture or
  weakens an existing safety rejection
- **THEN** compatibility SHALL fail until the change becomes additive or uses a new
  major-version contract path
