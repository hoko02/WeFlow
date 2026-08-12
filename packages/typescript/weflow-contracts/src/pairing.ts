import { createHash } from "node:crypto";
import { JsonObject, canonicalJson, validatePayload } from "./index.js";

export const QQ_GROUP_PAIRING_CHALLENGE_SCHEMA_ID = "https://weflow.local/contracts/v1/qq-group-pairing-challenge.schema.json";
export const QQ_GROUP_PAIRING_COMPLETION_SCHEMA_ID = "https://weflow.local/contracts/v1/qq-group-pairing-completion.schema.json";
export const QQ_GROUP_PAIRING_ACCEPTANCE_REPORT_SCHEMA_ID = "https://weflow.local/contracts/v1/qq-group-pairing-acceptance-report.schema.json";

export interface QQGroupPairingChallenge extends JsonObject { schema_id: typeof QQ_GROUP_PAIRING_CHALLENGE_SCHEMA_ID; challenge_id: string; challenge_sha256: string; app_id_hash: string; tenant_id: string; tenant_id_hash: string; status: "PENDING" | "EXPIRED" | "CANCELLED" | "CONFLICT"; }
export interface QQGroupPairingCompletion extends JsonObject { schema_id: typeof QQ_GROUP_PAIRING_COMPLETION_SCHEMA_ID; completion_id: string; challenge_id: string; pairing_id: string; tenant_id: string; tenant_id_hash: string; app_id_hash: string; group_openid_hash: string; status: "COMPLETED" | "REVOKED" | "EXPIRED" | "CONFLICT"; }
export interface QQGroupPairingAcceptanceReport extends JsonObject { schema_id: typeof QQ_GROUP_PAIRING_ACCEPTANCE_REPORT_SCHEMA_ID; mode: "offline-fake" | "qq-sandbox-live"; accepted: boolean; fake_pairing_verified: boolean; qq_group_pairing_live_verified: boolean; report_sha256: string; }

export function validateQQGroupPairingChain(challenge: JsonObject, completions: JsonObject[], root?: string): { valid: boolean; errors: string[] } {
  if (!validatePayload(challenge, root).valid) return { valid: false, errors: ["challenge_schema"] };
  const tenantHash = createHash("sha256").update(String(challenge.tenant_id)).digest("hex");
  if (challenge.tenant_id_hash !== tenantHash) return { valid: false, errors: ["tenant_hash_mismatch"] };
  if (completions.length > 1) return { valid: false, errors: ["duplicate_completion"] };
  for (const completion of completions) {
    if (!validatePayload(completion, root).valid) return { valid: false, errors: ["completion_schema"] };
    for (const field of ["challenge_id", "tenant_id", "tenant_id_hash", "app_id_hash"]) if (completion[field] !== challenge[field]) return { valid: false, errors: ["completion_link_mismatch"] };
  }
  return { valid: true, errors: [] };
}

export function validateQQGroupPairingAcceptanceReport(report: JsonObject, root?: string): { valid: boolean; errors: string[] } {
  if (!validatePayload(report, root).valid) return { valid: false, errors: ["report_schema"] };
  const material = { ...report }; delete material.report_sha256;
  if (report.report_sha256 !== createHash("sha256").update(canonicalJson(material)).digest("hex")) return { valid: false, errors: ["report_hash_mismatch"] };
  const completed = report.completion_status === "COMPLETED";
  const linked = ["pairing_id", "app_id_hash", "group_openid_hash", "tenant_id_hash"].every((field) => typeof report[field] === "string");
  if (report.accepted !== (completed && linked)) return { valid: false, errors: ["acceptance_mismatch"] };
  if (report.mode === "offline-fake" && !(report.fake_pairing_verified === true && report.qq_group_pairing_live_verified === false && report.network_required === false && report.credentials_required === false)) return { valid: false, errors: ["fake_mode_overclaim"] };
  if (report.mode === "qq-sandbox-live" && !(report.fake_pairing_verified === false && report.qq_group_pairing_live_verified === completed && report.network_required === true && report.credentials_required === true)) return { valid: false, errors: ["live_mode_invalid"] };
  return { valid: true, errors: [] };
}
