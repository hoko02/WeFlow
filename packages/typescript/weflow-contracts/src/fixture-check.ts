import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  JsonObject,
  validateAgentActionForContext,
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
};const missingIdentity = JSON.parse(
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
for (const [name, payload] of Object.entries(invalidAgentPayloads)) {
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
}if (validatePayload(missingIdentity, root).valid) {
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
      2,
  }),
);
