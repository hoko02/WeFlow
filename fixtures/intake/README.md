# Synthetic IM intake fixtures

These fixtures contain only opaque synthetic identifiers, fixed timestamps, and
content hashes. They deliberately omit message text, attachment bytes, credentials,
and customer records.

- `api-503-first-delivery` creates one Case, CaseRevision 1, and three events.
- `api-503-duplicate-delivery` repeats the same delivery with a different receipt
  timestamp and must be read-only.
- `api-503-out-of-order` contains a sequence gap and must be rejected without state
  mutation.
