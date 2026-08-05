import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  loadOperatorCaseSurface,
  renderOperatorCaseSurface,
  validateOperatorCaseSnapshot,
  validateOperatorCaseSnapshotShape,
} from "../check-dist/operator-case.js";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const fixture = JSON.parse(
  readFileSync(
    resolve(packageRoot, "../../fixtures/contracts/v1/semantic/operator-case-snapshot.json"),
    "utf8",
  ),
);

assert.ok(validateOperatorCaseSnapshotShape(fixture));
const validated = await validateOperatorCaseSnapshot(fixture);
assert.ok(validated);
const selected = fixture.timeline.find((entry) => entry.source_kind === "approval_decision");
const ready = renderOperatorCaseSurface(
  { status: "ready", snapshot: validated },
  selected.entry_id,
);
assert.equal(ready.status, "ready");
assert.equal(ready.timeline.length, 49);
assert.equal(ready.currentStateLabel, "DELIVERY_RECORDED (fixture-local)");
assert.equal(ready.selectedEntry.sourceKind, "approval_decision");
assert.equal(ready.selectedEntry.observation, "approved");
assert.equal(ready.selectedEntry.gateLabel, "passed");
assert.ok(ready.timeline.some((entry) => entry.phase === "intake"));
assert.ok(ready.timeline.some((entry) => entry.phase === "replay"));
assert.deepEqual(ready.capabilityLabels, [
  "offline synthetic fixture",
  "Replay verification only",
  "fixture-local delivery record",
  "no network or model",
  "no external-write or workflow authority",
]);
assert.ok(ready.limitations.every((item) => item.startsWith("No ")));

for (const mutation of [
  (snapshot) => { snapshot.raw_payload = "<script>blocked</script>"; },
  (snapshot) => { snapshot.timeline[0].raw_payload = "blocked"; },
  (snapshot) => { snapshot.timeline.pop(); },
  (snapshot) => { snapshot.snapshot_sha256 = "f".repeat(64); },
  (snapshot) => { snapshot.fixture_source_path = "C:/private/fixture.json"; },
  (snapshot) => {
    const entry = snapshot.timeline.find((item) => item.source_kind === "verifier_outcome");
    entry.gate_status = "failed";
    entry.result = "blocked";
  },
  (snapshot) => {
    const entry = snapshot.timeline.find((item) => item.source_kind === "policy_decision");
    entry.observation = "denied";
    entry.reason_code = "policy_denied";
  },
  (snapshot) => {
    const entry = snapshot.timeline.find((item) => item.source_kind === "approval_decision");
    entry.observation = "stale";
    entry.reason_code = "stale_approval";
  },
  (snapshot) => {
    const entry = snapshot.timeline.find((item) => item.source_kind === "delivery_completion");
    entry.observation = "timeout";
    entry.recovery_status = "blocked";
    entry.reason_code = "timeout_without_duplicate_completion";
  },
  (snapshot) => {
    const entry = snapshot.timeline.find((item) => item.source_kind === "delivery_completion");
    entry.observation = "recovered";
    entry.recovery_status = "recovered";
    entry.reason_code = "recovered_after_interruption";
  },
]) {
  const invalid = structuredClone(fixture);
  mutation(invalid);
  assert.equal(await validateOperatorCaseSnapshot(invalid), null);
}

for (const status of [
  "loading",
  "not-found",
  "identity-denied",
  "integrity-not-ready",
]) {
  const rendered = renderOperatorCaseSurface({ status });
  assert.equal(rendered.status, status);
  assert.ok(!JSON.stringify(rendered).includes("blocked"));
  assert.ok(!JSON.stringify(rendered).includes("<script>"));
}

const calls = [];
const loaded = await loadOperatorCaseSurface(async (input, init) => {
  calls.push({ input, init });
  return { ok: true, status: 200, json: async () => fixture };
});
assert.equal(loaded.status, "ready");
assert.deepEqual(calls, [
  {
    input: "http://127.0.0.1:8000/v1/operator/cases/api-503.v1",
    init: {
      method: "GET",
      headers: { "X-WeFlow-Synthetic-Actor": "simulator-tenant-a" },
    },
  },
]);
for (const [status, expected] of [
  [403, "identity-denied"],
  [404, "not-found"],
  [503, "integrity-not-ready"],
]) {
  const state = await loadOperatorCaseSurface(async () => ({
    ok: false,
    status,
    json: async () => ({ raw_payload: "<script>blocked</script>" }),
  }));
  assert.equal(state.status, expected);
  assert.ok(!JSON.stringify(state).includes("blocked"));
}
const invalidState = await loadOperatorCaseSurface(async () => ({
  ok: true,
  status: 200,
  json: async () => ({ ...fixture, raw_payload: "blocked" }),
}));
assert.equal(invalidState.status, "integrity-not-ready");

const rendered = JSON.stringify(ready);
for (const forbidden of [
  "<script>",
  "raw_payload",
  "customer delivered",
  "customer resolved",
  "case completed",
  "approval control",
  "replay control",
]) {
  assert.ok(!rendered.toLowerCase().includes(forbidden));
}

console.log(JSON.stringify({
  report_type: "weflow-console-operator-case-check.v1",
  timeline_entries_rendered: ready.timeline.length,
  selected_entry_checked: true,
  safe_surface_states_checked: 5,
  hard_gate_precedence_checked: true,
  unrestricted_json_rendered: false,
  live_or_customer_success_claims_rendered: false,
}));
