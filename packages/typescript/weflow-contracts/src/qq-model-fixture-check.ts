import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  JsonObject,
  validatePayload,
  validateQQModelLineage,
  validateQQModelWorkflowAcceptanceReport,
  validateQQModelWorkflowReadiness,
  validateQQModelWorkflowVerification,
} from "./index.js";

function repositoryRoot(start = process.cwd()): string {
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

const root = repositoryRoot();
const valid = JSON.parse(readFileSync(resolve(
  root,
  "fixtures/contracts/v1/semantic/qq-model-workflow.json",
), "utf8")) as Record<string, JsonObject>;
const invalid = JSON.parse(readFileSync(resolve(
  root,
  "fixtures/contracts/v1/invalid/qq-model-workflow-invalid-payloads.json",
), "utf8")) as Record<string, JsonObject>;
const failures: string[] = [];

for (const [name, payload] of Object.entries(valid)) {
  if (!validatePayload(payload, root).valid) failures.push(`${name}:schema`);
}
if (!validateQQModelWorkflowReadiness(valid.readiness, root).valid) {
  failures.push("readiness:semantic");
}
const lineage = ["request", "context", "budget", "invocation", "binding", "preview", "outcome"]
  .map((name) => valid[name]);
if (!validateQQModelLineage(lineage, root).valid) failures.push("lineage:semantic");
if (!validateQQModelWorkflowAcceptanceReport(valid.report, root).valid) {
  failures.push("report:semantic");
}
if (!validateQQModelWorkflowVerification(valid.verification, root).valid) {
  failures.push("verification:semantic");
}
for (const [name, payload] of Object.entries(invalid)) {
  if (validatePayload(payload, root).valid) failures.push(`${name}:accepted`);
}

const foreign = lineage.map((item) => structuredClone(item)) as JsonObject[];
foreign[4].tenant_id = "tenant-foreign";
if (validateQQModelLineage(foreign, root).valid) failures.push("foreign-lineage:accepted");

const fakeLive = structuredClone(valid.report) as JsonObject;
fakeLive.live_model_contact_verified = true;
if (validateQQModelWorkflowAcceptanceReport(fakeLive, root).valid) {
  failures.push("fake-as-live:accepted");
}

if (failures.length > 0) {
  throw new Error(`QQ model contract checks failed: ${failures.join(", ")}`);
}

console.log("QQ model cross-language contracts verified");
