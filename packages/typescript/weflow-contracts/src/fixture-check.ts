import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  JsonObject,
  canonicalJson,
  validateAgentActionForContext,
  validateBenchmarkCoreResult,
  validateEvaluationSuiteSnapshot,
  finalizeOperatorCaseSnapshot,
  operatorCaseEntryId,
  validateOperatorCaseSnapshot,
  validateEvidenceChain,
  validateChange4AuthorizationProfile,
  validateHashBoundApproval,
  validateOutboundDeliveryChain,
  validateCheckpointSequence,
  validateSideEffectChain,
  validateSideEffectIntents,
  validateGeneratedLedgerEvent,
  validatePayload,
  validateWorkflowCommandTenant,
  validateWorkflowCommandVersion,
} from "./index.js";
import {
  validateLiveContractChain,
  validateModelActionProposal,
  validateModelToolObservation,
  validateProviderPriceProfile,
} from "./live.js";

function findRepositoryRoot(start = process.cwd()): string {
  let current = resolve(start);
  while (true) {
    try {
      readFileSync(resolve(current, "pyproject.toml"), "utf8");
      return current;
    } catch {
      const parent = resolve(current, "..");
      if (parent === current) {
        throw new Error("WeFlow repository root could not be located");
      }
      current = parent;
    }
  }
}

const root = findRepositoryRoot();
const validPayloads = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/valid-payloads.json"), "utf8"),
) as Record<string, JsonObject>;
const invalidIntakePayloads = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/intake-invalid-payloads.json"), "utf8"),
) as Record<string, JsonObject>;
const invalidWorkflowPayloads = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/workflow-invalid-payloads.json"), "utf8"),
) as Record<string, JsonObject>;
const invalidAgentPayloads = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/agent-invalid-payloads.json"), "utf8"),
) as Record<string, JsonObject>;
const agentBoundary = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/agent-boundary.json"), "utf8"),
) as {
  context_manifest: JsonObject;
  agent_action: JsonObject;
  foreign_agent_action: JsonObject;
};
const missingGeneratedMetadata = JSON.parse(
  readFileSync(
    resolve(root, "fixtures/contracts/v1/semantic/missing-generated-ledger-metadata.json"),
    "utf8",
  ),
) as JsonObject;
const workflowNegativeCases = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/workflow-negative-cases.json"), "utf8"),
) as {
  foreign_command: JsonObject;
  stale_command: JsonObject;
  current_workflow_version: number;
  duplicate_intents: JsonObject[];
  conflicting_observation: JsonObject;
};
const workflowRecovery = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/workflow-recovery.json"), "utf8"),
) as {
  checkpoints: JsonObject[];
  intent: JsonObject;
  observations: JsonObject[];
  completions: JsonObject[];
};
const authorizationDelivery = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/authorization-delivery.json"), "utf8"),
) as {
  grant: JsonObject;
  policy_decision: JsonObject;
  authorization_binding: JsonObject;
  approval_request: JsonObject;
  approval_decision: JsonObject;
  outbound_delivery_intent: JsonObject;
  outbound_delivery_observation: JsonObject;
  outbound_delivery_completion: JsonObject;
};
const evidenceTrajectory = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/evidence-trajectory.json"), "utf8"),
) as { artifact: JsonObject; trajectory: JsonObject; report: JsonObject; replay_result: JsonObject };
const evidenceInvalid = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/evidence-trajectory-invalid-payloads.json"), "utf8"),
) as Record<string, { field: string; value?: unknown }>;
const invalidBenchmarkPayloads = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/evaluation-benchmark-invalid-payloads.json"), "utf8"),
) as Record<string, JsonObject>;
const evaluationSuiteSnapshot = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/evaluation-suite-snapshot.json"), "utf8"),
) as JsonObject;
const operatorCaseSnapshot = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/operator-case-snapshot.json"), "utf8"),
) as JsonObject;
const invalidOperatorCaseSnapshotCases = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/operator-case-snapshot-invalid-cases.json"), "utf8"),
) as Record<string, string>;
const invalidEvaluationSuiteSnapshotCases = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/evaluation-suite-snapshot-invalid-cases.json"), "utf8"),
) as Record<string, string>;
const missingIdentity = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/missing-schema-identity.json"), "utf8"),
) as JsonObject;
const liveBoundary = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/live-boundary.json"), "utf8"),
) as Record<string, JsonObject>;
const invalidLivePayloads = JSON.parse(
  readFileSync(
    resolve(root, "fixtures/contracts/v1/invalid/live-boundary-invalid-payloads.json"), "utf8",
  ),
) as Record<string, JsonObject>;

const failedSchemas: string[] = [];

function rehashEvaluationSuiteSnapshot(snapshot: JsonObject): void {
  const material = { ...snapshot };
  delete material.snapshot_sha256;
  snapshot.snapshot_sha256 = createHash("sha256").update(canonicalJson(material), "utf8").digest("hex");
}

function invalidEvaluationSuiteSnapshot(kind: string): JsonObject {
  const snapshot = structuredClone(evaluationSuiteSnapshot) as JsonObject;
  const tasks = snapshot.tasks as JsonObject[];
  const task = tasks[0];
  if (kind === "task_tenant") {
    task.tenant_id = "tenant-foreign";
    rehashEvaluationSuiteSnapshot(snapshot);
  } else if (kind === "report_hash") {
    snapshot.report_sha256 = "1".repeat(64);
    rehashEvaluationSuiteSnapshot(snapshot);
  } else if (kind === "suite_hash") {
    snapshot.suite_sha256 = "2".repeat(64);
  } else if (kind === "source_hash") {
    task.fixture_sha256 = "3".repeat(64);
  } else if (kind === "result_id") {
    task.evaluation_result_id = "evaluation-result:detached";
    rehashEvaluationSuiteSnapshot(snapshot);
  } else if (kind === "duplicate_task") {
    tasks.push(structuredClone(task));
    snapshot.task_count = 2;
    snapshot.passed_task_count = 2;
    (snapshot.task_result_ids as unknown[]).push(task.evaluation_result_id);
    rehashEvaluationSuiteSnapshot(snapshot);
  } else if (kind === "count") {
    snapshot.passed_task_count = 0;
    snapshot.failed_task_count = 1;
    rehashEvaluationSuiteSnapshot(snapshot);
  } else if (kind === "failed_gate_score") {
    ((task.hard_gates as JsonObject[])[0]).passed = false;
    task.hard_gate_passed = false;
    rehashEvaluationSuiteSnapshot(snapshot);
  } else if (kind === "absolute_path") {
    task.fixture_source_path = "C:/private/fixture.json";
  } else if (kind === "raw") {
    task.raw_payload = "blocked";
  } else if (kind === "secret") {
    task.provider_token = "blocked";
  } else if (kind === "authority") {
    snapshot.caller_role = "operator";
  } else if (kind === "live_provider") {
    snapshot.live_provider_enabled = true;
  } else if (kind === "customer_success") {
    snapshot.customer_resolved = true;
  } else if (kind === "external_write") {
    (snapshot.capability_flags as JsonObject).external_write = true;
  } else {
    throw new Error("unknown-invalid-evaluation-suite-snapshot-kind");
  }
  return snapshot;
}

function operatorEntry(snapshot: JsonObject, kind: string): JsonObject {
  return (snapshot.timeline as JsonObject[]).find((item) => item.source_kind === kind) as JsonObject;
}

function relinkOperatorSnapshot(snapshot: JsonObject): void {
  let prior: string | null = null;
  (snapshot.timeline as JsonObject[]).forEach((entry, index) => {
    const sequence = index + 1;
    entry.sequence = sequence;
    entry.entry_id = operatorCaseEntryId({
      sequence,
      sourceKind: String(entry.source_kind),
      sourceId: String(entry.source_id),
      sourceSha256: String(entry.source_sha256),
    });
    entry.predecessor_entry_id = prior;
    prior = String(entry.entry_id);
  });
}

function refinalizeOperatorSnapshot(snapshot: JsonObject): JsonObject {
  return finalizeOperatorCaseSnapshot(snapshot) as JsonObject;
}

function invalidOperatorCaseSnapshot(kind: string): JsonObject {
  let snapshot = structuredClone(operatorCaseSnapshot) as JsonObject;
  const timeline = snapshot.timeline as JsonObject[];
  if (kind === "foreign_identity") snapshot.tenant_id = "tenant-foreign";
  else if (kind === "detached_source_hash") {
    operatorEntry(snapshot, "tool_result").source_sha256 = "f".repeat(64);
    relinkOperatorSnapshot(snapshot); snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "detached_evidence_root") {
    (snapshot.evidence as JsonObject).root_sha256 = "e".repeat(64);
    snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "detached_replay_root") {
    (snapshot.replay as JsonObject).replayed_root_sha256 = "d".repeat(64);
    snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "snapshot_hash") snapshot.snapshot_sha256 = "c".repeat(64);
  else if (kind === "missing_entry") {
    snapshot.timeline = timeline.filter((item) => item.source_kind !== "capability_grant");
    relinkOperatorSnapshot(snapshot); snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "duplicate_entry") {
    timeline.splice(2, 0, structuredClone(timeline[1]));
    relinkOperatorSnapshot(snapshot); snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "duplicate_source") {
    timeline[2].source_id = timeline[1].source_id;
    timeline[2].source_kind = timeline[1].source_kind;
    timeline[2].phase = timeline[1].phase;
    relinkOperatorSnapshot(snapshot); snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "out_of_order_entry") {
    [timeline[0], timeline[timeline.length - 2]] = [timeline[timeline.length - 2], timeline[0]];
    relinkOperatorSnapshot(snapshot); snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "predecessor_mismatch") {
    timeline[1].predecessor_entry_id = null;
    snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "count_mismatch") {
    const counts = snapshot.counts as JsonObject;
    counts.timeline_entry_count = Number(counts.timeline_entry_count) + 1;
    snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "stale_approval_as_success") {
    const entry = operatorEntry(snapshot, "approval_decision");
    entry.observation = "stale"; entry.reason_code = "stale_approval";
    snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "policy_denial_as_success") {
    const entry = operatorEntry(snapshot, "policy_decision");
    entry.observation = "denied"; entry.reason_code = "policy_denied";
    snapshot = refinalizeOperatorSnapshot(snapshot);
  } else if (kind === "raw_field") snapshot.raw_payload = "blocked";
  else if (kind === "secret_like_field") snapshot.provider_token = "blocked";
  else if (kind === "executable_field") {
    operatorEntry(snapshot, "agent_step").reason_code = "<script>alert(1)</script>";
  } else if (kind === "absolute_path") snapshot.fixture_source_path = "C:/private/fixture.json";
  else if (kind === "escaping_path") snapshot.fixture_source_path = "../fixtures/policy/fixture.json";
  else if (kind === "caller_authority") snapshot.caller_role = "operator";
  else if (kind === "live_provider") (snapshot.capabilities as JsonObject).live_provider = true;
  else if (kind === "customer_success") (snapshot.capabilities as JsonObject).customer_resolution = true;
  else if (kind === "mutation_capability") (snapshot.capabilities as JsonObject).workflow_authority = true;
  else if (kind === "effect_capability") (snapshot.capabilities as JsonObject).retry_authority = true;
  else if (kind === "unsupported_recovery") {
    const entry = operatorEntry(snapshot, "delivery_completion");
    entry.recovery_status = "recovered"; entry.reason_code = "recovered_after_interruption";
    snapshot = refinalizeOperatorSnapshot(snapshot);
  } else throw new Error("unknown-invalid-operator-case-snapshot-kind");
  return snapshot;
}

for (const [name, payload] of Object.entries(validPayloads)) {
  if (!validatePayload(payload, root).valid) {
    failedSchemas.push(name);
  }
}
for (const [name, payload] of Object.entries(invalidIntakePayloads)) {
  if (validatePayload(payload, root).valid) {
    failedSchemas.push(`invalid-${name}`);
  }
}
for (const [name, payload] of Object.entries(invalidWorkflowPayloads)) {
  if (validatePayload(payload, root).valid) {
    failedSchemas.push(`invalid-workflow-${name}`);
  }
}
for (const [name, payload] of Object.entries(invalidBenchmarkPayloads)) {
  if (validatePayload(payload, root).valid) {
    failedSchemas.push(`invalid-benchmark-${name}`);
  }
}for (const [name, payload] of Object.entries(invalidAgentPayloads)) {
  if (validatePayload(payload, root).valid) {
    failedSchemas.push(`invalid-agent-${name}`);
  }
}
if (!validateAgentActionForContext(agentBoundary.agent_action, agentBoundary.context_manifest, root).valid) {
  failedSchemas.push("agent-context-link");
}
if (validateAgentActionForContext(agentBoundary.foreign_agent_action, agentBoundary.context_manifest, root).valid) {
  failedSchemas.push("foreign-agent-action");
}
if (
  !validateChange4AuthorizationProfile(
    authorizationDelivery.authorization_binding,
    authorizationDelivery.grant,
    authorizationDelivery.policy_decision,
    {
      action: "outbound_delivery.execute",
      currentCaseRevisionId: "revision-api-503",
      currentCheckpointId: "checkpoint-api-503",
      currentWorkflowVersion: 7,
      currentCandidateHash: "d".repeat(64),
      currentEvidenceHashes: ["a".repeat(64), "b".repeat(64), "c".repeat(64)],
      resourceId: "fixture-local-im:api-503",
      dataClassification: "synthetic",
      effectiveTenantId: "tenant-alpha",
      now: "2026-07-29T00:00:03Z",
    },
    root,
  ).valid
) {
  failedSchemas.push("change4-authorization-profile");
}
if (
  !validateHashBoundApproval(
    authorizationDelivery.approval_request,
    authorizationDelivery.approval_decision,
    authorizationDelivery.authorization_binding,
    {
      currentCaseRevisionId: "revision-api-503",
      currentCheckpointId: "checkpoint-api-503",
      currentWorkflowVersion: 7,
      currentCandidateHash: "d".repeat(64),
      currentEvidenceHashes: ["a".repeat(64), "b".repeat(64), "c".repeat(64)],
      effectiveTenantId: "tenant-alpha",
      effectiveApproverId: "fixture-approver-alpha",
      effectiveApproverRole: "fixture-approver",
      now: "2026-07-29T00:00:03Z",
    },
    root,
  ).valid
) {
  failedSchemas.push("change4-hash-bound-approval");
}
if (
  !validateOutboundDeliveryChain(
    authorizationDelivery.outbound_delivery_intent,
    [authorizationDelivery.outbound_delivery_observation],
    [authorizationDelivery.outbound_delivery_completion],
    authorizationDelivery.authorization_binding,
    root,
  ).valid
) {
  failedSchemas.push("change4-outbound-delivery-chain");
}
if (!validateEvidenceChain(evidenceTrajectory.artifact, evidenceTrajectory.trajectory, evidenceTrajectory.report, evidenceTrajectory.replay_result, root).valid) {
  failedSchemas.push("evidence-chain");
}
for (const [name, mutation] of Object.entries(evidenceInvalid)) {
  const artifact = structuredClone(evidenceTrajectory.artifact);
  const trajectory = structuredClone(evidenceTrajectory.trajectory);
  const report = structuredClone(evidenceTrajectory.report);
  const replay = structuredClone(evidenceTrajectory.replay_result);
  if (name === "raw_payload") (report as JsonObject)[mutation.field] = "blocked";
  else if (name === "foreign_tenant") (report as JsonObject)[mutation.field] = mutation.value;
  else if (name === "duplicate_node") ((trajectory.nodes as JsonObject[])[2])[mutation.field] = mutation.value;
  else if (name === "out_of_order") ((trajectory.nodes as JsonObject[])[2])[mutation.field] = mutation.value;
  else if (name === "customer_success") (report as JsonObject)[mutation.field] = mutation.value;
  else (trajectory as JsonObject)[mutation.field] = mutation.value;
  if (validateEvidenceChain(artifact, trajectory, report, replay, root).valid) failedSchemas.push(`invalid-evidence-${name}`);
}
if (validatePayload(missingIdentity, root).valid) {
  failedSchemas.push("missing-schema-identity");
}
if (validateGeneratedLedgerEvent(missingGeneratedMetadata, root).valid) {
  failedSchemas.push("missing-generated-ledger-metadata");
}
if (validateWorkflowCommandTenant(workflowNegativeCases.foreign_command, "tenant-demo", root).valid) {
  failedSchemas.push("foreign-workflow-command");
}
if (
  validateWorkflowCommandVersion(
    workflowNegativeCases.stale_command,
    workflowNegativeCases.current_workflow_version,
    root,
  ).valid
) {
  failedSchemas.push("stale-workflow-command");
}
if (validateSideEffectIntents(workflowNegativeCases.duplicate_intents, root).valid) {
  failedSchemas.push("duplicate-workflow-intent");
}
if (!validateCheckpointSequence(workflowRecovery.checkpoints, root).valid) {
  failedSchemas.push("workflow-checkpoint-sequence");
}
if (
  !validateSideEffectChain(
    workflowRecovery.intent,
    workflowRecovery.observations,
    workflowRecovery.completions,
    root,
  ).valid
) {
  failedSchemas.push("workflow-side-effect-chain");
}
if (!validatePayload(workflowNegativeCases.conflicting_observation, root).valid) {
  failedSchemas.push("conflicting-workflow-observation");
}
const benchmarkTask = JSON.parse(readFileSync(resolve(root, "evals/tasks/intake-accepted/task.json"), "utf8")) as JsonObject;
const benchmarkOracle = JSON.parse(readFileSync(resolve(root, "evals/tasks/intake-accepted/oracle.json"), "utf8")) as JsonObject;
const benchmarkTaskHash = createHash("sha256").update(canonicalJson(benchmarkTask)).digest("hex");
const benchmarkOracleHash = createHash("sha256").update(canonicalJson(benchmarkOracle)).digest("hex");
const benchmarkResultId = "evaluation-result-typescript-001";
const benchmarkFlags = { offline: true, replay: true, network: false, model: false, external_write: false };
const benchmarkGrader = {
  schema_id: "https://weflow.local/contracts/v1/grader-result.schema.json", schema_version: "v1", tenant_id: "tenant-alpha", grader_result_id: "grader-typescript-001", suite_id: "offline-seed.v1", run_id: "typescript-run-001", evaluation_task_id: "intake-accepted", task_sha256: benchmarkTaskHash, oracle_sha256: benchmarkOracleHash,
  hard_gates: (benchmarkOracle.required_hard_gates as string[]).map((name) => ({ name, applicable: true, passed: true, reason_code: "passed" })), hard_gate_passed: true,
  dimensions: ["outcome", "evidence", "recovery", "efficiency"].map((name) => ({ name, score: 100 })), quality_score: 100, result: "passed", failure_classification: null, capability_flags: benchmarkFlags,
} as JsonObject;
const benchmarkMetrics = {
  schema_id: "https://weflow.local/contracts/v1/run-metrics.schema.json", schema_version: "v1", tenant_id: "tenant-alpha", run_metrics_id: "metrics-typescript-001", suite_id: "offline-seed.v1", run_id: "typescript-run-001", evaluation_task_id: "intake-accepted", tool_call_count: 0, local_effect_count: 0, network_request_count: 0, model_invocation_count: 0, external_write_attempt_count: 0,
} as JsonObject;
const benchmarkReportMaterial = {
  schema_id: "https://weflow.local/contracts/v1/evaluation-suite-report.schema.json",
  schema_version: "v1",
  suite_report_id: "suite-report-typescript-001",
  suite_id: "offline-seed.v1",
  suite_sha256: "e".repeat(64),
  profile: "benchmark-core.v1",
  task_count: 1,
  passed_task_count: 1,
  failed_task_count: 0,
  unscored_task_count: 0,
  task_result_ids: [benchmarkResultId],
  capability_flags: benchmarkFlags,
} as JsonObject;
const benchmarkReport = {
  ...benchmarkReportMaterial,
  report_sha256: createHash("sha256").update(canonicalJson(benchmarkReportMaterial)).digest("hex"),
} as JsonObject;
const benchmarkEvaluationCase = {
  schema_id: "https://weflow.local/contracts/v1/evaluation-case.schema.json",
  schema_version: "v1",
  tenant_id: "tenant-alpha",
  evaluation_case_id: "evaluation-case-typescript-001",
  fixture_id: benchmarkTask.fixture_id,
  input_hash: benchmarkTask.fixture_sha256,
  created_at: "2026-08-05T00:00:00Z",
  oracle_id: benchmarkOracle.oracle_id,
  benchmark_profile: "benchmark-core.v1",
  suite_id: "offline-seed.v1",
  evaluation_task_id: "intake-accepted",
  task_sha256: benchmarkTaskHash,
  oracle_sha256: benchmarkOracleHash,
} as JsonObject;
const benchmarkEvaluationResult = {
  schema_id: "https://weflow.local/contracts/v1/evaluation-result.schema.json",
  schema_version: "v1",
  tenant_id: "tenant-alpha",
  evaluation_result_id: benchmarkResultId,
  evaluation_case_id: "evaluation-case-typescript-001",
  result: "passed",
  recorded_at: "2026-08-05T00:00:00Z",
  failure_classification: null,
  benchmark_profile: "benchmark-core.v1",
  suite_id: "offline-seed.v1",
  evaluation_task_id: "intake-accepted",
  task_sha256: benchmarkTaskHash,
  oracle_sha256: benchmarkOracleHash,
  hard_gate_passed: true,
  grader_result_id: "grader-typescript-001",
  run_metrics_id: "metrics-typescript-001",
  suite_report_id: "suite-report-typescript-001",
  report_sha256: benchmarkReport.report_sha256,
  quality_score: 100,
  capability_flags: benchmarkFlags,
} as JsonObject;
if (!validateBenchmarkCoreResult(benchmarkEvaluationCase, benchmarkEvaluationResult, benchmarkTask, benchmarkOracle, benchmarkGrader, benchmarkMetrics, benchmarkReport, root).valid) failedSchemas.push("benchmark-core-result");
const invalidBenchmark = structuredClone(benchmarkGrader) as JsonObject;
(invalidBenchmark.hard_gates as JsonObject[])[0].passed = false;
invalidBenchmark.hard_gate_passed = false;
if (validateBenchmarkCoreResult(benchmarkEvaluationCase, { ...benchmarkEvaluationResult, hard_gate_passed: false, quality_score: 100 }, benchmarkTask, benchmarkOracle, invalidBenchmark, benchmarkMetrics, benchmarkReport, root).valid) failedSchemas.push("benchmark-core-unscored-gate");
if (validateBenchmarkCoreResult(benchmarkEvaluationCase, { ...benchmarkEvaluationResult, suite_report_id: "detached-report" }, benchmarkTask, benchmarkOracle, benchmarkGrader, benchmarkMetrics, benchmarkReport, root).valid) failedSchemas.push("benchmark-core-detached-report");
if (validateBenchmarkCoreResult({ ...benchmarkEvaluationCase, input_hash: "f".repeat(64) }, benchmarkEvaluationResult, benchmarkTask, benchmarkOracle, benchmarkGrader, benchmarkMetrics, benchmarkReport, root).valid) failedSchemas.push("benchmark-core-source-mismatch");
if (validateBenchmarkCoreResult(benchmarkEvaluationCase, benchmarkEvaluationResult, benchmarkTask, benchmarkOracle, benchmarkGrader, { ...benchmarkMetrics, evaluation_task_id: "another-task" }, benchmarkReport, root).valid) failedSchemas.push("benchmark-core-cross-task-link");
const unscoredGrader = structuredClone(benchmarkGrader) as JsonObject;
(unscoredGrader.hard_gates as JsonObject[])[0].passed = false;
(unscoredGrader.hard_gates as JsonObject[])[0].reason_code = "tenant_reference_failed";
unscoredGrader.hard_gate_passed = false;
unscoredGrader.quality_score = "not_scored";
unscoredGrader.result = "failed";
unscoredGrader.failure_classification = "hard_gate_failed";
const unscoredReportMaterial = {
  ...benchmarkReportMaterial,
  passed_task_count: 0,
  unscored_task_count: 1,
} as JsonObject;
const unscoredReport = {
  ...unscoredReportMaterial,
  report_sha256: createHash("sha256").update(canonicalJson(unscoredReportMaterial)).digest("hex"),
} as JsonObject;
const unscoredResult = {
  ...benchmarkEvaluationResult,
  hard_gate_passed: false,
  quality_score: "not_scored",
  result: "failed",
  failure_classification: "hard_gate_failed",
  report_sha256: unscoredReport.report_sha256,
} as JsonObject;
if (!validateBenchmarkCoreResult(benchmarkEvaluationCase, unscoredResult, benchmarkTask, benchmarkOracle, unscoredGrader, benchmarkMetrics, unscoredReport, root).valid) failedSchemas.push("benchmark-core-unscored-chain");
if (!validateEvaluationSuiteSnapshot(evaluationSuiteSnapshot, root).valid) {
  failedSchemas.push("evaluation-suite-snapshot");
}
for (const [name, kind] of Object.entries(invalidEvaluationSuiteSnapshotCases)) {
  if (validateEvaluationSuiteSnapshot(invalidEvaluationSuiteSnapshot(kind), root).valid) {
    failedSchemas.push("invalid-evaluation-suite-snapshot-" + name);
  }
}
if (!validateOperatorCaseSnapshot(operatorCaseSnapshot, root).valid) {
  failedSchemas.push("operator-case-snapshot");
}
for (const [name, kind] of Object.entries(invalidOperatorCaseSnapshotCases)) {
  if (validateOperatorCaseSnapshot(invalidOperatorCaseSnapshot(kind), root).valid) {
    failedSchemas.push("invalid-operator-case-snapshot-" + name);
  }
}

for (const [name, payload] of Object.entries(liveBoundary)) {
  if (!validatePayload(payload, root).valid) failedSchemas.push("live-schema-" + name);
}
for (const [name, payload] of Object.entries(invalidLivePayloads)) {
  if (validatePayload(payload, root).valid) failedSchemas.push("invalid-live-" + name);
}
if (!validateModelActionProposal(liveBoundary.model_action_proposal, root).valid) {
  failedSchemas.push("model-action-proposal");
}
if (!validateModelToolObservation(liveBoundary.model_tool_observation, root).valid) {
  failedSchemas.push("model-tool-observation");
}

function rehashLive(payload: JsonObject, field: string): void {
  const material = { ...payload };
  delete material[field];
  payload[field] = createHash("sha256").update(canonicalJson(material), "utf8").digest("hex");
}

const liveIntent = structuredClone(liveBoundary.model_invocation_intent);
const liveObservation = structuredClone(liveBoundary.model_invocation_observation);
const liveArtifact = structuredClone(liveBoundary.response_draft_artifact);
const liveBinding = structuredClone(liveBoundary.live_candidate_binding);
const liveMetrics = structuredClone(liveBoundary.live_run_metrics);
const liveAttempt = structuredClone(liveBoundary.live_evaluation_attempt);
const liveReport = structuredClone(liveBoundary.live_evaluation_suite_report);
for (const [payload, field] of [
  [liveIntent, "intent_sha256"],
  [liveObservation, "observation_sha256"],
  [liveArtifact, "artifact_sha256"],
  [liveBinding, "binding_sha256"],
  [liveMetrics, "metrics_sha256"],
] as [JsonObject, string][]) rehashLive(payload, field);
liveAttempt.metrics_sha256 = liveMetrics.metrics_sha256;
liveAttempt.candidate_binding_id = liveBinding.binding_sha256;
rehashLive(liveAttempt, "attempt_sha256");
rehashLive(liveReport, "report_sha256");
if (!validateLiveContractChain(liveIntent, liveObservation, liveArtifact, liveBinding, liveMetrics, liveAttempt, liveReport, root).valid) {
  failedSchemas.push("live-contract-chain");
}
const livePriceProfile = structuredClone(liveBoundary.provider_price_profile);
rehashLive(livePriceProfile, "profile_sha256");
if (!validateProviderPriceProfile(livePriceProfile, root).valid) failedSchemas.push("live-price-profile");
const detachedLiveBinding = structuredClone(liveBinding);
detachedLiveBinding.tenant_id = "tenant-foreign";
rehashLive(detachedLiveBinding, "binding_sha256");
if (validateLiveContractChain(liveIntent, liveObservation, liveArtifact, detachedLiveBinding, liveMetrics, liveAttempt, liveReport, root).valid) {
  failedSchemas.push("detached-live-binding");
}
if (failedSchemas.length > 0) {
  throw new Error(`contract-fixture-check-failed:${failedSchemas.join(",")}`);
}

console.log(
  JSON.stringify({
    report_type: "weflow-typescript-contract-check.v1",
    valid_payloads: Object.keys(validPayloads).length,
    invalid_payloads:
      Object.keys(invalidIntakePayloads).length +
      Object.keys(invalidWorkflowPayloads).length +
      Object.keys(invalidAgentPayloads).length +
      Object.keys(evidenceInvalid).length +
      Object.keys(invalidBenchmarkPayloads).length +
      Object.keys(invalidOperatorCaseSnapshotCases).length +
      Object.keys(invalidLivePayloads).length +
      2,
  }),
);
