import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  JsonObject,
  validateGeneratedLedgerEvent,
  validatePayload,
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
const missingGeneratedMetadata = JSON.parse(
  readFileSync(resolve(root, "fixtures/contracts/v1/semantic/missing-generated-ledger-metadata.json"), "utf8"),
) as JsonObject;
const missingIdentity = JSON.parse(
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
if (validatePayload(missingIdentity, root).valid) {
  failedSchemas.push("missing-schema-identity");
}
if (validateGeneratedLedgerEvent(missingGeneratedMetadata, root).valid) {
  failedSchemas.push("missing-generated-ledger-metadata");
}
if (failedSchemas.length > 0) {
  throw new Error(`contract-fixture-check-failed:${failedSchemas.join(",")}`);
}

console.log(
  JSON.stringify({
    report_type: "weflow-typescript-contract-check.v1",
    valid_payloads: Object.keys(validPayloads).length,
    invalid_payloads: Object.keys(invalidIntakePayloads).length + 2,
  }),
);
