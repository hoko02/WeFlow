import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { Ajv2020 } from "ajv/dist/2020.js";

export type JsonObject = Record<string, unknown>;
export const BUSINESS_EVENT_SCHEMA_ID = "https://weflow.local/contracts/v1/business-event.schema.json";
export const CASE_PROJECTION_SCHEMA_ID = "https://weflow.local/contracts/v1/case-projection.schema.json";
export const INBOUND_MESSAGE_EVENT_SCHEMA_ID = "https://weflow.local/contracts/v1/inbound-message-event.schema.json";

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
