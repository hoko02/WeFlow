import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  JsonObject,
  canonicalJson,
  validatePayload,
  validateQQHandlerAcceptanceReport,
  validateQQHandlerApprovalChain,
  validateQQHandlerArtifact,
  validateQQHandlerCommand,
  validateQQHandlerNotificationChain,
  validateQQHandlerPassiveReplyChain,
} from "./index.js";

function findRepositoryRoot(start = process.cwd()): string {
  let current = resolve(start);
  while (true) {
    try {
      readFileSync(resolve(current, "pyproject.toml"), "utf8");
      return current;
    } catch {
      const parent = resolve(current, "..");
      if (parent === current) throw new Error("WeFlow repository root could not be located");
      current = parent;
    }
  }
}

const root = findRepositoryRoot();
const fixture = JSON.parse(readFileSync(resolve(
  root,
  "fixtures/contracts/v1/semantic/qq-handler-approval-and-delivery.json",
), "utf8")) as Record<string, JsonObject>;
const failures: string[] = [];

for (const [name, payload] of Object.entries(fixture)) {
  if (!validatePayload(payload, root).valid) failures.push(`${name}:schema`);
}
if (!validateQQHandlerArtifact(fixture.issue_artifact, root).valid) failures.push("issue:semantic");
if (!validateQQHandlerArtifact(fixture.response_artifact, root).valid) failures.push("response:semantic");
if (!validateQQHandlerCommand(fixture.command, root).valid) failures.push("command:semantic");
if (!validateQQHandlerNotificationChain(
  fixture.notification_intent,
  [fixture.notification_result],
  root,
).valid) failures.push("notification:semantic");
if (!validateQQHandlerApprovalChain(
  fixture.approval_request,
  [fixture.approval_decision],
  root,
).valid) failures.push("approval:semantic");
if (!validateQQHandlerPassiveReplyChain(
  fixture.passive_reply_intent,
  [fixture.passive_reply_result],
  root,
).valid) failures.push("passive-reply:semantic");
const groupNudge = structuredClone(fixture.passive_reply_intent) as JsonObject;
groupNudge.surface = "group";
groupNudge.operation = "qq.final_reply.execute";
groupNudge.response_kind = "group-nudge";
groupNudge.reply_msg_seq = 2;
groupNudge.approval_decision_id = null;
if (!validateQQHandlerPassiveReplyChain(groupNudge, [], root).valid) {
  failures.push("group-nudge:semantic");
}
const unsafeNudge = structuredClone(groupNudge) as JsonObject;
unsafeNudge.reply_msg_seq = 5;
if (validateQQHandlerPassiveReplyChain(unsafeNudge, [], root).valid) {
  failures.push("group-nudge-shape-accepted");
}

const report = structuredClone(fixture.report) as JsonObject;
const material = { ...report };
delete material.report_sha256;
report.report_sha256 = createHash("sha256").update(canonicalJson(material)).digest("hex");
if (!validateQQHandlerAcceptanceReport(report, root).valid) failures.push("report:semantic");

const unknownCommand = structuredClone(fixture.command) as JsonObject;
unknownCommand.command = "send-arbitrary-message";
if (validateQQHandlerCommand(unknownCommand, root).valid) failures.push("unknown-command-accepted");
const rejectCommand = structuredClone(fixture.command) as JsonObject;
rejectCommand.command = "reject";
rejectCommand.candidate_artifact_id = null;
rejectCommand.rejection_reason_code = "not_my_scope";
if (!validateQQHandlerCommand(rejectCommand, root).valid) failures.push("reject-reason-denied");
const unsafeReason = structuredClone(fixture.command) as JsonObject;
unsafeReason.rejection_reason_code = "not_my_scope";
if (validateQQHandlerCommand(unsafeReason, root).valid) {
  failures.push("non-reject-reason-accepted");
}

const leaked = structuredClone(fixture.response_artifact) as JsonObject;
leaked.candidate_text = "private";
if (validatePayload(leaked, root).valid) failures.push("candidate-plaintext-accepted");

if (failures.length > 0) {
  throw new Error(`QQ handler contract checks failed: ${failures.join(", ")}`);
}

console.log("QQ handler cross-language contracts verified");
