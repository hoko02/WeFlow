# Change 4 policy fixtures

`api-503-policy-approval-delivery.json` is the only checked-in Change 4 fixture. It
contains fixed clock metadata, synthetic tenant/principal roles, the fixture policy
version, a one-delivery budget, the named fixture-local IM resource, and explicit
`network_required=false` / `credentials_required=false` declarations.

It contains no customer message body, candidate text, tool payload, credential,
provider target, real connector configuration, approval token, or delivery result. The
control kernel creates grants, policy decisions, bindings, approval records, and local
delivery facts from durable workflow state; the fixture cannot grant authority itself.