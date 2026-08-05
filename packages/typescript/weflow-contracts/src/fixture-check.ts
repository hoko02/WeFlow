import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  JsonObject,
  canonicalJson,
  validateAgentActionForContext,
  validateBenchmarkCoreResult,
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
) as Record<string, JsonObject>;const missingIdentity = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/invalid/missing-schema-identity.json"), "utf8"),
) as JsonObject;

const failedSchemas: string[] = [];
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
const benchmarkReport = {
  schema_id: "https://weflow.local/contracts/v1/evaluation-suite-report.schema.json", schema_version: "v1", suite_report_id: "suite-report-typescript-001", suite_id: "offline-seed.v1", suite_sha256: "e".repeat(64), profile: "benchmark-core.v1", task_count: 1, passed_task_count: 1, failed_task_count: 0, unscored_task_count: 0, task_result_ids: [benchmarkResultId], capability_flags: benchmarkFlags, report_sha256: "f".repeat(64),
} as JsonObject;
const benchmarkEvaluationResult = {
  schema_id: "https://weflow.local/contracts/v1/evaluation-result.schema.json", schema_version: "v1", tenant_id: "tenant-alpha", evaluation_result_id: benchmarkResultId, evaluation_case_id: "evaluation-case-typescript-001", result: "passed", recorded_at: "2026-08-05T00:00:00Z", failure_classification: null, benchmark_profile: "benchmark-core.v1", suite_id: "offline-seed.v1", evaluation_task_id: "intake-accepted", task_sha256: benchmarkTaskHash, oracle_sha256: benchmarkOracleHash, hard_gate_passed: true, grader_result_id: "grader-typescript-001", run_metrics_id: "metrics-typescript-001", suite_report_id: "suite-report-typescript-001", report_sha256: "f".repeat(64), quality_score: 100, capability_flags: benchmarkFlags,
} as JsonObject;
if (!validateBenchmarkCoreResult(benchmarkEvaluationResult, benchmarkTask, benchmarkOracle, benchmarkGrader, benchmarkMetrics, benchmarkReport, root).valid) failedSchemas.push("benchmark-core-result");
const invalidBenchmark = structuredClone(benchmarkGrader) as JsonObject;
(invalidBenchmark.hard_gates as JsonObject[])[0].passed = false;
invalidBenchmark.hard_gate_passed = false;
if (validateBenchmarkCoreResult({ ...benchmarkEvaluationResult, hard_gate_passed: false, quality_score: 100 }, benchmarkTask, benchmarkOracle, invalidBenchmark, benchmarkMetrics, benchmarkReport, root).valid) failedSchemas.push("benchmark-core-unscored-gate");
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
      2,
  }),
);
