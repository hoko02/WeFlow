import type {
  EvaluationSuiteSnapshot,
  EvaluationTaskSnapshot,
  JsonObject,
} from "@weflow/contracts";

export type EvaluationSurfaceState =
  | { status: "loading" }
  | { status: "ready"; snapshot: EvaluationSuiteSnapshot }
  | { status: "not-found" }
  | { status: "identity-denied" }
  | { status: "integrity-not-ready" };

export interface EvaluationTaskSummary {
  evaluationTaskId: string;
  result: "passed" | "failed";
  hardGateLabel: "passed" | "failed";
  qualityLabel: string;
  state: string;
  outcome: string;
}

export interface EvaluationTaskDetail extends EvaluationTaskSummary {
  fixtureId: string;
  fixtureSourcePath: string;
  fixtureHash: string;
  taskHash: string;
  oracleId: string;
  oracleHash: string;
  evaluationResultId: string;
  failureClassification: string;
  gates: Array<{ name: string; status: "passed" | "failed" | "not-applicable"; reasonCode: string }>;
  dimensions: Array<{ name: string; score: number }>;
  counters: Array<{ label: string; value: number }>;
  evidenceLabel: string;
  approvalLabel: string;
  localEffectLabel: string;
}

export interface ReadyEvaluationRenderModel {
  status: "ready";
  headline: string;
  detail: string;
  suiteId: string;
  profile: string;
  reportHash: string;
  snapshotHash: string;
  acceptedLabel: string;
  determinismLabel: string;
  counts: { total: number; passed: number; failed: number; unscored: number };
  capabilityLabels: string[];
  tasks: EvaluationTaskSummary[];
  selectedTask: EvaluationTaskDetail;
  unsupportedMetrics: string[];
}

export interface UnavailableEvaluationRenderModel {
  status: "loading" | "not-found" | "identity-denied" | "integrity-not-ready";
  headline: string;
  detail: string;
}

export type EvaluationRenderModel =
  | ReadyEvaluationRenderModel
  | UnavailableEvaluationRenderModel;

interface EvaluationHttpResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

export type EvaluationFetch = (
  input: string,
  init: { method: "GET"; headers: Record<string, string> },
) => Promise<EvaluationHttpResponse>;

const SNAPSHOT_SCHEMA_ID =
  "https://weflow.local/contracts/v1/evaluation-suite-snapshot.schema.json";
const EVALUATION_ENDPOINT = "http://127.0.0.1:8000/v1/evaluations/offline-seed.v1";
const HASH = /^[a-f0-9]{64}$/i;
const SAFE_PATH = /^[A-Za-z0-9._/-]+\.json$/;
const HARD_GATES = new Set([
  "tenant_reference",
  "offline_replay",
  "external_write_absent",
  "local_effect_identity",
  "approval_binding",
  "evidence_lineage",
  "expected_outcome",
]);
const DIMENSIONS = new Set(["outcome", "evidence", "recovery", "efficiency"]);
const STATES = new Set([
  "APPROVAL_INVALIDATED",
  "DELIVERY_RECORDED",
  "INTAKE_REJECTED",
  "RECEIVED",
  "RESPONSE_READY",
  "TICKET_READY",
  "TRAJECTORY_REPLAY_REJECTED",
  "WAITING_FOR_OPERATOR",
]);
const OUTCOMES = new Set([
  "accepted",
  "authorization_denied",
  "deduplicated",
  "fixture_delivery_recorded",
  "inbound_out_of_order",
  "lineage_invalid",
  "recovered_after_interruption",
  "response_ready",
  "ticket_ready",
  "waiting_for_operator",
]);

function asObject(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function hasExactKeys(value: JsonObject, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && actual.every((key, index) => key === [...expected].sort()[index]);
}

function nonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function hash(value: unknown): value is string {
  return typeof value === "string" && HASH.test(value);
}

function safeSourcePath(value: unknown, prefix: string): value is string {
  return (
    typeof value === "string" &&
    value.startsWith(prefix) &&
    !value.includes("\\") &&
    !value.split("/").includes("..") &&
    SAFE_PATH.test(value)
  );
}

function capabilityFlags(value: unknown): boolean {
  const flags = asObject(value);
  return (
    flags !== null &&
    hasExactKeys(flags, ["external_write", "model", "network", "offline", "replay"]) &&
    flags.offline === true &&
    flags.replay === true &&
    flags.network === false &&
    flags.model === false &&
    flags.external_write === false
  );
}

function metrics(value: unknown): value is JsonObject {
  const item = asObject(value);
  return (
    item !== null &&
    hasExactKeys(item, [
      "external_write_attempt_count",
      "local_effect_count",
      "model_invocation_count",
      "network_request_count",
      "tool_call_count",
    ]) &&
    Number.isInteger(item.tool_call_count) &&
    Number(item.tool_call_count) >= 0 &&
    Number.isInteger(item.local_effect_count) &&
    Number(item.local_effect_count) >= 0 &&
    Number(item.local_effect_count) <= 2 &&
    item.network_request_count === 0 &&
    item.model_invocation_count === 0 &&
    item.external_write_attempt_count === 0
  );
}

function observation(value: unknown): value is JsonObject {
  const item = asObject(value);
  return (
    item !== null &&
    hasExactKeys(item, [
      "approval_valid",
      "evidence_valid",
      "external_write",
      "local_effect_count",
      "model",
      "network",
      "offline",
      "outcome",
      "replay",
      "state",
      "tool_call_count",
    ]) &&
    typeof item.state === "string" &&
    STATES.has(item.state) &&
    typeof item.outcome === "string" &&
    OUTCOMES.has(item.outcome) &&
    typeof item.evidence_valid === "boolean" &&
    typeof item.approval_valid === "boolean" &&
    Number.isInteger(item.tool_call_count) &&
    Number(item.tool_call_count) >= 0 &&
    Number.isInteger(item.local_effect_count) &&
    Number(item.local_effect_count) >= 0 &&
    Number(item.local_effect_count) <= 2 &&
    item.offline === true &&
    item.replay === true &&
    item.network === false &&
    item.model === false &&
    item.external_write === false
  );
}

const TASK_KEYS = [
  "dimensions",
  "evaluation_case_id",
  "evaluation_result_id",
  "evaluation_task_id",
  "failure_classification",
  "fixture_id",
  "fixture_sha256",
  "fixture_source_id",
  "fixture_source_path",
  "grader_result_id",
  "hard_gate_passed",
  "hard_gates",
  "metrics",
  "observation",
  "oracle_id",
  "oracle_sha256",
  "policy_sha256",
  "policy_source_id",
  "policy_source_path",
  "quality_score",
  "result",
  "run_metrics_id",
  "task_sha256",
  "tenant_id",
] as const;

function taskSnapshot(value: unknown, tenantId: string): value is EvaluationTaskSnapshot {
  const task = asObject(value);
  if (task === null || !hasExactKeys(task, TASK_KEYS) || task.tenant_id !== tenantId) return false;
  if (
    ![
      task.evaluation_task_id,
      task.fixture_id,
      task.fixture_source_id,
      task.policy_source_id,
      task.oracle_id,
      task.evaluation_case_id,
      task.grader_result_id,
      task.run_metrics_id,
      task.evaluation_result_id,
    ].every(nonEmpty) ||
    !safeSourcePath(task.fixture_source_path, "fixtures/") ||
    !safeSourcePath(task.policy_source_path, "evals/sources/") ||
    ![task.fixture_sha256, task.policy_sha256, task.task_sha256, task.oracle_sha256].every(hash) ||
    (task.result !== "passed" && task.result !== "failed") ||
    !(task.failure_classification === null || nonEmpty(task.failure_classification))
  ) {
    return false;
  }
  if (!Array.isArray(task.hard_gates) || task.hard_gates.length === 0) return false;
  const gates = task.hard_gates.map(asObject);
  if (
    gates.some(
      (gate) =>
        gate === null ||
        !hasExactKeys(gate, ["applicable", "name", "passed", "reason_code"]) ||
        typeof gate.name !== "string" ||
        !HARD_GATES.has(gate.name) ||
        typeof gate.applicable !== "boolean" ||
        typeof gate.passed !== "boolean" ||
        !nonEmpty(gate.reason_code),
    )
  ) {
    return false;
  }
  const applicable = gates.filter((gate) => gate?.applicable === true);
  const hardGatePassed = applicable.length > 0 && applicable.every((gate) => gate?.passed === true);
  if (task.hard_gate_passed !== hardGatePassed) return false;
  if (hardGatePassed ? typeof task.quality_score !== "number" : task.quality_score !== "not_scored") {
    return false;
  }
  if (!Array.isArray(task.dimensions)) return false;
  if (
    task.dimensions.map(asObject).some(
      (dimension) =>
        dimension === null ||
        !hasExactKeys(dimension, ["name", "score"]) ||
        typeof dimension.name !== "string" ||
        !DIMENSIONS.has(dimension.name) ||
        typeof dimension.score !== "number" ||
        dimension.score < 0 ||
        dimension.score > 100,
    )
  ) {
    return false;
  }
  return (
    metrics(task.metrics) &&
    observation(task.observation) &&
    task.metrics.tool_call_count === task.observation.tool_call_count &&
    task.metrics.local_effect_count === task.observation.local_effect_count
  );
}

const SNAPSHOT_KEYS = [
  "accepted",
  "capability_flags",
  "evaluation_suite_snapshot_id",
  "failed_task_count",
  "passed_task_count",
  "profile",
  "repeated_baseline_equal",
  "report_sha256",
  "schema_id",
  "schema_version",
  "snapshot_sha256",
  "suite_id",
  "suite_report_id",
  "suite_sha256",
  "task_count",
  "task_result_ids",
  "tasks",
  "tenant_id",
  "unscored_task_count",
] as const;

export function validateEvaluationSnapshot(value: unknown): EvaluationSuiteSnapshot | null {
  const snapshot = asObject(value);
  if (
    snapshot === null ||
    !hasExactKeys(snapshot, SNAPSHOT_KEYS) ||
    snapshot.schema_id !== SNAPSHOT_SCHEMA_ID ||
    snapshot.schema_version !== "v1" ||
    snapshot.suite_id !== "offline-seed.v1" ||
    snapshot.profile !== "benchmark-core.v1" ||
    snapshot.accepted !== true ||
    snapshot.repeated_baseline_equal !== true ||
    !nonEmpty(snapshot.tenant_id) ||
    !nonEmpty(snapshot.suite_report_id) ||
    !hash(snapshot.suite_sha256) ||
    !hash(snapshot.report_sha256) ||
    !hash(snapshot.snapshot_sha256) ||
    snapshot.evaluation_suite_snapshot_id !==
      `evaluation-suite-snapshot:${String(snapshot.report_sha256)}` ||
    !capabilityFlags(snapshot.capability_flags) ||
    !Array.isArray(snapshot.tasks) ||
    snapshot.tasks.length !== 12 ||
    snapshot.task_count !== 12 ||
    !Array.isArray(snapshot.task_result_ids) ||
    snapshot.task_result_ids.length !== 12 ||
    !snapshot.tasks.every((task) => taskSnapshot(task, snapshot.tenant_id as string))
  ) {
    return null;
  }
  const tasks = snapshot.tasks as unknown as EvaluationTaskSnapshot[];
  const snapshotResultIds = snapshot.task_result_ids as unknown[];
  const taskIds = tasks.map((task) => task.evaluation_task_id);
  const resultIds = tasks.map((task) => task.evaluation_result_id);
  const passed = tasks.filter(
    (task) => task.result === "passed" && task.quality_score !== "not_scored",
  ).length;
  const unscored = tasks.filter((task) => task.quality_score === "not_scored").length;
  const failed = tasks.length - passed - unscored;
  if (
    new Set(taskIds).size !== taskIds.length ||
    new Set(resultIds).size !== resultIds.length ||
    resultIds.some((resultId, index) => resultId !== snapshotResultIds[index]) ||
    snapshot.passed_task_count !== passed ||
    snapshot.failed_task_count !== failed ||
    snapshot.unscored_task_count !== unscored
  ) {
    return null;
  }
  return snapshot as unknown as EvaluationSuiteSnapshot;
}

export async function loadEvaluationSurface(
  fetcher: EvaluationFetch = globalThis.fetch as EvaluationFetch,
): Promise<EvaluationSurfaceState> {
  try {
    const response = await fetcher(EVALUATION_ENDPOINT, {
      method: "GET",
      headers: { "X-WeFlow-Synthetic-Actor": "simulator-tenant-a" },
    });
    if (response.status === 403) return { status: "identity-denied" };
    if (response.status === 404) return { status: "not-found" };
    if (!response.ok) return { status: "integrity-not-ready" };
    const snapshot = validateEvaluationSnapshot(await response.json());
    return snapshot ? { status: "ready", snapshot } : { status: "integrity-not-ready" };
  } catch {
    return { status: "not-found" };
  }
}

function taskSummary(task: EvaluationTaskSnapshot): EvaluationTaskSummary {
  return {
    evaluationTaskId: task.evaluation_task_id,
    result: task.result,
    hardGateLabel: task.hard_gate_passed ? "passed" : "failed",
    qualityLabel:
      task.quality_score === "not_scored" ? "not scored (hard gate)" : `${task.quality_score}/100`,
    state: task.observation.state,
    outcome: task.observation.outcome,
  };
}

function taskDetail(task: EvaluationTaskSnapshot): EvaluationTaskDetail {
  return {
    ...taskSummary(task),
    fixtureId: task.fixture_id,
    fixtureSourcePath: task.fixture_source_path,
    fixtureHash: task.fixture_sha256,
    taskHash: task.task_sha256,
    oracleId: task.oracle_id,
    oracleHash: task.oracle_sha256,
    evaluationResultId: task.evaluation_result_id,
    failureClassification: task.failure_classification ?? "none",
    gates: task.hard_gates.map((gate) => ({
      name: gate.name,
      status: gate.applicable ? (gate.passed ? "passed" : "failed") : "not-applicable",
      reasonCode: gate.reason_code,
    })),
    dimensions: task.dimensions.map((dimension) => ({ ...dimension })),
    counters: [
      { label: "Tool calls", value: task.metrics.tool_call_count },
      { label: "Fixture-local effects", value: task.metrics.local_effect_count },
      { label: "Network requests", value: task.metrics.network_request_count },
      { label: "Model invocations", value: task.metrics.model_invocation_count },
      { label: "External write attempts", value: task.metrics.external_write_attempt_count },
    ],
    evidenceLabel: task.observation.evidence_valid ? "validated" : "not validated",
    approvalLabel: task.observation.approval_valid ? "fixture-valid" : "not applicable",
    localEffectLabel:
      task.metrics.local_effect_count > 0
        ? "fixture-local record only — no provider or customer receipt"
        : "none",
  };
}

export function renderEvaluationSurface(
  state: EvaluationSurfaceState,
  selectedTaskId?: string,
): EvaluationRenderModel {
  if (state.status === "loading") {
    return { status: "loading", headline: "Evaluation evidence: loading", detail: "Reading the fixed offline suite." };
  }
  if (state.status === "not-found") {
    return { status: "not-found", headline: "Evaluation evidence: unavailable", detail: "No tenant-visible canonical report is available." };
  }
  if (state.status === "identity-denied") {
    return { status: "identity-denied", headline: "Evaluation evidence: identity denied", detail: "The synthetic observer identity was not accepted." };
  }
  if (state.status === "integrity-not-ready") {
    return { status: "integrity-not-ready", headline: "Evaluation evidence: integrity not ready", detail: "The retained evidence did not pass the closed snapshot boundary." };
  }

  const snapshot = state.snapshot;
  const selected =
    snapshot.tasks.find((task) => task.evaluation_task_id === selectedTaskId) ?? snapshot.tasks[0];
  return {
    status: "ready",
    headline: "Offline evaluation evidence: accepted",
    detail: "12 deterministic synthetic tasks, revalidated from the canonical report.",
    suiteId: snapshot.suite_id,
    profile: snapshot.profile,
    reportHash: snapshot.report_sha256,
    snapshotHash: snapshot.snapshot_sha256,
    acceptedLabel: snapshot.accepted ? "accepted" : "not accepted",
    determinismLabel: snapshot.repeated_baseline_equal ? "repeated baselines equal" : "not equal",
    counts: {
      total: snapshot.task_count,
      passed: snapshot.passed_task_count,
      failed: snapshot.failed_task_count,
      unscored: snapshot.unscored_task_count,
    },
    capabilityLabels: ["Replay-only", "offline", "no network", "no model", "no external write"],
    tasks: snapshot.tasks.map(taskSummary),
    selectedTask: taskDetail(selected),
    unsupportedMetrics: [
      "Latency: unavailable — offline fixture scope",
      "Tokens and cost: unavailable — no model invocation",
      "Live-run variance: unavailable — no live runs",
      "Customer receipt: out of scope",
      "Incident resolution: out of scope",
    ],
  };
}
