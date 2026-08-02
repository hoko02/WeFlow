# Change 2 workflow fixtures

These fixtures compose a checked-in synthetic intake envelope with an allowlisted
fixture SLA and, optionally, one deterministic fault point. They contain no raw
customer content, provider configuration, credentials, approval decision, outbound
delivery target, or real connector request.

Each fixture names an `advance_clock_seconds` value. It is applied only after an
injected interruption and only to the simulator's injected fixture clock, allowing the
SLA-expiry case to recover deterministically without host wall-clock time. A fault
fixture is restarted over the same SQLite source store before its `expected_state` is
checked.
