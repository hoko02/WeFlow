import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { Ajv2020 } from "ajv/dist/2020.js";

export type JsonObject = Record<string, unknown>;
export const BUSINESS_EVENT_SCHEMA_ID = "https://weflow.local/contracts/v1/business-event.schema.json";
export const CASE_PROJECTION_SCHEMA_ID = "https://weflow.local/contracts/v1/case-projection.schema.json";
export const INBOUND_MESSAGE_EVENT_SCHEMA_ID = "https://weflow.local/contracts/v1/inbound-message-event.schema.json";
export const SIDE_EFFECT_COMPLETION_SCHEMA_ID = "https://weflow.local/contracts/v1/side-effect-completion.schema.json";
export const SIDE_EFFECT_INTENT_SCHEMA_ID = "https://weflow.local/contracts/v1/side-effect-intent.schema.json";
export const SIDE_EFFECT_OBSERVATION_SCHEMA_ID = "https://weflow.local/contracts/v1/side-effect-observation.schema.json";
export const SYNTHETIC_SLA_POLICY_SCHEMA_ID = "https://weflow.local/contracts/v1/synthetic-sla-policy.schema.json";
export const WORKFLOW_CHECKPOINT_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-checkpoint.schema.json";
export const WORKFLOW_COMMAND_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-command.schema.json";
export const WORKFLOW_PROJECTION_SCHEMA_ID = "https://weflow.local/contracts/v1/workflow-projection.schema.json";
export const CONTEXT_MANIFEST_SCHEMA_ID = "https://weflow.local/contracts/v1/context-manifest.schema.json";
export const AGENT_ACTION_SCHEMA_ID = "https://weflow.local/contracts/v1/agent-action.schema.json";
export const TOOL_REQUEST_SCHEMA_ID = "https://weflow.local/contracts/v1/tool-request.schema.json";
export const TOOL_RESULT_SCHEMA_ID = "https://weflow.local/contracts/v1/tool-result.schema.json";
export const RESPONSE_CANDIDATE_SCHEMA_ID = "https://weflow.local/contracts/v1/response-candidate.schema.json";
export const VERIFIER_OUTCOME_SCHEMA_ID = "https://weflow.local/contracts/v1/verifier-outcome.schema.json";export const AUTHORIZATION_BINDING_SCHEMA_ID = "https://weflow.local/contracts/v1/authorization-binding.schema.json";
export const CAPABILITY_GRANT_SCHEMA_ID = "https://weflow.local/contracts/v1/capability-grant.schema.json";
export const POLICY_DECISION_SCHEMA_ID = "https://weflow.local/contracts/v1/policy-decision.schema.json";
export const APPROVAL_REQUEST_SCHEMA_ID = "https://weflow.local/contracts/v1/approval-request.schema.json";
export const APPROVAL_DECISION_SCHEMA_ID = "https://weflow.local/contracts/v1/approval-decision.schema.json";
export const OUTBOUND_DELIVERY_INTENT_SCHEMA_ID = "https://weflow.local/contracts/v1/outbound-delivery-intent.schema.json";
export const OUTBOUND_DELIVERY_OBSERVATION_SCHEMA_ID = "https://weflow.local/contracts/v1/outbound-delivery-observation.schema.json";
export const OUTBOUND_DELIVERY_COMPLETION_SCHEMA_ID = "https://weflow.local/contracts/v1/outbound-delivery-completion.schema.json";

export type AgentActionType =
  | "read_crm"
  | "read_monitoring"
  | "read_knowledge"
  | "needs_information"
  | "needs_operator"
  | "response_candidate";

export interface ContextManifest extends JsonObject {
  schema_id: typeof CONTEXT_MANIFEST_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  context_manifest_id: string;
  context_sha256: string;
  environment_snapshot_sha256: string;
  evidence_references: string[];
  action_budget: number;
  tool_budget: number;
  no_progress_limit: number;
  created_at: string;
}

export interface AgentAction extends JsonObject {
  schema_id: typeof AGENT_ACTION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  context_manifest_id: string;
  step_id: string;
  action_type: AgentActionType;
  action_sha256: string;
  created_at: string;
}

export interface ToolRequest extends JsonObject {
  schema_id: typeof TOOL_REQUEST_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  context_manifest_id: string;
  tool_request_id: string;
  step_id: string;
  tool_name: "crm" | "monitoring" | "knowledge";
  request_sha256: string;
  created_at: string;
}

export interface ToolResult extends JsonObject {
  schema_id: typeof TOOL_RESULT_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  context_manifest_id: string;
  tool_name: "crm" | "monitoring" | "knowledge";
  tool_result_id: string;
  tool_request_id: string;
  evidence_id: string;
  content_sha256: string;
  redaction_classification: "synthetic";
  recorded_at: string;
}

export interface ResponseCandidate extends JsonObject {
  schema_id: typeof RESPONSE_CANDIDATE_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  context_manifest_id: string;
  candidate_id: string;
  context_sha256: string;
  evidence_hashes: string[];
  candidate_sha256: string;
  risk: "low" | "medium" | "high";
  next_step: "operator_review" | "awaiting_information";
  created_at: string;
}

export interface VerifierOutcome extends JsonObject {
  schema_id: typeof VERIFIER_OUTCOME_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  context_manifest_id: string;
  verifier_outcome_id: string;
  candidate_id: string;
  candidate_sha256: string;
  outcome: "verified" | "rejected";
  reason_code: string;
  recorded_at: string;
}

export interface InboundMessageEvent extends JsonObject {
  schema_id: typeof INBOUND_MESSAGE_EVENT_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  channel: "synthetic-im";
  channel_event_id: string;
  conversation_id: string;
  sender_id: string;
  customer_id: string;
  conversation_sequence: number;
  occurred_at: string;
  received_at: string;
  correlation_id: string;
  content_classification: "synthetic";
  content_sha256: string;
}

export interface CaseProjection extends JsonObject {
  schema_id: typeof CASE_PROJECTION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  latest_case_revision_id: string;
  latest_revision: number;
  state: string;
  source_event_id: string;
  event_count: number;
  correlation_id: string;
  created_at: string;
  updated_at: string;
}

export type WorkflowState =
  | "RECEIVED"
  | "TICKET_READY"
  | "INVESTIGATING"
  | "RESPONSE_READY"
  | "AWAITING_APPROVAL"
  | "DELIVERING"
  | "DELIVERY_RECORDED"
  | "PAUSED"
  | "WAITING_FOR_OPERATOR"
  | "NEEDS_RECONCILIATION"
  | "CANCELLED";

export interface WorkflowProjection extends JsonObject {
  schema_id: typeof WORKFLOW_PROJECTION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  workflow_definition_version: string;
  state: WorkflowState;
  run_status: "active" | "paused" | "blocked" | "cancelled";
  workflow_version: number;
  latest_checkpoint_id: string;
  latest_checkpoint_sequence: number;
  sla_deadline_at: string;
  correlation_id: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowCheckpoint extends JsonObject {
  schema_id: typeof WORKFLOW_CHECKPOINT_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  workflow_definition_version: string;
  checkpoint_id: string;
  checkpoint_sequence: number;
  previous_checkpoint_id: string | null;
  current_state: WorkflowState;
  resume_state: Exclude<WorkflowState, "PAUSED">;
  workflow_version: number;
  sla_deadline_at: string;
  pending_intent_ids: string[];
  completed_intent_ids: string[];
  causation_event_id: string | null;
  correlation_id: string;
  content_sha256: string;
  created_at: string;
}

export interface WorkflowCommand extends JsonObject {
  schema_id: typeof WORKFLOW_COMMAND_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  command_id: string;
  command_type: "pause" | "resume" | "cancel";
  expected_workflow_version: number;
  command_payload_sha256: string;
  requested_at: string;
}

export interface SyntheticSlaPolicy extends JsonObject {
  schema_id: typeof SYNTHETIC_SLA_POLICY_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  policy_id: string;
  policy_version: string;
  deadline_seconds: number;
  created_at: string;
}

export interface SideEffectIntent extends JsonObject {
  schema_id: typeof SIDE_EFFECT_INTENT_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  intent_id: string;
  effect_kind: "fixture-local-ticket";
  operation: "find-or-create" | "workflow-handoff";
  natural_key: string;
  intended_state_hash: string;
  idempotency_key: string;
  evidence_references: string[];
  correlation_id: string;
  created_at: string;
}

export interface SideEffectObservation extends JsonObject {
  schema_id: typeof SIDE_EFFECT_OBSERVATION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  observation_id: string;
  intent_id: string;
  status: "absent" | "present" | "unknown" | "conflict";
  observed_ticket_id: string | null;
  observed_version: number | null;
  outcome_sha256: string | null;
  reason_code: string | null;
  recorded_at: string;
}

export interface SideEffectCompletion extends JsonObject {
  schema_id: typeof SIDE_EFFECT_COMPLETION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  completion_id: string;
  intent_id: string;
  observation_id: string;
  observed_ticket_id: string;
  observed_version: number;
  result_sha256: string;
  completed_at: string;
}

export type Change4Action =
  | "approval.request"
  | "approval.decide"
  | "outbound_delivery.execute";

export interface AuthorizationBinding extends JsonObject {
  schema_id: typeof AUTHORIZATION_BINDING_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  authorization_binding_id: string;
  authorization_binding_sha256: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  workflow_version: number;
  candidate_hash: string;
  evidence_hashes: string[];
  action: Change4Action;
  policy_decision_id: string;
  policy_version: string;
  policy_decision_sha256: string;
  grant_id: string;
  grant_version: string;
  grant_sha256: string;
  subject_id: string;
  role: string;
  delivery_resource_id: string;
  delivery_resource_scope: string;
  data_classification: "synthetic" | "unsafe_instruction" | "secret" | "raw_private";
  remaining_budget: number;
  expires_at: string;
  created_at: string;
}

export interface CapabilityGrant extends JsonObject {
  schema_id: typeof CAPABILITY_GRANT_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  grant_id: string;
  subject_id: string;
  capability: string;
  scopes: string[];
  issued_at: string;
  expires_at: string;
  status: "active" | "revoked" | "expired";
  grant_version?: string;
  grant_sha256?: string;
  role?: string;
  resource_scope?: string;
  data_classifications?: string[];
}

export interface PolicyDecision extends JsonObject {
  schema_id: typeof POLICY_DECISION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  policy_decision_id: string;
  case_id: string;
  case_revision_id: string;
  decision: "allow" | "deny";
  reason_code: string;
  evidence_hashes: string[];
  decided_at: string;
}

export interface OutboundDeliveryIntent extends JsonObject {
  schema_id: typeof OUTBOUND_DELIVERY_INTENT_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  intent_id: string;
  effect_kind: "fixture-local-outbound-delivery";
  operation: "deliver";
  channel: "fixture-local-im";
  conversation_id: string;
  delivery_resource_id: string;
  candidate_hash: string;
  authorization_binding_sha256: string;
  natural_key: string;
  intended_state_hash: string;
  idempotency_key: string;
  evidence_hashes: string[];
  correlation_id: string;
  created_at: string;
}

export interface OutboundDeliveryObservation extends JsonObject {
  schema_id: typeof OUTBOUND_DELIVERY_OBSERVATION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  observation_id: string;
  intent_id: string;
  status: "absent" | "present" | "unknown" | "conflict";
  observed_delivery_id: string | null;
  observed_version: number | null;
  content_sha256: string | null;
  reason_code: string | null;
  recorded_at: string;
}

export interface OutboundDeliveryCompletion extends JsonObject {
  schema_id: typeof OUTBOUND_DELIVERY_COMPLETION_SCHEMA_ID;
  schema_version: "v1";
  tenant_id: string;
  case_id: string;
  case_revision_id: string;
  workflow_id: string;
  checkpoint_id: string;
  completion_id: string;
  intent_id: string;
  observation_id: string;
  observed_delivery_id: string;
  observed_version: number;
  content_sha256: string;
  completed_at: string;
}
export interface ValidationResult {
  valid: boolean;
  reasonCode?: string;
}

function findRepositoryRoot(start = process.cwd()): string {
  let current = resolve(start);
  while (true) {
    if (existsSync(resolve(current, "pyproject.toml")) && existsSync(resolve(current, "contracts/jsonschema/v1"))) {
      return current;
    }
    const parent = resolve(current, "..");
    if (parent === current) {
      throw new Error("WeFlow repository root could not be located");
    }
    current = parent;
  }
}

function schemaDirectory(root = findRepositoryRoot()): string {
  return resolve(root, "contracts/jsonschema/v1");
}

function readJson(path: string): JsonObject {
  return JSON.parse(readFileSync(path, "utf8")) as JsonObject;
}

export function loadContractSchemas(root?: string): Map<string, JsonObject> {
  const schemas = new Map<string, JsonObject>();
  for (const filename of readdirSync(schemaDirectory(root)).filter((name) => name.endsWith(".schema.json")).sort()) {
    const schema = readJson(resolve(schemaDirectory(root), filename));
    const schemaId = schema.$id;
    if (typeof schemaId !== "string" || schemaId.length === 0) {
      throw new Error(`Schema has no stable identifier: ${filename}`);
    }
    schemas.set(schemaId, schema);
  }
  return schemas;
}

export function validatePayload(payload: JsonObject, root?: string): ValidationResult {
  const schemaId = payload.schema_id;
  if (typeof schemaId !== "string" || schemaId.length === 0) {
    return { valid: false, reasonCode: "missing_schema_id" };
  }

  const schemas = loadContractSchemas(root);
  const schema = schemas.get(schemaId);
  if (!schema) {
    return { valid: false, reasonCode: "schema_not_found" };
  }

  const ajv = new Ajv2020({ allErrors: true, strict: true });
  for (const item of schemas.values()) {
    ajv.addSchema(item);
  }
  const validator = ajv.getSchema(schemaId);
  if (!validator) {
    return { valid: false, reasonCode: "schema_not_compiled" };
  }
  if (validator(payload)) {
    return { valid: true };
  }

  const firstError = validator.errors?.[0];
  const path = firstError?.instancePath?.replace(/^\//, "").replaceAll("/", ".") || "root";
  return { valid: false, reasonCode: `${path}:${firstError?.keyword ?? "validation"}` };
}

function validateExpectedSchema(
  payload: JsonObject,
  schemaId: string,
  root?: string,
): ValidationResult {
  const result = validatePayload(payload, root);
  if (!result.valid) {
    return result;
  }
  return payload.schema_id === schemaId ? { valid: true } : { valid: false, reasonCode: "unexpected_schema" };
}

export function validateContextManifest(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, CONTEXT_MANIFEST_SCHEMA_ID, root);
}

export function validateAgentAction(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, AGENT_ACTION_SCHEMA_ID, root);
}

export function validateToolRequest(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, TOOL_REQUEST_SCHEMA_ID, root);
}

export function validateToolResult(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, TOOL_RESULT_SCHEMA_ID, root);
}

export function validateResponseCandidate(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, RESPONSE_CANDIDATE_SCHEMA_ID, root);
}

export function validateVerifierOutcome(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, VERIFIER_OUTCOME_SCHEMA_ID, root);
}

function requireChange4Fields(payload: JsonObject, fields: string[]): ValidationResult {
  for (const field of fields) {
    const value = payload[field];
    if (value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
      return { valid: false, reasonCode: `${field}_required` };
    }
  }
  return { valid: true };
}

function change4Same(left: JsonObject, right: JsonObject, fields: string[]): ValidationResult {
  for (const field of fields) {
    if (left[field] !== right[field]) {
      return { valid: false, reasonCode: field === "tenant_id" ? "tenant_identity_mismatch" : "binding_mismatch" };
    }
  }
  return { valid: true };
}

function change4OrderedEqual(left: unknown, right: unknown): boolean {
  return Array.isArray(left) && Array.isArray(right) && canonicalJson(left) === canonicalJson(right);
}

export function change4ContentHash(payload: JsonObject, hashField: string): string {
  const material = { ...payload };
  delete material[hashField];
  return createHash("sha256").update(canonicalJson(material), "utf8").digest("hex");
}

function change4ClaimedHash(payload: JsonObject, hashField: string): ValidationResult {
  return payload[hashField] === change4ContentHash(payload, hashField)
    ? { valid: true }
    : { valid: false, reasonCode: `${hashField}_mismatch` };
}

export function validateCapabilityGrant(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, CAPABILITY_GRANT_SCHEMA_ID, root);
}

export function validatePolicyDecision(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, POLICY_DECISION_SCHEMA_ID, root);
}

export function validateApprovalRequest(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, APPROVAL_REQUEST_SCHEMA_ID, root);
}

export function validateApprovalDecision(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, APPROVAL_DECISION_SCHEMA_ID, root);
}

export function validateAuthorizationBinding(payload: JsonObject, root?: string): ValidationResult {
  const schema = validateExpectedSchema(payload, AUTHORIZATION_BINDING_SCHEMA_ID, root);
  if (!schema.valid) {
    return schema;
  }
  const hash = change4ClaimedHash(payload, "authorization_binding_sha256");
  if (!hash.valid) {
    return hash;
  }
  const evidence = payload.evidence_hashes;
  return Array.isArray(evidence) && evidence.length === new Set(evidence).size
    ? { valid: true }
    : { valid: false, reasonCode: "evidence_not_ordered_unique" };
}

export function validateOutboundDeliveryIntent(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, OUTBOUND_DELIVERY_INTENT_SCHEMA_ID, root);
}

export function validateOutboundDeliveryObservation(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, OUTBOUND_DELIVERY_OBSERVATION_SCHEMA_ID, root);
}

export function validateOutboundDeliveryCompletion(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, OUTBOUND_DELIVERY_COMPLETION_SCHEMA_ID, root);
}

export interface Change4AuthorizationContext {
  action: Change4Action;
  currentCaseRevisionId: string;
  currentCheckpointId: string;
  currentWorkflowVersion: number;
  currentCandidateHash: string;
  currentEvidenceHashes: string[];
  resourceId: string;
  dataClassification: string;
  effectiveTenantId?: string;
  effectiveSubjectId?: string;
  effectiveRole?: string;
  now?: string;
}

export function validateChange4AuthorizationProfile(
  binding: JsonObject,
  grant: JsonObject,
  decision: JsonObject,
  context: Change4AuthorizationContext,
  root?: string,
): ValidationResult {
  if (!["approval.request", "approval.decide", "outbound_delivery.execute"].includes(context.action)) {
    return { valid: false, reasonCode: "action_not_allowlisted" };
  }
  for (const result of [validateAuthorizationBinding(binding, root), validateCapabilityGrant(grant, root), validatePolicyDecision(decision, root)]) {
    if (!result.valid) {
      return result;
    }
  }
  const requiredGrant = requireChange4Fields(grant, ["grant_version", "grant_sha256", "role", "resource_scope", "data_classifications"]);
  if (!requiredGrant.valid) {
    return requiredGrant;
  }
  const grantHash = change4ClaimedHash(grant, "grant_sha256");
  if (!grantHash.valid) {
    return grantHash;
  }
  const requiredDecision = requireChange4Fields(decision, ["checkpoint_id", "workflow_id", "workflow_version", "candidate_hash", "action", "policy_version", "policy_input_sha256", "policy_decision_sha256", "grant_id", "grant_sha256", "subject_id", "role", "resource_id", "data_classification"]);
  if (!requiredDecision.valid) {
    return requiredDecision;
  }
  const decisionHash = change4ClaimedHash(decision, "policy_decision_sha256");
  if (!decisionHash.valid) {
    return decisionHash;
  }
  if (decision.decision !== "allow") {
    return { valid: false, reasonCode: "policy_denied" };
  }
  const current = Date.parse(context.now ?? new Date().toISOString());
  if (
    grant.status !== "active" ||
    Date.parse(String(grant.expires_at)) <= current ||
    Date.parse(String(binding.expires_at)) <= current ||
    !Array.isArray(grant.scopes) ||
    !grant.scopes.includes(context.action) ||
    grant.resource_scope !== context.resourceId ||
    !Array.isArray(grant.data_classifications) ||
    !grant.data_classifications.includes(context.dataClassification) ||
    context.dataClassification !== "synthetic"
  ) {
    return { valid: false, reasonCode: "grant_scope_denied" };
  }
  for (const result of [
    change4Same(binding, grant, ["tenant_id", "grant_id", "grant_version", "grant_sha256", "subject_id", "role"]),
    change4Same(binding, decision, ["tenant_id", "case_id", "case_revision_id", "workflow_id", "checkpoint_id", "workflow_version", "candidate_hash", "policy_decision_id", "policy_version", "policy_decision_sha256", "grant_id", "grant_sha256", "subject_id", "role"]),
  ]) {
    if (!result.valid) {
      return result;
    }
  }
  if (
    !change4OrderedEqual(binding.evidence_hashes, decision.evidence_hashes) ||
    binding.action !== context.action || decision.action !== context.action ||
    binding.delivery_resource_id !== context.resourceId || decision.resource_id !== context.resourceId ||
    binding.data_classification !== context.dataClassification || decision.data_classification !== context.dataClassification ||
    binding.case_revision_id !== context.currentCaseRevisionId || binding.checkpoint_id !== context.currentCheckpointId ||
    binding.workflow_version !== context.currentWorkflowVersion || binding.candidate_hash !== context.currentCandidateHash ||
    !change4OrderedEqual(binding.evidence_hashes, context.currentEvidenceHashes)
  ) {
    return { valid: false, reasonCode: "binding_mismatch" };
  }
  if (context.effectiveTenantId !== undefined && binding.tenant_id !== context.effectiveTenantId) {
    return { valid: false, reasonCode: "tenant_identity_mismatch" };
  }
  if (context.effectiveSubjectId !== undefined && binding.subject_id !== context.effectiveSubjectId) {
    return { valid: false, reasonCode: "subject_identity_mismatch" };
  }
  if (context.effectiveRole !== undefined && binding.role !== context.effectiveRole) {
    return { valid: false, reasonCode: "role_identity_mismatch" };
  }
  return { valid: true };
}

export function validateHashBoundApproval(
  request: JsonObject,
  decision: JsonObject,
  binding: JsonObject,
  context: Omit<Change4AuthorizationContext, "action" | "resourceId" | "dataClassification"> & { effectiveApproverId: string; effectiveApproverRole: string },
  root?: string,
): ValidationResult {
  for (const result of [validateApprovalRequest(request, root), validateApprovalDecision(decision, root), validateAuthorizationBinding(binding, root)]) {
    if (!result.valid) {
      return result;
    }
  }
  const req = requireChange4Fields(request, ["workflow_id", "checkpoint_id", "workflow_version", "authorization_binding_sha256", "policy_decision_sha256", "policy_version", "grant_sha256"]);
  const dec = requireChange4Fields(decision, ["workflow_id", "checkpoint_id", "workflow_version", "authorization_binding_sha256", "approver_id", "approver_role", "decision_sha256"]);
  if (!req.valid || !dec.valid) {
    return !req.valid ? req : dec;
  }
  const hash = change4ClaimedHash(decision, "decision_sha256");
  if (!hash.valid || decision.decision !== "approved") {
    return !hash.valid ? hash : { valid: false, reasonCode: "approval_not_granted" };
  }
  const links = change4Same(request, decision, ["tenant_id", "approval_request_id", "case_id", "case_revision_id", "candidate_hash", "workflow_id", "checkpoint_id", "workflow_version", "authorization_binding_sha256"]);
  if (!links.valid || !change4OrderedEqual(request.evidence_hashes, decision.evidence_hashes)) {
    return links.valid ? { valid: false, reasonCode: "binding_mismatch" } : links;
  }
  if (
    request.authorization_binding_sha256 !== binding.authorization_binding_sha256 ||
    request.policy_decision_sha256 !== binding.policy_decision_sha256 || request.policy_version !== binding.policy_version || request.grant_sha256 !== binding.grant_sha256 ||
    decision.tenant_id !== context.effectiveTenantId || decision.approver_id !== context.effectiveApproverId || decision.approver_role !== context.effectiveApproverRole ||
    request.case_revision_id !== context.currentCaseRevisionId || request.checkpoint_id !== context.currentCheckpointId || request.workflow_version !== context.currentWorkflowVersion ||
    request.candidate_hash !== context.currentCandidateHash || !change4OrderedEqual(request.evidence_hashes, context.currentEvidenceHashes) ||
    Date.parse(String(decision.expires_at)) <= Date.parse(context.now ?? new Date().toISOString())
  ) {
    return { valid: false, reasonCode: "approval_stale_or_mismatched" };
  }
  return { valid: true };
}

export function validateOutboundDeliveryChain(intent: JsonObject, observations: JsonObject[], completions: JsonObject[], binding: JsonObject, root?: string): ValidationResult {
  for (const result of [validateOutboundDeliveryIntent(intent, root), validateAuthorizationBinding(binding, root)]) {
    if (!result.valid) {
      return result;
    }
  }
  if (intent.authorization_binding_sha256 !== binding.authorization_binding_sha256 || intent.candidate_hash !== binding.candidate_hash || !change4OrderedEqual(intent.evidence_hashes, binding.evidence_hashes)) {
    return { valid: false, reasonCode: "binding_mismatch" };
  }
  if (completions.length > 1) {
    return { valid: false, reasonCode: "multiple_completions" };
  }
  const observationIds = new Set<string>();
  for (const observation of observations) {
    const result = validateOutboundDeliveryObservation(observation, root);
    if (!result.valid) {
      return result;
    }
    const id = String(observation.observation_id);
    if (observationIds.has(id)) {
      return { valid: false, reasonCode: "duplicate_observation" };
    }
    observationIds.add(id);
    const links = change4Same(intent, observation, ["tenant_id", "case_id", "case_revision_id", "workflow_id", "checkpoint_id"]);
    if (!links.valid || observation.intent_id !== intent.intent_id) {
      return links.valid ? { valid: false, reasonCode: "intent_reference_mismatch" } : links;
    }
  }
  for (const completion of completions) {
    const result = validateOutboundDeliveryCompletion(completion, root);
    if (!result.valid) {
      return result;
    }
    const links = change4Same(intent, completion, ["tenant_id", "case_id", "case_revision_id", "workflow_id", "checkpoint_id"]);
    if (!links.valid || completion.intent_id !== intent.intent_id) {
      return links.valid ? { valid: false, reasonCode: "intent_reference_mismatch" } : links;
    }
    const observation = observations.find((item) => item.observation_id === completion.observation_id && item.status === "present");
    if (!observation) {
      return { valid: false, reasonCode: "completion_observation_missing" };
    }
    if (observation.observed_delivery_id !== completion.observed_delivery_id || observation.observed_version !== completion.observed_version || observation.content_sha256 !== completion.content_sha256) {
      return { valid: false, reasonCode: "completion_observation_mismatch" };
    }
  }
  return { valid: true };
}

const CONTEXT_LINK_FIELDS = [
  "tenant_id",
  "case_id",
  "case_revision_id",
  "workflow_id",
  "checkpoint_id",
  "context_manifest_id",
] as const;

export function validateAgentActionForContext(
  payload: JsonObject,
  contextManifest: JsonObject,
  root?: string,
): ValidationResult {
  const action = validateAgentAction(payload, root);
  if (!action.valid) {
    return action;
  }
  const manifest = validateContextManifest(contextManifest, root);
  if (!manifest.valid) {
    return manifest;
  }
  for (const field of CONTEXT_LINK_FIELDS) {
    if (payload[field] !== contextManifest[field]) {
      return { valid: false, reasonCode: field === "tenant_id" ? "tenant_identity_mismatch" : "causation_mismatch" };
    }
  }
  return { valid: true };
}

export function validateInboundMessageEvent(
  payload: JsonObject,
  root?: string,
): ValidationResult {
  return validateExpectedSchema(payload, INBOUND_MESSAGE_EVENT_SCHEMA_ID, root);
}

export function validateInboundTenantClaim(
  payload: JsonObject,
  effectiveTenantId: string,
  root?: string,
): ValidationResult {
  const result = validateInboundMessageEvent(payload, root);
  if (!result.valid) {
    return result;
  }
  return payload.tenant_id === effectiveTenantId
    ? { valid: true }
    : { valid: false, reasonCode: "tenant_identity_mismatch" };
}

export function validateCaseProjection(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, CASE_PROJECTION_SCHEMA_ID, root);
}

export function validateWorkflowProjection(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, WORKFLOW_PROJECTION_SCHEMA_ID, root);
}

export function validateWorkflowCheckpoint(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, WORKFLOW_CHECKPOINT_SCHEMA_ID, root);
}

export function validateWorkflowCommand(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, WORKFLOW_COMMAND_SCHEMA_ID, root);
}

export function validateWorkflowCommandTenant(
  payload: JsonObject,
  effectiveTenantId: string,
  root?: string,
): ValidationResult {
  const result = validateWorkflowCommand(payload, root);
  if (!result.valid) {
    return result;
  }
  return payload.tenant_id === effectiveTenantId
    ? { valid: true }
    : { valid: false, reasonCode: "tenant_identity_mismatch" };
}

export function validateWorkflowCommandVersion(
  payload: JsonObject,
  currentWorkflowVersion: number,
  root?: string,
): ValidationResult {
  const result = validateWorkflowCommand(payload, root);
  if (!result.valid) {
    return result;
  }
  return Number.isInteger(currentWorkflowVersion) &&
    currentWorkflowVersion >= 0 &&
    payload.expected_workflow_version === currentWorkflowVersion
    ? { valid: true }
    : { valid: false, reasonCode: "workflow_version_conflict" };
}

export function validateCheckpointSequence(
  payloads: JsonObject[],
  root?: string,
): ValidationResult {
  if (payloads.length === 0) {
    return { valid: false, reasonCode: "checkpoint_chain_empty" };
  }
  let expectedSequence = 1;
  let previousId: string | null = null;
  let identity: string | undefined;
  let previousVersion: number | undefined;
  let completedIds = new Set<string>();
  const checkpointIds = new Set<string>();
  for (const payload of payloads) {
    const result = validateWorkflowCheckpoint(payload, root);
    if (!result.valid) {
      return result;
    }
    const currentIdentity = [
      payload.tenant_id,
      payload.case_id,
      payload.case_revision_id,
      payload.workflow_id,
    ].join("\u0000");
    if (identity !== undefined && identity !== currentIdentity) {
      return { valid: false, reasonCode: "workflow_identity_mismatch" };
    }
    identity = currentIdentity;
    if (payload.checkpoint_sequence !== expectedSequence) {
      return { valid: false, reasonCode: "checkpoint_not_monotonic" };
    }
    if (payload.previous_checkpoint_id !== previousId) {
      return { valid: false, reasonCode: "checkpoint_predecessor_mismatch" };
    }
    const checkpointId = String(payload.checkpoint_id);
    if (checkpointIds.has(checkpointId)) {
      return { valid: false, reasonCode: "checkpoint_id_duplicate" };
    }
    checkpointIds.add(checkpointId);
    const pendingIds = new Set(payload.pending_intent_ids as string[]);
    const completed = new Set(payload.completed_intent_ids as string[]);
    if ([...pendingIds].some((intentId) => completed.has(intentId))) {
      return { valid: false, reasonCode: "checkpoint_effect_overlap" };
    }
    if ([...completedIds].some((intentId) => !completed.has(intentId))) {
      return { valid: false, reasonCode: "completed_effect_regressed" };
    }
    const version = Number(payload.workflow_version);
    if (previousVersion !== undefined && version <= previousVersion) {
      return { valid: false, reasonCode: "workflow_version_not_monotonic" };
    }
    previousId = checkpointId;
    previousVersion = version;
    completedIds = completed;
    expectedSequence += 1;
  }
  return { valid: true };
}

export function validateSyntheticSlaPolicy(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, SYNTHETIC_SLA_POLICY_SCHEMA_ID, root);
}

export function validateSideEffectIntent(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, SIDE_EFFECT_INTENT_SCHEMA_ID, root);
}

export function validateSideEffectIntents(
  payloads: JsonObject[],
  root?: string,
): ValidationResult {
  const intentIds = new Set<string>();
  const idempotencyKeys = new Set<string>();
  let identity: string | undefined;
  for (const payload of payloads) {
    const result = validateSideEffectIntent(payload, root);
    if (!result.valid) {
      return result;
    }
    const currentIdentity = [
      payload.tenant_id,
      payload.case_id,
      payload.case_revision_id,
      payload.workflow_id,
    ].join("\u0000");
    if (identity !== undefined && identity !== currentIdentity) {
      return { valid: false, reasonCode: "workflow_identity_mismatch" };
    }
    identity = currentIdentity;
    const intentId = String(payload.intent_id);
    const idempotencyKey = String(payload.idempotency_key);
    if (intentIds.has(intentId) || idempotencyKeys.has(idempotencyKey)) {
      return { valid: false, reasonCode: "duplicate_intent" };
    }
    intentIds.add(intentId);
    idempotencyKeys.add(idempotencyKey);
  }
  return { valid: true };
}

export function validateSideEffectObservation(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, SIDE_EFFECT_OBSERVATION_SCHEMA_ID, root);
}

export function validateSideEffectCompletion(payload: JsonObject, root?: string): ValidationResult {
  return validateExpectedSchema(payload, SIDE_EFFECT_COMPLETION_SCHEMA_ID, root);
}

export function validateSideEffectChain(
  intent: JsonObject,
  observations: JsonObject[],
  completions: JsonObject[],
  root?: string,
): ValidationResult {
  const intentResult = validateSideEffectIntent(intent, root);
  if (!intentResult.valid) {
    return intentResult;
  }
  if (completions.length > 1) {
    return { valid: false, reasonCode: "multiple_completions" };
  }
  const observationIds = new Set<string>();
  for (const observation of observations) {
    const result = validateSideEffectObservation(observation, root);
    if (!result.valid) {
      return result;
    }
    const observationId = String(observation.observation_id);
    if (observationIds.has(observationId)) {
      return { valid: false, reasonCode: "duplicate_observation" };
    }
    observationIds.add(observationId);
    for (const field of ["tenant_id", "case_id", "case_revision_id", "workflow_id", "checkpoint_id"] as const) {
      if (intent[field] !== observation[field]) {
        return { valid: false, reasonCode: field === "tenant_id" ? "tenant_identity_mismatch" : "intent_reference_mismatch" };
      }
    }
    if (intent.intent_id !== observation.intent_id) {
      return { valid: false, reasonCode: "intent_reference_mismatch" };
    }
  }
  for (const completion of completions) {
    const result = validateSideEffectCompletion(completion, root);
    if (!result.valid) {
      return result;
    }
    for (const field of ["tenant_id", "case_id", "case_revision_id", "workflow_id", "checkpoint_id"] as const) {
      if (intent[field] !== completion[field]) {
        return { valid: false, reasonCode: field === "tenant_id" ? "tenant_identity_mismatch" : "intent_reference_mismatch" };
      }
    }
    if (intent.intent_id !== completion.intent_id) {
      return { valid: false, reasonCode: "intent_reference_mismatch" };
    }
    const matchingObservation = observations.find(
      (observation) =>
        observation.observation_id === completion.observation_id && observation.status === "present",
    );
    if (!matchingObservation) {
      return { valid: false, reasonCode: "completion_observation_missing" };
    }
    if (
      completion.observed_ticket_id !== matchingObservation.observed_ticket_id ||
      completion.observed_version !== matchingObservation.observed_version ||
      completion.result_sha256 !== matchingObservation.outcome_sha256
    ) {
      return { valid: false, reasonCode: "completion_observation_mismatch" };
    }
  }
  return { valid: true };
}

export function validateGeneratedLedgerEvent(
  payload: JsonObject,
  root?: string,
): ValidationResult {
  const result = validateExpectedSchema(payload, BUSINESS_EVENT_SCHEMA_ID, root);
  if (!result.valid) {
    return result;
  }
  const eventIndex = payload.case_event_index;
  const payloadDigest = payload.payload_sha256;
  if (!Number.isInteger(eventIndex) || Number(eventIndex) < 1) {
    return { valid: false, reasonCode: "case_event_index_required" };
  }
  if (typeof payloadDigest !== "string" || !/^[a-f0-9]{64}$/.test(payloadDigest)) {
    return { valid: false, reasonCode: "payload_sha256_required" };
  }
  return { valid: true };
}
export function stableIdempotencyKey(input: {
  tenantId: string;
  providerId: string;
  operation: string;
  naturalKey: string;
  intendedStateHash: string;
}): string {
  const canonical = JSON.stringify({
    intended_state_hash: input.intendedStateHash,
    natural_key: input.naturalKey,
    operation: input.operation,
    provider_id: input.providerId,
    tenant_id: input.tenantId,
  });
  return createHash("sha256").update(canonical, "utf8").digest("hex");
}

export function classifyEventDelivery(events: JsonObject[], root?: string): { duplicate: boolean; outOfOrder: boolean } {
  const seen = new Set<string>();
  let latestOccurredAt: string | undefined;
  let duplicate = false;
  let outOfOrder = false;

  for (const event of events) {
    const validation = validatePayload(event, root);
    if (!validation.valid) {
      throw new Error(`invalid_event_fixture:${validation.reasonCode}`);
    }
    const eventId = String(event.event_id);
    const occurredAt = String(event.occurred_at);
    duplicate ||= seen.has(eventId);
    seen.add(eventId);
    outOfOrder ||= latestOccurredAt !== undefined && occurredAt < latestOccurredAt;
    latestOccurredAt = latestOccurredAt === undefined || occurredAt > latestOccurredAt ? occurredAt : latestOccurredAt;
  }
  return { duplicate, outOfOrder };
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const objectValue = value as Record<string, unknown>;
    return `{${Object.keys(objectValue).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(objectValue[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function schemaFingerprints(root?: string): Record<string, string> {
  const fingerprints: Record<string, string> = {};
  for (const [schemaId, schema] of loadContractSchemas(root).entries()) {
    fingerprints[schemaId] = createHash("sha256").update(canonicalJson(schema), "utf8").digest("hex");
  }
  return Object.fromEntries(Object.entries(fingerprints).sort(([left], [right]) => left.localeCompare(right)));
}
