## ADDED Requirements

### Requirement: QQ group-pairing contracts are versioned and payload-safe
WeFlow SHALL maintain compatible language-neutral schemas for
`QQGroupPairingChallenge`, `QQGroupPairingCompletion`, and
`QQGroupPairingAcceptanceReport`. Each SHALL declare a stable schema identity/version,
forbid undeclared properties, bind safe pairing/application/group/tenant identities and
lifecycle timestamps where applicable, and contain only allowlisted opaque IDs, hashes,
enumerations, counts, status/reason codes, and explicit capability flags. They MUST
reject challenge plaintext, raw group/member/message identifiers, ordinary QQ group
numbers, credentials, access tokens, raw events/provider bodies, transcripts,
caller-selected authority, QQ-write claims, Case/workflow effects, customer receipt,
resolution, and Case-completion claims.

#### Scenario: Valid pairing fixtures validate cross-language
- **WHEN** Python and TypeScript consume a complete safe challenge, completion, and
  offline/live report fixture chain
- **THEN** both packages SHALL accept the same identities, hashes, links, lifecycle,
  and capability flags without needing a QQ credential, raw locator, or network call

#### Scenario: A pairing fixture contains private data or false authority
- **WHEN** a pairing fixture contains challenge text, raw OpenID/message/event data,
  credentials, caller-selected group/tenant, a detached/foreign reference, invalid
  expiry/hash/status, QQ send, Case creation, or customer-success assertion
- **THEN** both validators SHALL reject it before pairing or report publication

### Requirement: Pairing contract evolution preserves every retained v1 result
The compatibility command SHALL validate the pairing corpus in Python and TypeScript
alongside every retained valid and invalid v1 fixture. Pairing schemas SHALL be additive
and SHALL not broaden existing QQ intake, provider, workflow, approval, delivery,
evidence, benchmark, or operator contracts. An incompatible semantic change MUST use a
new major-version contract path.

#### Scenario: The pairing corpus is added to compatibility checks
- **WHEN** cross-language compatibility runs after pairing contracts and semantic
  fixtures are introduced
- **THEN** all retained fixtures SHALL preserve their prior result and both languages
  SHALL agree on every new pairing valid/invalid result
