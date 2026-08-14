## MODIFIED Requirements

### Requirement: QQ acceptance evidence is truthful and independently verifiable
The repository SHALL provide an offline fake-transport acceptance path and a separate
operator-run QQ sandbox acceptance path. Reports SHALL distinguish fake verification
from real sandbox verification, SHALL keep `customer_receipt_verified=false`, and SHALL
contain only safe IDs, hashes, counts, status/reason codes, timings, and explicit
capability flags. The retained offline acceptance report used as the source of its
change-verification SHA-256 SHALL be tracked with LF-canonical bytes, and the stored
hash SHALL bind those exact canonical bytes regardless of a contributor's default
checkout line-ending setting. This change SHALL NOT initialize a model, handler
approval, business tool, final delivery path, or Case/customer resolution transition.

#### Scenario: Offline CI exercises the QQ slice
- **WHEN** tests inject token, gateway, WebSocket, and send fakes with duplicate,
  reconnect, timeout, lost-response, restart, cross-tenant, unsafe-content, and denial
  cases
- **THEN** the acceptance report SHALL be reproducible without network or credentials,
  set fake verification truthfully, and leave real live verification false

#### Scenario: An operator completes a real sandbox run
- **WHEN** one allowlisted real QQ mention creates a Case and the fixed acknowledgement
  has a validated accepted/present provider result
- **THEN** the report MAY set `qq_sandbox_live_verified=true` while customer receipt,
  issue resolution, final delivery, model use, and production readiness remain false

#### Scenario: A retained offline report is verified from a Linux or Windows checkout
- **WHEN** the QQ change-verification test reads the retained offline acceptance report
  and its stored `stable_report_sha256`
- **THEN** the report SHALL use the declared LF-canonical bytes and the test SHALL
  observe the same SHA-256 on each supported checkout platform without changing any
  fake/live, customer, or production capability flag
