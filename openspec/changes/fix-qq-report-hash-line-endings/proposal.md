## Why

GitHub Actions on Linux fails the retained QQ change-verification test because the
source report is hashed as raw bytes while Windows contributors check it out with
CRLF line endings. The same committed JSON therefore has a different SHA-256 in CI
than in the Windows verification record, making the offline CI result non-reproducible.

## What Changes

- Define the QQ offline acceptance report used by the retained verification as an
  LF-canonical tracked file.
- Rebind its stored `stable_report_sha256` to the canonical LF bytes and retain the
  existing source-backed verification assertion.
- Add a focused regression check for the required Git line-ending attribute, then
  verify the complete offline test path under canonical LF semantics.

## Non-Goals

- Do not change QQ intake, acknowledgement, model, approval, delivery, or any live
  provider behavior.
- Do not regenerate or alter the semantic acceptance evidence, enable an external
  write, or change customer-receipt, resolution, completion, or production claims.
- Do not normalize unrelated reports in this maintenance increment.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `workspace-operability`: baseline CI preserves and verifies the same retained
  content-addressed report bytes across supported checkout platforms.
- `qq-sandbox-intake-and-ack`: the offline acceptance verification binds to the
  canonical portable report representation rather than a workstation-specific
  line-ending variant.

## Impact

- Affected repository metadata: `.gitattributes`.
- Affected retained evidence: the QQ offline acceptance verification record only.
- Affected test: `tests/security/test_qq_change_verification.py`.
- The change remains offline, deterministic, credential-free, and has no API or
  runtime behavior impact.
