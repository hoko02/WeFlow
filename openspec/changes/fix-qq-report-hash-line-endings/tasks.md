## 1. Canonical report representation

- [x] 1.1 Declare LF checkout semantics for the QQ offline acceptance source report and materialize its verified clean bytes accordingly.
- [x] 1.2 Rebind the dependent `stable_report_sha256` to the canonical LF source bytes without changing report semantics or capability claims.

## 2. Regression coverage

- [x] 2.1 Extend the source-backed QQ verification test to require the file-scoped LF attribute while retaining the raw-byte hash check.
- [x] 2.2 Run the focused QQ verification test and confirm the source report bytes match the retained hash under LF semantics.

## 3. Change verification

- [x] 3.1 Run the complete offline pytest suite and repository hygiene/diff checks without network, credentials, or external writes.
- [x] 3.2 Run strict OpenSpec validation for this change and record the completed task state.
