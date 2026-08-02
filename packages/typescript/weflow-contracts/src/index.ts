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
