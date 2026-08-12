import { createHash } from "node:crypto";

import { JsonObject, canonicalJson, validatePayload } from "./index.js";

const BASE = "https://weflow.local/contracts/v1";
export const QQ_HANDLER_PAIRING_CHALLENGE_SCHEMA_ID = `${BASE}/qq-handler-pairing-challenge.schema.json`;
export const QQ_HANDLER_BINDING_SCHEMA_ID = `${BASE}/qq-handler-binding.schema.json`;
export const QQ_HANDLER_PRIVATE_LOCATOR_SCHEMA_ID = `${BASE}/qq-handler-private-locator.schema.json`;
export const QQ_CUSTOMER_ISSUE_ARTIFACT_SCHEMA_ID = `${BASE}/qq-customer-issue-artifact.schema.json`;
export const QQ_HANDLER_RESPONSE_ARTIFACT_SCHEMA_ID = `${BASE}/qq-handler-response-artifact.schema.json`;
export const QQ_HANDLER_COMMAND_SCHEMA_ID = `${BASE}/qq-handler-command.schema.json`;
export const QQ_HANDLER_NOTIFICATION_INTENT_SCHEMA_ID = `${BASE}/qq-handler-notification-intent.schema.json`;
export const QQ_HANDLER_NOTIFICATION_RESULT_SCHEMA_ID = `${BASE}/qq-handler-notification-result.schema.json`;
export const QQ_HANDLER_CANDIDATE_REVISION_SCHEMA_ID = `${BASE}/qq-handler-candidate-revision.schema.json`;
export const QQ_HANDLER_APPROVAL_REQUEST_SCHEMA_ID = `${BASE}/qq-handler-approval-request.schema.json`;
export const QQ_HANDLER_APPROVAL_DECISION_SCHEMA_ID = `${BASE}/qq-handler-approval-decision.schema.json`;
export const QQ_HANDLER_PASSIVE_REPLY_INTENT_SCHEMA_ID = `${BASE}/qq-handler-passive-reply-intent.schema.json`;
export const QQ_HANDLER_PASSIVE_REPLY_RESULT_SCHEMA_ID = `${BASE}/qq-handler-passive-reply-result.schema.json`;
export const QQ_HANDLER_ACCEPTANCE_REPORT_SCHEMA_ID = `${BASE}/qq-handler-acceptance-report.schema.json`;

export interface QQHandlerBinding extends JsonObject {
  schema_id: typeof QQ_HANDLER_BINDING_SCHEMA_ID;
  handler_binding_id: string;
  group_member_identity_hash: string;
  c2c_user_identity_hash: string;
  assurance_level: "operator_confirmed_dual_challenge" | "provider_cross_surface_verified";
  status: "ACTIVE" | "REVOKED" | "EXPIRED" | "CONFLICT";
}

export interface QQHandlerCommand extends JsonObject {
  schema_id: typeof QQ_HANDLER_COMMAND_SCHEMA_ID;
  surface: "c2c" | "group";
  command: "pull" | "accept" | "draft" | "reject" | "approve";
  expected_version: number;
}

export interface QQHandlerAcceptanceReport extends JsonObject {
  schema_id: typeof QQ_HANDLER_ACCEPTANCE_REPORT_SCHEMA_ID;
  mode: "offline-fake" | "readiness" | "qq-sandbox-live";
  report_sha256: string;
}

export type Validation = { valid: boolean; errors: string[] };

function schema(payload: JsonObject, expected: string, root?: string): Validation {
  if (payload.schema_id !== expected) return { valid: false, errors: ["unexpected_schema"] };
  const result = validatePayload(payload, root);
  return result.valid ? { valid: true, errors: [] } : { valid: false, errors: ["schema"] };
}

function timestamp(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function validateQQHandlerArtifact(payload: JsonObject, root?: string): Validation {
  const expected = payload.artifact_kind === "qq_customer_issue"
    ? QQ_CUSTOMER_ISSUE_ARTIFACT_SCHEMA_ID
    : QQ_HANDLER_RESPONSE_ARTIFACT_SCHEMA_ID;
  const base = schema(payload, expected, root);
  if (!base.valid) return base;
  const created = timestamp(payload.created_at);
  const expires = timestamp(payload.expires_at);
  if (created === null || expires === null || expires <= created || expires - created > 86_400_000) {
    return { valid: false, errors: ["retention_invalid"] };
  }
  if ((payload.deletion_status === "DELETED") !== (payload.deleted_at !== null)) {
    return { valid: false, errors: ["deletion_state_invalid"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQHandlerCommand(payload: JsonObject, root?: string): Validation {
  const base = schema(payload, QQ_HANDLER_COMMAND_SCHEMA_ID, root);
  if (!base.valid) return base;
  const c2c = new Set(["pull", "accept", "draft", "reject"]);
  const group = new Set(["approve"]);
  if ((payload.surface === "c2c" && !c2c.has(String(payload.command))) ||
      (payload.surface === "group" && !group.has(String(payload.command)))) {
    return { valid: false, errors: ["command_surface_mismatch"] };
  }
  if ((payload.command === "reject") !== (typeof payload.rejection_reason_code === "string")) {
    return { valid: false, errors: ["rejection_reason_mismatch"] };
  }
  if (payload.command !== "reject" && payload.rejection_reason_code !== null) {
    return { valid: false, errors: ["rejection_reason_mismatch"] };
  }
  if (payload.command === "draft" && payload.candidate_artifact_id === null) {
    return { valid: false, errors: ["candidate_artifact_missing"] };
  }
  if (payload.command === "approve" &&
      (payload.approval_request_id === null || payload.candidate_hash_prefix === null)) {
    return { valid: false, errors: ["approval_metadata_missing"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQHandlerNotificationChain(
  intent: JsonObject,
  results: JsonObject[],
  root?: string,
): Validation {
  if (!schema(intent, QQ_HANDLER_NOTIFICATION_INTENT_SCHEMA_ID, root).valid) {
    return { valid: false, errors: ["intent_schema"] };
  }
  if (results.length > 1) return { valid: false, errors: ["multiple_attempts_forbidden"] };
  for (const result of results) {
    if (!schema(result, QQ_HANDLER_NOTIFICATION_RESULT_SCHEMA_ID, root).valid) {
      return { valid: false, errors: ["result_schema"] };
    }
    if (result.intent_id !== intent.intent_id || result.tenant_id !== intent.tenant_id) {
      return { valid: false, errors: ["result_link_mismatch"] };
    }
    if (result.provider_accepted !== (result.status === "accepted")) {
      return { valid: false, errors: ["acceptance_mismatch"] };
    }
  }
  return { valid: true, errors: [] };
}

export function validateQQHandlerApprovalChain(
  request: JsonObject,
  decisions: JsonObject[],
  root?: string,
): Validation {
  if (!schema(request, QQ_HANDLER_APPROVAL_REQUEST_SCHEMA_ID, root).valid) {
    return { valid: false, errors: ["request_schema"] };
  }
  if (!String(request.candidate_sha256).startsWith(String(request.candidate_hash_prefix))) {
    return { valid: false, errors: ["hash_prefix_mismatch"] };
  }
  if (decisions.length > 1) return { valid: false, errors: ["duplicate_decision"] };
  const links = ["approval_request_id", "tenant_id", "case_id", "case_revision_id",
    "handler_binding_id", "candidate_revision_id", "candidate_sha256", "workflow_version"];
  for (const decision of decisions) {
    if (!schema(decision, QQ_HANDLER_APPROVAL_DECISION_SCHEMA_ID, root).valid) {
      return { valid: false, errors: ["decision_schema"] };
    }
    if (links.some((field) => decision[field] !== request[field])) {
      return { valid: false, errors: ["decision_link_mismatch"] };
    }
  }
  return { valid: true, errors: [] };
}

export function validateQQHandlerPassiveReplyChain(
  intent: JsonObject,
  results: JsonObject[],
  root?: string,
): Validation {
  if (!schema(intent, QQ_HANDLER_PASSIVE_REPLY_INTENT_SCHEMA_ID, root).valid) {
    return { valid: false, errors: ["intent_schema"] };
  }
  const expectedShapes: Record<string, [string, string, number]> = {
    pull: ["c2c", "qq.c2c.passive_reply.execute", 1],
    accept: ["c2c", "qq.c2c.passive_reply.execute", 2],
    "draft-preview": ["c2c", "qq.c2c.passive_reply.execute", 3],
    reject: ["c2c", "qq.c2c.passive_reply.execute", 4],
    "group-nudge": ["group", "qq.final_reply.execute", 2],
    final: ["group", "qq.final_reply.execute", 5],
  };
  const expected = expectedShapes[String(intent.response_kind)];
  const actual = [String(intent.surface), String(intent.operation), Number(intent.reply_msg_seq)];
  if (!expected || actual.some((value, index) => value !== expected[index])) {
    return { valid: false, errors: ["response_shape_mismatch"] };
  }
  if (results.length > 1) return { valid: false, errors: ["duplicate_result"] };
  for (const result of results) {
    if (!schema(result, QQ_HANDLER_PASSIVE_REPLY_RESULT_SCHEMA_ID, root).valid) {
      return { valid: false, errors: ["result_schema"] };
    }
    if (result.intent_id !== intent.intent_id || result.tenant_id !== intent.tenant_id) {
      return { valid: false, errors: ["result_link_mismatch"] };
    }
    if (result.provider_accepted !== ["accepted", "duplicate"].includes(String(result.status))) {
      return { valid: false, errors: ["acceptance_mismatch"] };
    }
  }
  return { valid: true, errors: [] };
}

const forbiddenReportKeys = new Set([
  "member_openid", "user_openid", "group_openid", "client_secret", "access_token",
  "raw_event", "provider_response", "customer_issue", "candidate_text", "draft_preview", "transcript",
]);

function containsForbiddenKey(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenKey);
  if (value !== null && typeof value === "object") {
    return Object.entries(value).some(([key, child]) =>
      forbiddenReportKeys.has(key.toLowerCase()) || containsForbiddenKey(child));
  }
  return false;
}

export function validateQQHandlerAcceptanceReport(report: JsonObject, root?: string): Validation {
  const base = schema(report, QQ_HANDLER_ACCEPTANCE_REPORT_SCHEMA_ID, root);
  if (!base.valid) return base;
  const material = { ...report };
  delete material.report_sha256;
  const hash = createHash("sha256").update(canonicalJson(material)).digest("hex");
  if (report.report_sha256 !== hash) return { valid: false, errors: ["report_hash_mismatch"] };
  if (["model_invocation", "customer_receipt_verified", "issue_resolution", "case_completion", "production_ready"]
    .some((field) => report[field] !== false)) {
    return { valid: false, errors: ["acceptance_overclaim"] };
  }
  if (containsForbiddenKey(report)) return { valid: false, errors: ["unsafe_report_key"] };
  return { valid: true, errors: [] };
}
