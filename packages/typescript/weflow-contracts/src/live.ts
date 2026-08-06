import { createHash } from "node:crypto";

import { JsonObject, ValidationResult, canonicalJson, validatePayload } from "./index.js";

export const MODEL_ACTION_PROPOSAL_SCHEMA_ID = "https://weflow.local/contracts/v1/model-action-proposal.schema.json";
export const MODEL_TOOL_OBSERVATION_SCHEMA_ID = "https://weflow.local/contracts/v1/model-tool-observation.schema.json";
export const MODEL_INVOCATION_INTENT_SCHEMA_ID = "https://weflow.local/contracts/v1/model-invocation-intent.schema.json";
export const MODEL_INVOCATION_OBSERVATION_SCHEMA_ID = "https://weflow.local/contracts/v1/model-invocation-observation.schema.json";
export const RESPONSE_DRAFT_ARTIFACT_SCHEMA_ID = "https://weflow.local/contracts/v1/response-draft-artifact.schema.json";
export const LIVE_CANDIDATE_BINDING_SCHEMA_ID = "https://weflow.local/contracts/v1/live-candidate-binding.schema.json";
export const PROVIDER_PRICE_PROFILE_SCHEMA_ID = "https://weflow.local/contracts/v1/provider-price-profile.schema.json";
export const LIVE_RUN_METRICS_SCHEMA_ID = "https://weflow.local/contracts/v1/live-run-metrics.schema.json";
export const LIVE_EVALUATION_ATTEMPT_SCHEMA_ID = "https://weflow.local/contracts/v1/live-evaluation-attempt.schema.json";
export const LIVE_EVALUATION_SUITE_REPORT_SCHEMA_ID = "https://weflow.local/contracts/v1/live-evaluation-suite-report.schema.json";

function validateExpected(payload: JsonObject, schemaId: string, root?: string): ValidationResult {
  const result = validatePayload(payload, root);
  if (!result.valid) return result;
  return payload.schema_id === schemaId
    ? { valid: true }
    : { valid: false, reasonCode: "unexpected_schema" };
}

function claimedHash(payload: JsonObject, field: string): string {
  const material = { ...payload };
  delete material[field];
  return createHash("sha256").update(canonicalJson(material), "utf8").digest("hex");
}

function validateHash(payload: JsonObject, field: string): ValidationResult {
  return payload[field] === claimedHash(payload, field)
    ? { valid: true }
    : { valid: false, reasonCode: `${field}_mismatch` };
}

export function validateModelActionProposal(payload: JsonObject, root?: string): ValidationResult {
  return validateExpected(payload, MODEL_ACTION_PROPOSAL_SCHEMA_ID, root);
}

export function validateModelToolObservation(payload: JsonObject, root?: string): ValidationResult {
  return validateExpected(payload, MODEL_TOOL_OBSERVATION_SCHEMA_ID, root);
}

export function validateModelInvocationIntent(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, MODEL_INVOCATION_INTENT_SCHEMA_ID, root);
  if (!result.valid) return result;
  const reservation = payload.reservation as JsonObject;
  if (reservation.total_tokens !== Number(reservation.input_tokens) + Number(reservation.output_tokens)) {
    return { valid: false, reasonCode: "token_reservation_mismatch" };
  }
  if (Number(reservation.request_timeout_ms) > Number(reservation.wall_time_ms)) {
    return { valid: false, reasonCode: "timeout_reservation_mismatch" };
  }
  return validateHash(payload, "intent_sha256");
}

export function validateModelInvocationObservation(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, MODEL_INVOCATION_OBSERVATION_SCHEMA_ID, root);
  if (!result.valid) return result;
  const usage = payload.usage as JsonObject;
  if (usage.total_tokens !== Number(usage.input_tokens) + Number(usage.output_tokens)) {
    return { valid: false, reasonCode: "token_usage_mismatch" };
  }
  if (payload.status === "completed") {
    if (usage.available !== true || payload.response_sha256 === null || payload.failure_classification !== null) {
      return { valid: false, reasonCode: "completed_observation_incomplete" };
    }
  } else if (payload.failure_classification === null) {
    return { valid: false, reasonCode: "failure_classification_missing" };
  }
  return validateHash(payload, "observation_sha256");
}

export function validateResponseDraftArtifact(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, RESPONSE_DRAFT_ARTIFACT_SCHEMA_ID, root);
  if (!result.valid) return result;
  if (Date.parse(String(payload.expires_at)) <= Date.parse(String(payload.created_at))) {
    return { valid: false, reasonCode: "expiry_invalid" };
  }
  const evidence = (payload.claim_evidence_summary as JsonObject[]).map((item) => item.evidence_sha256);
  if (evidence.length !== new Set(evidence).size) return { valid: false, reasonCode: "evidence_duplicate" };
  return validateHash(payload, "artifact_sha256");
}

export function validateLiveCandidateBinding(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, LIVE_CANDIDATE_BINDING_SCHEMA_ID, root);
  return result.valid ? validateHash(payload, "binding_sha256") : result;
}

export function validateProviderPriceProfile(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, PROVIDER_PRICE_PROFILE_SCHEMA_ID, root);
  if (!result.valid) return result;
  if (Date.parse(String(payload.expires_at)) <= Date.parse(String(payload.effective_at))) {
    return { valid: false, reasonCode: "expiry_invalid" };
  }
  return validateHash(payload, "profile_sha256");
}

export function validateLiveRunMetrics(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, LIVE_RUN_METRICS_SCHEMA_ID, root);
  if (!result.valid) return result;
  if (payload.invocation_count !== Number(payload.successful_invocation_count) + Number(payload.failed_invocation_count)) return { valid: false, reasonCode: "invocation_count_mismatch" };
  if (payload.total_tokens !== Number(payload.input_tokens) + Number(payload.output_tokens)) return { valid: false, reasonCode: "token_count_mismatch" };
  if (Number(payload.valid_proposal_count) > Number(payload.invocation_count)) return { valid: false, reasonCode: "proposal_count_invalid" };
  if (Number(payload.provider_latency_ms) > Number(payload.end_to_end_latency_ms)) return { valid: false, reasonCode: "latency_order_invalid" };
  return validateHash(payload, "metrics_sha256");
}

export function validateLiveEvaluationAttempt(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, LIVE_EVALUATION_ATTEMPT_SCHEMA_ID, root);
  if (!result.valid) return result;
  const passed = (payload.hard_gates as JsonObject[]).every((gate) => gate.passed === true);
  if (payload.hard_gate_passed !== passed) return { valid: false, reasonCode: "hard_gate_summary_invalid" };
  if (passed === (payload.quality_score === "not_scored")) return { valid: false, reasonCode: "quality_score_invalid" };
  const responseReady = payload.terminal_outcome === "response_ready";
  if (responseReady !== Boolean(payload.candidate_binding_id && payload.verifier_outcome_id)) return { valid: false, reasonCode: "candidate_verifier_link_invalid" };
  return validateHash(payload, "attempt_sha256");
}

export function validateLiveEvaluationSuiteReport(payload: JsonObject, root?: string): ValidationResult {
  const result = validateExpected(payload, LIVE_EVALUATION_SUITE_REPORT_SCHEMA_ID, root);
  if (!result.valid) return result;
  const ids = (payload.task_aggregates as JsonObject[]).map((item) => item.evaluation_task_id);
  if (new Set(ids).size !== 6) return { valid: false, reasonCode: "task_ids_duplicate" };
  if (payload.attempt_count !== (payload.attempt_ids as unknown[]).length) return { valid: false, reasonCode: "attempt_count_mismatch" };
  return validateHash(payload, "report_sha256");
}

export function validateLiveContractChain(
  intent: JsonObject,
  observation: JsonObject,
  artifact: JsonObject,
  binding: JsonObject,
  metrics: JsonObject,
  attempt: JsonObject,
  report: JsonObject,
  root?: string,
): ValidationResult {
  for (const result of [
    validateModelInvocationIntent(intent, root), validateModelInvocationObservation(observation, root),
    validateResponseDraftArtifact(artifact, root), validateLiveCandidateBinding(binding, root),
    validateLiveRunMetrics(metrics, root), validateLiveEvaluationAttempt(attempt, root),
    validateLiveEvaluationSuiteReport(report, root),
  ]) if (!result.valid) return result;
  const invocationFields = ["tenant_id", "evaluation_session_id", "suite_id", "evaluation_task_id", "attempt_id", "logical_turn_id", "invocation_id"];
  if (!invocationFields.every((field) => intent[field] === observation[field])) return { valid: false, reasonCode: "invocation_link_mismatch" };
  if (artifact.tenant_id !== observation.tenant_id || artifact.attempt_id !== observation.attempt_id || artifact.producer_invocation_id !== observation.invocation_id) return { valid: false, reasonCode: "artifact_invocation_mismatch" };
  const artifactEvidence = new Set((artifact.claim_evidence_summary as JsonObject[]).map((item) => item.evidence_sha256));
  if (
    binding.invocation_id !== observation.invocation_id || binding.observation_id !== observation.observation_id ||
    binding.draft_artifact_id !== artifact.artifact_id || binding.draft_content_sha256 !== artifact.content_sha256 ||
    (binding.evidence_hashes as unknown[]).some((value) => !artifactEvidence.has(value)) ||
    metrics.tenant_id !== attempt.tenant_id || metrics.evaluation_task_id !== attempt.evaluation_task_id || metrics.attempt_id !== attempt.attempt_id ||
    attempt.live_run_metrics_id !== metrics.live_run_metrics_id || attempt.metrics_sha256 !== metrics.metrics_sha256 ||
    !(attempt.invocation_observation_ids as unknown[]).includes(observation.observation_id) || attempt.candidate_binding_id !== binding.binding_sha256 ||
    attempt.terminal_outcome !== metrics.terminal_outcome || !(report.attempt_ids as unknown[]).includes(attempt.attempt_id) ||
    report.evaluation_session_id !== attempt.evaluation_session_id || report.price_profile_sha256 !== metrics.price_profile_sha256 || report.model_id_sha256 !== metrics.model_id_sha256
  ) return { valid: false, reasonCode: "live_chain_link_mismatch" };
  return { valid: true };
}
