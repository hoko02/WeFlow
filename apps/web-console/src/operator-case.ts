import type {
  JsonObject,
  OperatorCaseSnapshot,
  OperatorCaseTimelineEntry,
} from "@weflow/contracts";

export type OperatorCaseSurfaceState =
  | { status: "loading" }
  | { status: "ready"; snapshot: OperatorCaseSnapshot }
  | { status: "not-found" }
  | { status: "identity-denied" }
  | { status: "integrity-not-ready" };

export interface OperatorCaseTimelineSummary {
  sequence: number;
  entryId: string;
  phase: string;
  sourceKind: string;
  observation: string;
  transitionLabel: string;
  gateLabel: string;
  recoveryLabel: string;
}

export interface OperatorCaseEntryDetail extends OperatorCaseTimelineSummary {
  sourceId: string;
  sourceHash: string;
  result: string;
  reasonCode: string;
  classification: string;
}

export interface ReadyOperatorCaseRenderModel {
  status: "ready";
  headline: string;
  detail: string;
  fixtureId: string;
  caseId: string;
  revisionId: string;
  revision: number;
  workflowId: string;
  workflowVersion: number;
  currentStateLabel: string;
  reportId: string;
  reportHash: string;
  snapshotHash: string;
  evidenceRoot: string;
  replayHash: string;
  capabilityLabels: string[];
  countLabels: Array<{ label: string; value: number }>;
  timeline: OperatorCaseTimelineSummary[];
  selectedEntry: OperatorCaseEntryDetail;
  limitations: string[];
}

export interface UnavailableOperatorCaseRenderModel {
  status: "loading" | "not-found" | "identity-denied" | "integrity-not-ready";
  headline: string;
  detail: string;
}

export type OperatorCaseRenderModel =
  | ReadyOperatorCaseRenderModel
  | UnavailableOperatorCaseRenderModel;

interface OperatorCaseHttpResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

export type OperatorCaseFetch = (
  input: string,
  init: { method: "GET"; headers: Record<string, string> },
) => Promise<OperatorCaseHttpResponse>;

const SCHEMA_ID =
  "https://weflow.local/contracts/v1/operator-case-snapshot.schema.json";
const ENDPOINT = "http://127.0.0.1:8000/v1/operator/cases/api-503.v1";
const HASH = /^[a-f0-9]{64}$/;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]*$/;
const SOURCE_ID = /^[a-z_]+:[A-Za-z0-9][A-Za-z0-9._:-]*$/;
const PHASES = [
  "intake", "case", "workflow", "investigation", "tools",
  "verification", "policy", "approval", "delivery", "replay",
] as const;
const SOURCE_PHASE: Record<string, string> = {
  accepted_intake: "intake",
  case_revision: "case",
  case_event: "case",
  workflow_activation: "workflow",
  workflow_checkpoint: "workflow",
  context_manifest: "investigation",
  agent_step: "investigation",
  tool_request: "tools",
  tool_result: "tools",
  evidence: "tools",
  response_candidate: "verification",
  verifier_outcome: "verification",
  policy_activation: "policy",
  capability_grant: "policy",
  policy_decision: "policy",
  authorization_binding: "policy",
  approval_request: "approval",
  approval_decision: "approval",
  delivery_intent: "delivery",
  delivery_completion: "delivery",
  replay_result: "replay",
};
const HARD_GATES = new Set([
  "verifier_outcome", "capability_grant", "policy_decision",
  "authorization_binding", "approval_decision",
]);
const STATES = new Set([
  "RECEIVED", "TICKET_READY", "INVESTIGATING", "RESPONSE_READY",
  "AWAITING_APPROVAL", "DELIVERING", "DELIVERY_RECORDED",
  "WAITING_FOR_OPERATOR", "NEEDS_RECONCILIATION",
]);
const OBSERVATIONS = new Set([
  "accepted", "recorded", "proposed", "verified", "allowed", "approved",
  "fixture_local_recorded", "denied", "stale", "timeout", "recovered",
]);
const RESULTS = new Set([
  "recorded", "passed", "allowed", "approved",
  "fixture_local_recorded", "verified", "blocked",
]);
const REASONS = new Set([
  "accepted_intake", "revision_created", "case_event_recorded",
  "workflow_activated", "workflow_checkpoint_recorded", "context_compiled",
  "agent_action_recorded", "tool_request_recorded", "tool_result_recorded",
  "evidence_linked", "candidate_proposed", "evidence_complete",
  "policy_activated", "capability_active", "fixture_policy_allowed",
  "authorization_bound", "approval_requested", "fixture_approval_approved",
  "delivery_intent_recorded", "fixture_delivery_recorded",
  "verification_replay_verified", "policy_denied", "stale_approval",
  "reconciliation_required", "recovered_after_interruption",
  "timeout_without_duplicate_completion",
]);
const TOP_KEYS = [
  "capabilities", "case", "counts", "current_state", "current_state_label",
  "evidence", "fixture_id", "fixture_sha256", "fixture_source_path",
  "operator_case_snapshot_id", "replay", "schema_id", "schema_version",
  "snapshot_sha256", "source_report", "tenant_id", "timeline",
] as const;
const ENTRY_KEYS = [
  "classification", "entry_id", "from_state", "gate_status", "observation",
  "phase", "predecessor_entry_id", "reason_code", "recovery_status", "result",
  "sequence", "source_id", "source_kind", "source_sha256", "to_state",
] as const;

function object(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function exact(value: JsonObject, keys: readonly string[]): boolean {
  const expected = [...keys].sort();
  const actual = Object.keys(value).sort();
  return actual.length === expected.length &&
    actual.every((key, index) => key === expected[index]);
}

function id(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 &&
    value.length <= 240 && SAFE_ID.test(value);
}

function digest(value: unknown): value is string {
  return typeof value === "string" && HASH.test(value);
}

function integer(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0;
}

function capabilityShape(value: unknown): boolean {
  const item = object(value);
  return item !== null && exact(item, [
    "approval_authority", "case_completion", "customer_receipt",
    "customer_resolution", "external_write", "fixture_local_delivery",
    "live_provider", "model", "network", "offline", "replay_verification_only",
    "retry_authority", "synthetic", "workflow_authority",
  ]) &&
    item.offline === true && item.synthetic === true &&
    item.replay_verification_only === true && item.fixture_local_delivery === true &&
    item.network === false && item.model === false && item.live_provider === false &&
    item.external_write === false && item.customer_receipt === false &&
    item.customer_resolution === false && item.case_completion === false &&
    item.approval_authority === false && item.workflow_authority === false &&
    item.retry_authority === false;
}

function nestedShapes(snapshot: JsonObject): boolean {
  const caseItem = object(snapshot.case);
  const report = object(snapshot.source_report);
  const evidence = object(snapshot.evidence);
  const replay = object(snapshot.replay);
  const counts = object(snapshot.counts);
  return caseItem !== null && exact(caseItem, [
    "case_id", "case_revision_id", "latest_checkpoint_id",
    "revision", "workflow_id", "workflow_version",
  ]) && id(caseItem.case_id) && id(caseItem.case_revision_id) &&
    caseItem.revision === 1 && id(caseItem.workflow_id) &&
    Number.isInteger(caseItem.workflow_version) &&
    Number(caseItem.workflow_version) >= 1 && id(caseItem.latest_checkpoint_id) &&
    report !== null && exact(report, [
      "report_id", "report_profile_id", "report_sha256", "retained_report_path",
    ]) && id(report.report_id) && digest(report.report_sha256) &&
    report.report_profile_id === "fixture-local-evidence.v1" &&
    report.retained_report_path ===
      "reports/add-offline-operator-case-timeline-acceptance.json" &&
    evidence !== null && exact(evidence, [
      "node_count", "root_sha256", "timeline_source_sha256", "trajectory_id",
    ]) && id(evidence.trajectory_id) && digest(evidence.root_sha256) &&
    digest(evidence.timeline_source_sha256) && Number.isInteger(evidence.node_count) &&
    Number(evidence.node_count) >= 1 && Number(evidence.node_count) <= 127 &&
    replay !== null && exact(replay, [
      "mode", "recorded_root_sha256", "replay_result_id", "replayed_root_sha256",
      "report_sha256", "result_sha256", "verification_outcome",
    ]) && id(replay.replay_result_id) && digest(replay.result_sha256) &&
    digest(replay.report_sha256) && digest(replay.recorded_root_sha256) &&
    digest(replay.replayed_root_sha256) && replay.mode === "verification_replay" &&
    replay.verification_outcome === "verified" &&
    counts !== null && exact(counts, [
      "agent_step_count", "case_event_count", "case_revision_count",
      "evidence_node_count", "fixture_delivery_effect_count",
      "local_ticket_effect_count", "replay_result_count", "timeline_entry_count",
      "tool_result_count", "workflow_checkpoint_count",
    ]) && Object.values(counts).every(integer) && counts.case_revision_count === 1 &&
    counts.local_ticket_effect_count === 2 &&
    counts.fixture_delivery_effect_count === 1 && counts.replay_result_count === 1;
}

function entryShape(value: unknown): value is OperatorCaseTimelineEntry {
  const item = object(value);
  if (item === null || !exact(item, ENTRY_KEYS)) return false;
  const kind = item.source_kind;
  return Number.isInteger(item.sequence) && Number(item.sequence) >= 1 &&
    id(item.entry_id) && (item.predecessor_entry_id === null ||
      id(item.predecessor_entry_id)) && typeof kind === "string" &&
    SOURCE_PHASE[kind] !== undefined && item.phase === SOURCE_PHASE[kind] &&
    typeof item.source_id === "string" && SOURCE_ID.test(item.source_id) &&
    item.source_id.split(":", 1)[0] === kind && digest(item.source_sha256) &&
    (item.classification === "synthetic" || item.classification === "redacted") &&
    (item.from_state === null ||
      (typeof item.from_state === "string" && STATES.has(item.from_state))) &&
    (item.to_state === null ||
      (typeof item.to_state === "string" && STATES.has(item.to_state))) &&
    typeof item.observation === "string" && OBSERVATIONS.has(item.observation) &&
    typeof item.result === "string" && RESULTS.has(item.result) &&
    ["not_applicable", "passed", "failed"].includes(String(item.gate_status)) &&
    ["not_required", "reconciled", "recovered", "blocked"].includes(
      String(item.recovery_status),
    ) && typeof item.reason_code === "string" && REASONS.has(item.reason_code);
}

export function validateOperatorCaseSnapshotShape(
  value: unknown,
): OperatorCaseSnapshot | null {
  const snapshot = object(value);
  if (snapshot === null || !exact(snapshot, TOP_KEYS) ||
    snapshot.schema_id !== SCHEMA_ID || snapshot.schema_version !== "v1" ||
    snapshot.tenant_id !== "tenant-alpha" ||
    snapshot.fixture_id !== "api-503-policy-approval-delivery" ||
    snapshot.fixture_source_path !==
      "fixtures/policy/api-503-policy-approval-delivery.json" ||
    !digest(snapshot.fixture_sha256) || !id(snapshot.operator_case_snapshot_id) ||
    !digest(snapshot.snapshot_sha256) || snapshot.current_state !== "DELIVERY_RECORDED" ||
    snapshot.current_state_label !== "DELIVERY_RECORDED (fixture-local)" ||
    !nestedShapes(snapshot) || !capabilityShape(snapshot.capabilities) ||
    !Array.isArray(snapshot.timeline) || snapshot.timeline.length < 2 ||
    snapshot.timeline.length > 128 || !snapshot.timeline.every(entryShape)) return null;

  const timeline = snapshot.timeline as unknown as OperatorCaseTimelineEntry[];
  const caseItem = snapshot.case as JsonObject;
  const report = snapshot.source_report as JsonObject;
  const evidence = snapshot.evidence as JsonObject;
  const replay = snapshot.replay as JsonObject;
  const counts = snapshot.counts as JsonObject;
  let prior: string | null = null;
  let priorPhase = -1;
  const entryIds: string[] = [];
  const sourceIds: string[] = [];
  const kinds: string[] = [];
  for (let index = 0; index < timeline.length; index += 1) {
    const entry = timeline[index];
    const phase = PHASES.indexOf(entry.phase as (typeof PHASES)[number]);
    if (entry.sequence !== index + 1 || entry.predecessor_entry_id !== prior ||
      phase < priorPhase || (HARD_GATES.has(entry.source_kind) &&
        entry.gate_status !== "passed") || entry.gate_status === "failed" ||
      entry.result === "blocked" || ["denied", "stale", "timeout"].includes(
        entry.observation,
      ) || entry.recovery_status !== "not_required") return null;
    prior = entry.entry_id;
    priorPhase = phase;
    entryIds.push(entry.entry_id);
    sourceIds.push(entry.source_id);
    kinds.push(entry.source_kind);
  }
  const countKind = (kind: string) => kinds.filter((item) => item === kind).length;
  if (new Set(entryIds).size !== entryIds.length ||
    new Set(sourceIds).size !== sourceIds.length ||
    !Object.keys(SOURCE_PHASE).every((kind) => kinds.includes(kind)) ||
    kinds.at(-1) !== "replay_result" ||
    report.report_sha256 !== replay.report_sha256 ||
    evidence.root_sha256 !== replay.recorded_root_sha256 ||
    evidence.root_sha256 !== replay.replayed_root_sha256 ||
    !sourceIds.includes("case_revision:" + String(caseItem.case_revision_id)) ||
    !sourceIds.includes("workflow_checkpoint:" + String(caseItem.latest_checkpoint_id)) ||
    sourceIds.at(-1) !== "replay_result:" + String(replay.replay_result_id) ||
    timeline.at(-1)?.source_sha256 !== replay.result_sha256 ||
    counts.timeline_entry_count !== timeline.length ||
    counts.case_event_count !== kinds.filter(
      (kind) => kind === "accepted_intake" || kind === "case_event",
    ).length || counts.case_revision_count !== countKind("case_revision") ||
    counts.workflow_checkpoint_count !== countKind("workflow_checkpoint") ||
    counts.agent_step_count !== countKind("agent_step") ||
    counts.tool_result_count !== countKind("tool_result") ||
    counts.fixture_delivery_effect_count !== countKind("delivery_completion") ||
    counts.evidence_node_count !== timeline.length - 1 ||
    counts.replay_result_count !== countKind("replay_result")) return null;
  const one = (kind: string, observation: string) => timeline.filter(
    (entry) => entry.source_kind === kind && entry.observation === observation,
  ).length === 1;
  if (!one("verifier_outcome", "verified") || !one("policy_decision", "allowed") ||
    !one("approval_decision", "approved") ||
    !one("delivery_completion", "fixture_local_recorded")) return null;
  return snapshot as unknown as OperatorCaseSnapshot;
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(canonicalJson).join(",") + "]";
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return "{" + Object.keys(record).sort().map(
      (key) => JSON.stringify(key) + ":" + canonicalJson(record[key]),
    ).join(",") + "}";
  }
  return JSON.stringify(value);
}

async function sha256(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(value));
  const result = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(result)].map(
    (item) => item.toString(16).padStart(2, "0"),
  ).join("");
}

export async function validateOperatorCaseSnapshot(
  value: unknown,
): Promise<OperatorCaseSnapshot | null> {
  const snapshot = validateOperatorCaseSnapshotShape(value);
  if (snapshot === null) return null;
  const entryChecks = await Promise.all(snapshot.timeline.map(async (entry) => {
    const hash = await sha256({
      sequence: entry.sequence,
      source_id: entry.source_id,
      source_kind: entry.source_kind,
      source_sha256: entry.source_sha256,
    });
    return entry.entry_id === "operator_entry_" + hash.slice(0, 32);
  }));
  if (entryChecks.some((valid) => !valid)) return null;
  const sourceMaterial = snapshot.timeline.slice(0, -1).map((entry) => ({
    source_kind: entry.source_kind,
    source_id: entry.source_id,
    source_sha256: entry.source_sha256,
  }));
  if (snapshot.evidence.timeline_source_sha256 !== await sha256(sourceMaterial)) return null;
  const material = { ...snapshot } as JsonObject;
  delete material.operator_case_snapshot_id;
  delete material.snapshot_sha256;
  const hash = await sha256(material);
  if (snapshot.snapshot_sha256 !== hash ||
    snapshot.operator_case_snapshot_id !== "operator_case_snapshot_" + hash) return null;
  return snapshot;
}

export async function loadOperatorCaseSurface(
  fetcher: OperatorCaseFetch = globalThis.fetch as OperatorCaseFetch,
): Promise<OperatorCaseSurfaceState> {
  try {
    const response = await fetcher(ENDPOINT, {
      method: "GET",
      headers: { "X-WeFlow-Synthetic-Actor": "simulator-tenant-a" },
    });
    if (response.status === 403) return { status: "identity-denied" };
    if (response.status === 404) return { status: "not-found" };
    if (!response.ok) return { status: "integrity-not-ready" };
    const snapshot = await validateOperatorCaseSnapshot(await response.json());
    return snapshot ? { status: "ready", snapshot } : { status: "integrity-not-ready" };
  } catch {
    return { status: "not-found" };
  }
}

function transition(entry: OperatorCaseTimelineEntry): string {
  if (entry.from_state !== null && entry.to_state !== null) {
    return entry.from_state + " → " + entry.to_state;
  }
  if (entry.to_state !== null) return "→ " + entry.to_state;
  return entry.observation;
}

function summary(entry: OperatorCaseTimelineEntry): OperatorCaseTimelineSummary {
  return {
    sequence: entry.sequence,
    entryId: entry.entry_id,
    phase: entry.phase,
    sourceKind: entry.source_kind,
    observation: entry.observation,
    transitionLabel: transition(entry),
    gateLabel: entry.gate_status,
    recoveryLabel: entry.recovery_status,
  };
}

function detail(entry: OperatorCaseTimelineEntry): OperatorCaseEntryDetail {
  return {
    ...summary(entry),
    sourceId: entry.source_id,
    sourceHash: entry.source_sha256,
    result: entry.result,
    reasonCode: entry.reason_code,
    classification: entry.classification,
  };
}

export function renderOperatorCaseSurface(
  state: OperatorCaseSurfaceState,
  selectedEntryId?: string,
): OperatorCaseRenderModel {
  if (state.status === "loading") return {
    status: "loading",
    headline: "Operator Case: loading",
    detail: "Reading the fixed tenant-scoped offline snapshot.",
  };
  if (state.status === "not-found") return {
    status: "not-found",
    headline: "Operator Case: unavailable",
    detail: "No tenant-visible canonical Case snapshot is available.",
  };
  if (state.status === "identity-denied") return {
    status: "identity-denied",
    headline: "Operator Case: identity denied",
    detail: "The synthetic observer identity was not accepted.",
  };
  if (state.status === "integrity-not-ready") return {
    status: "integrity-not-ready",
    headline: "Operator Case: integrity not ready",
    detail: "The retained Case evidence did not pass the closed snapshot boundary.",
  };
  const snapshot = state.snapshot;
  const selected = snapshot.timeline.find(
    (entry) => entry.entry_id === selectedEntryId,
  ) ?? snapshot.timeline[0];
  const caseItem = snapshot.case as {
    case_id: string;
    case_revision_id: string;
    revision: number;
    workflow_id: string;
    workflow_version: number;
  };
  const report = snapshot.source_report as {
    report_id: string;
    report_sha256: string;
  };
  const evidence = snapshot.evidence as { root_sha256: string };
  const replay = snapshot.replay as { result_sha256: string };
  const countValues = snapshot.counts as Record<string, number>;
  return {
    status: "ready",
    headline: "API-503 Operator Case timeline",
    detail: "One source-linked synthetic Case projection generated from offline facts.",
    fixtureId: snapshot.fixture_id,
    caseId: caseItem.case_id,
    revisionId: caseItem.case_revision_id,
    revision: caseItem.revision,
    workflowId: caseItem.workflow_id,
    workflowVersion: caseItem.workflow_version,
    currentStateLabel: snapshot.current_state_label,
    reportId: report.report_id,
    reportHash: report.report_sha256,
    snapshotHash: snapshot.snapshot_sha256,
    evidenceRoot: evidence.root_sha256,
    replayHash: replay.result_sha256,
    capabilityLabels: [
      "offline synthetic fixture",
      "Replay verification only",
      "fixture-local delivery record",
      "no network or model",
      "no external-write or workflow authority",
    ],
    countLabels: [
      { label: "Timeline entries", value: countValues.timeline_entry_count },
      { label: "Case events", value: countValues.case_event_count },
      { label: "Workflow checkpoints", value: countValues.workflow_checkpoint_count },
      { label: "Agent steps", value: countValues.agent_step_count },
      { label: "Tool results", value: countValues.tool_result_count },
      { label: "Fixture-local ticket effects", value: countValues.local_ticket_effect_count },
      { label: "Fixture-local delivery effects", value: countValues.fixture_delivery_effect_count },
    ],
    timeline: snapshot.timeline.map(summary),
    selectedEntry: detail(selected),
    limitations: [
      "No live provider send or provider acknowledgement.",
      "No customer receipt, incident resolution, Case completion, or customer-success claim.",
      "No approval, workflow, retry, Replay, or external-effect control is exposed.",
    ],
  };
}
