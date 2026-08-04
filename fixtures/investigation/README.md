# Investigation fixtures

These fixtures are the deterministic, offline Change 3 corpus. The replay transcript
contains only action names, limits, and fixed hashes. The CRM, monitoring, and knowledge
fixture contains synthetic resource keys and redacted hashes only. It intentionally does
not contain customer message text, tool payload bodies, credentials, or network targets.

`api-503-investigation` is the single bounded happy-path transcript. It reads CRM,
monitoring, and knowledge exactly once, then proposes an internal response candidate.
The deterministic verifier—not the transcript—decides whether the workflow may enter
`RESPONSE_READY`.
