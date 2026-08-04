## MODIFIED Requirements

### Requirement: No runtime component can authorize or complete a side effect
The Agent Runtime and Business Simulator SHALL NOT register a live/external-write
executor or treat replay content or a model-like response as a Capability Grant, Policy
Decision, approval, verifier result, delivery completion, or Case-completion
declaration. Only the deterministic control kernel may evaluate the named fixture-owned
Capability/Policy rules, persist a hash-bound approval, and invoke the named
fixture-local delivery adapter after all gates pass. That bounded local adapter SHALL
not initialize a network client, credential, real enterprise connector, or
customer-success behavior.

#### Scenario: A replay fixture requests an external action
- **WHEN** a synthetic replay fixture contains a proposed ticket, reply, or other
  external action
- **THEN** the runtime SHALL record it only as replay data or reject it by policy,
  SHALL NOT execute an external call, and SHALL NOT emit a successful completion result

#### Scenario: A self-approval-like input is supplied
- **WHEN** replay input presents a proposed action together with a purported approval
  or success assertion not bound to a valid current ApprovalDecision and policy/
  Capability authorization profile
- **THEN** the runtime SHALL reject it as unauthorized or stale and SHALL NOT grant
  permission, approve the action, or declare success

#### Scenario: The named control path reaches fixture-local delivery
- **WHEN** the deterministic control kernel has a current valid policy, Capability,
  approval, and authorization binding for the named fixture
- **THEN** it MAY record the fixture-local delivery chain while the Agent Runtime and
  Business Simulator do not grant authority or contact an external provider
