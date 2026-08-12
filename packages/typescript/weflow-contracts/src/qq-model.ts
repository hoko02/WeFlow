import { createHash } from "node:crypto";

import { JsonObject, canonicalJson, validatePayload } from "./index.js";

const BASE = "https://weflow.local/contracts/v1";
export const QQ_MODEL_WORKFLOW_READINESS_SCHEMA_ID = `${BASE}/qq-model-workflow-readiness.schema.json`;
export const QQ_MODEL_ASSIST_COMMAND_SCHEMA_ID = `${BASE}/qq-model-assist-command.schema.json`;
export const QQ_MODEL_ASSIST_REQUEST_SCHEMA_ID = `${BASE}/qq-model-assist-request.schema.json`;
export const QQ_MODEL_ASSIST_CONTEXT_SCHEMA_ID = `${BASE}/qq-model-assist-context.schema.json`;
export const QQ_MODEL_CASE_BUDGET_SCHEMA_ID = `${BASE}/qq-model-case-budget.schema.json`;
export const QQ_MODEL_INVOCATION_EVIDENCE_SCHEMA_ID = `${BASE}/qq-model-invocation-evidence.schema.json`;
export const QQ_MODEL_CANDIDATE_BINDING_SCHEMA_ID = `${BASE}/qq-model-candidate-binding.schema.json`;
export const QQ_MODEL_PRIVATE_PREVIEW_SCHEMA_ID = `${BASE}/qq-model-private-preview.schema.json`;
export const QQ_MODEL_ASSIST_OUTCOME_SCHEMA_ID = `${BASE}/qq-model-assist-outcome.schema.json`;
export const QQ_MODEL_WORKFLOW_ACCEPTANCE_REPORT_SCHEMA_ID = `${BASE}/qq-model-workflow-acceptance-report.schema.json`;
export const QQ_MODEL_WORKFLOW_VERIFICATION_SCHEMA_ID = `${BASE}/qq-model-workflow-verification.schema.json`;

export interface QQModelAssistCommand extends JsonObject {
  schema_id: typeof QQ_MODEL_ASSIST_COMMAND_SCHEMA_ID;
  surface: "c2c";
  command: "assist";
  case_id: string;
  expected_version: number;
}

export interface QQModelAssistOutcome extends JsonObject {
  schema_id: typeof QQ_MODEL_ASSIST_OUTCOME_SCHEMA_ID;
  terminal_outcome: "response_ready" | "needs_information" | "needs_operator" |
    "tool_timeout" | "budget_exhausted" | "policy_denied" |
    "malformed_model_output" | "provider_outcome_unknown";
  manual_draft_available: true;
  approval_authorized: false;
  delivery_authorized: false;
  customer_outcome_verified: false;
}

export interface QQModelWorkflowAcceptanceReport extends JsonObject {
  schema_id: typeof QQ_MODEL_WORKFLOW_ACCEPTANCE_REPORT_SCHEMA_ID;
  mode: "offline-fake" | "qq-model-integrated-live";
  report_sha256: string;
  customer_receipt_verified: false;
  issue_resolution: false;
  case_completion: false;
  production_ready: false;
}

export type QQModelValidation = { valid: boolean; errors: string[] };

function schema(payload: JsonObject, expected: string, root?: string): QQModelValidation {
  if (payload.schema_id !== expected) return { valid: false, errors: ["unexpected_schema"] };
  return validatePayload(payload, root).valid
    ? { valid: true, errors: [] }
    : { valid: false, errors: ["schema"] };
}

function canonicalHash(payload: JsonObject, without: string): string {
  const material = { ...payload };
  delete material[without];
  return createHash("sha256").update(canonicalJson(material)).digest("hex");
}

function claimedHash(payload: JsonObject, field: string): boolean {
  return payload[field] === canonicalHash(payload, field);
}

const forbiddenKeys = new Set([
  "member_openid", "user_openid", "group_openid", "client_secret", "access_token",
  "authorization", "raw_event", "provider_response", "provider_request", "customer_issue",
  "issue_text", "candidate_text", "draft", "draft_preview", "prompt", "transcript", "tool_output",
]);

function safeTree(value: unknown): boolean {
  if (Array.isArray(value)) return value.every(safeTree);
  if (value !== null && typeof value === "object") {
    return Object.entries(value).every(([key, child]) =>
      !forbiddenKeys.has(key.toLowerCase()) && safeTree(child));
  }
  if (typeof value === "string") {
    return !/(?:\bBearer\s+[A-Za-z0-9._-]+|\bsk-[A-Za-z0-9_-]{8,}|(?:api[_ -]?key|client[_ -]?secret|access[_ -]?token)\s*[:=])/i
      .test(value);
  }
  return true;
}

export function validateQQModelWorkflowReadiness(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_WORKFLOW_READINESS_SCHEMA_ID, root);
  if (!base.valid) return base;
  if (payload.ready !== (payload.selector_resolved === true && payload.profile_current === true)) {
    return { valid: false, errors: ["readiness_mismatch"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQModelAssistRequest(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_ASSIST_REQUEST_SCHEMA_ID, root);
  if (!base.valid) return base;
  if (!claimedHash(payload, "request_sha256")) return { valid: false, errors: ["request_hash"] };
  if (Date.parse(String(payload.expires_at)) <= Date.parse(String(payload.created_at))) {
    return { valid: false, errors: ["expiry"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQModelAssistContext(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_ASSIST_CONTEXT_SCHEMA_ID, root);
  return base.valid && claimedHash(payload, "context_sha256")
    ? base : { valid: false, errors: ["context_hash"] };
}

function tokenTotals(block: unknown): boolean {
  if (block === null || typeof block !== "object") return false;
  const value = block as JsonObject;
  return value.total_tokens === Number(value.input_tokens) + Number(value.output_tokens);
}

export function validateQQModelCaseBudget(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_CASE_BUDGET_SCHEMA_ID, root);
  if (!base.valid || !tokenTotals(payload.reserved) || !tokenTotals(payload.used) ||
      !claimedHash(payload, "budget_sha256")) return { valid: false, errors: ["budget"] };
  const reserved = payload.reserved as JsonObject;
  const used = payload.used as JsonObject;
  if (Object.keys(used).some((field) => Number(used[field]) > Number(reserved[field]))) {
    return { valid: false, errors: ["budget_exceeded"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQModelInvocationEvidence(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_INVOCATION_EVIDENCE_SCHEMA_ID, root);
  if (!base.valid || !tokenTotals(payload.reservation) || !tokenTotals(payload.usage) ||
      !claimedHash(payload, "evidence_sha256")) return { valid: false, errors: ["invocation"] };
  const intentOnly = payload.status === "intent_recorded";
  if (intentOnly !== (payload.observation_id === null && payload.observed_at === null)) {
    return { valid: false, errors: ["observation_state"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQModelCandidateBinding(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_CANDIDATE_BINDING_SCHEMA_ID, root);
  return base.valid && claimedHash(payload, "binding_sha256")
    ? base : { valid: false, errors: ["binding_hash"] };
}

export function validateQQModelPrivatePreview(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_PRIVATE_PREVIEW_SCHEMA_ID, root);
  if (!base.valid || !String(payload.candidate_sha256).startsWith(String(payload.candidate_hash_prefix)) ||
      !claimedHash(payload, "preview_sha256")) return { valid: false, errors: ["preview"] };
  return { valid: true, errors: [] };
}

export function validateQQModelAssistOutcome(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_ASSIST_OUTCOME_SCHEMA_ID, root);
  if (!base.valid || !claimedHash(payload, "outcome_sha256")) {
    return { valid: false, errors: ["outcome"] };
  }
  const ready = payload.terminal_outcome === "response_ready";
  if (ready !== (typeof payload.candidate_binding_id === "string" &&
                 typeof payload.private_preview_id === "string")) {
    return { valid: false, errors: ["candidate_outcome"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQModelWorkflowAcceptanceReport(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_WORKFLOW_ACCEPTANCE_REPORT_SCHEMA_ID, root);
  if (!base.valid || !claimedHash(payload, "report_sha256") || !safeTree(payload)) {
    return { valid: false, errors: ["report_integrity"] };
  }
  if (["customer_receipt_verified", "issue_resolution", "case_completion", "production_ready"]
      .some((field) => payload[field] !== false)) {
    return { valid: false, errors: ["business_outcome_overclaim"] };
  }
  const usage = payload.model_usage as JsonObject;
  if (!tokenTotals(usage)) return { valid: false, errors: ["usage_total"] };
  if (payload.mode === "offline-fake") {
    if (payload.live_model_contact_verified !== false || usage.available !== false) {
      return { valid: false, errors: ["fake_as_live"] };
    }
  } else {
    const required = ["qq_intake_ack_verified", "handler_private_workflow_verified",
      "live_model_contact_verified", "candidate_verification_verified", "group_approval_verified",
      "final_provider_accepted", "artifact_deletion_verified"];
    if (!required.every((field) => payload[field] === true) || usage.available !== true) {
      return { valid: false, errors: ["live_evidence_incomplete"] };
    }
  }
  return { valid: true, errors: [] };
}

export function validateQQModelWorkflowVerification(
  payload: JsonObject,
  root?: string,
): QQModelValidation {
  const base = schema(payload, QQ_MODEL_WORKFLOW_VERIFICATION_SCHEMA_ID, root);
  return base.valid && claimedHash(payload, "verification_sha256")
    ? base : { valid: false, errors: ["verification_hash"] };
}

export function validateQQModelLineage(records: JsonObject[], root?: string): QQModelValidation {
  if (records.length !== 7) return { valid: false, errors: ["record_count"] };
  const [request, context, budget, invocation, binding, preview, outcome] = records;
  const validators = [validateQQModelAssistRequest, validateQQModelAssistContext,
    validateQQModelCaseBudget, validateQQModelInvocationEvidence, validateQQModelCandidateBinding,
    validateQQModelPrivatePreview, validateQQModelAssistOutcome];
  if (records.some((record, index) => !validators[index](record, root).valid)) {
    return { valid: false, errors: ["record_invalid"] };
  }
  const common = ["tenant_id", "case_id", "case_revision_id", "handler_binding_id"];
  if (records.slice(1).some((record) => common.some((field) => record[field] !== request[field]) ||
      record.assist_request_id !== request.assist_request_id)) {
    return { valid: false, errors: ["lineage_mismatch"] };
  }
  if (invocation.context_id !== context.context_id || invocation.context_sha256 !== context.context_sha256 ||
      binding.context_id !== context.context_id || binding.invocation_id !== invocation.invocation_id ||
      binding.invocation_evidence_sha256 !== invocation.evidence_sha256 ||
      binding.budget_sha256 !== budget.budget_sha256 || preview.budget_sha256 !== budget.budget_sha256 ||
      preview.candidate_artifact_id !== binding.candidate_artifact_id ||
      preview.approval_request_id !== binding.approval_request_id ||
      outcome.candidate_binding_id !== binding.binding_id || outcome.private_preview_id !== preview.preview_id) {
    return { valid: false, errors: ["lineage_link"] };
  }
  return { valid: true, errors: [] };
}
