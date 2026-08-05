import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  loadEvaluationSurface,
  renderEvaluationSurface,
  validateEvaluationSnapshot,
} from "../check-dist/evaluation-report.js";

const packageRoot = fileURLToPath(new URL("../", import.meta.url));
const fixture = JSON.parse(
  readFileSync(
    resolve(packageRoot, "../../fixtures/contracts/v1/semantic/evaluation-suite-snapshot.json"),
    "utf8",
  ),
);
const tasks = Array.from({ length: 12 }, (_value, index) => {
  const number = String(index + 1).padStart(2, "0");
  return {
    ...structuredClone(fixture.tasks[0]),
    evaluation_task_id: `console-task-${number}`,
    evaluation_case_id: `evaluation-case:console:${number}`,
    grader_result_id: `grader:console:${number}`,
    run_metrics_id: `metrics:console:${number}`,
    evaluation_result_id: `evaluation-result:console:${number}`,
  };
});
const snapshot = {
  ...fixture,
  task_count: 12,
  passed_task_count: 12,
  failed_task_count: 0,
  unscored_task_count: 0,
  task_result_ids: tasks.map((task) => task.evaluation_result_id),
  tasks,
  snapshot_sha256: "a".repeat(64),
};

const validated = validateEvaluationSnapshot(snapshot);
assert.ok(validated);
const ready = renderEvaluationSurface({ status: "ready", snapshot: validated }, "console-task-05");
assert.equal(ready.status, "ready");
assert.equal(ready.tasks.length, 12);
assert.equal(ready.selectedTask.evaluationTaskId, "console-task-05");
assert.equal(ready.selectedTask.hardGateLabel, "passed");
assert.deepEqual(ready.capabilityLabels, [
  "Replay-only",
  "offline",
  "no network",
  "no model",
  "no external write",
]);
assert.ok(ready.unsupportedMetrics.every((item) => item.includes("unavailable") || item.includes("out of scope")));
assert.ok(ready.selectedTask.localEffectLabel === "none");

const failedGate = structuredClone(snapshot);
failedGate.tasks[0].hard_gates[0].passed = false;
failedGate.tasks[0].hard_gate_passed = false;
failedGate.tasks[0].quality_score = "not_scored";
failedGate.tasks[0].result = "failed";
failedGate.tasks[0].failure_classification = "hard_gate_failed";
failedGate.tasks[0].dimensions[0].score = 0;
failedGate.passed_task_count = 11;
failedGate.unscored_task_count = 1;
const failedValidated = validateEvaluationSnapshot(failedGate);
assert.ok(failedValidated);
const failedRendered = renderEvaluationSurface(
  { status: "ready", snapshot: failedValidated },
  "console-task-01",
);
assert.equal(failedRendered.status, "ready");
assert.equal(failedRendered.selectedTask.hardGateLabel, "failed");
assert.equal(failedRendered.selectedTask.qualityLabel, "not scored (hard gate)");

const raw = structuredClone(snapshot);
raw.tasks[0].raw_payload = "blocked";
assert.equal(validateEvaluationSnapshot(raw), null);
const unsafePath = structuredClone(snapshot);
unsafePath.tasks[0].fixture_source_path = "C:/private/fixture.json";
assert.equal(validateEvaluationSnapshot(unsafePath), null);
const duplicate = structuredClone(snapshot);
duplicate.tasks[1].evaluation_task_id = duplicate.tasks[0].evaluation_task_id;
assert.equal(validateEvaluationSnapshot(duplicate), null);

for (const status of ["loading", "not-found", "identity-denied", "integrity-not-ready"]) {
  const rendered = renderEvaluationSurface({ status });
  assert.equal(rendered.status, status);
  assert.ok(!JSON.stringify(rendered).includes("blocked"));
}

const calls = [];
const loaded = await loadEvaluationSurface(async (input, init) => {
  calls.push({ input, init });
  return { ok: true, status: 200, json: async () => snapshot };
});
assert.equal(loaded.status, "ready");
assert.deepEqual(calls, [
  {
    input: "http://127.0.0.1:8000/v1/evaluations/offline-seed.v1",
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
  const state = await loadEvaluationSurface(async () => ({
    ok: false,
    status,
    json: async () => ({ raw_payload: "blocked" }),
  }));
  assert.equal(state.status, expected);
  assert.ok(!JSON.stringify(state).includes("blocked"));
}
const invalidState = await loadEvaluationSurface(async () => ({
  ok: true,
  status: 200,
  json: async () => raw,
}));
assert.equal(invalidState.status, "integrity-not-ready");

console.log(
  JSON.stringify({
    report_type: "weflow-console-evaluation-check.v1",
    task_summaries_rendered: ready.tasks.length,
    selected_task_hard_gate_checked: true,
    unavailable_states_checked: 4,
    unrestricted_json_rendered: false,
    live_metric_claims_rendered: false,
  }),
);
