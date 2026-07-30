import type { JsonObject } from "@weflow/contracts";

export interface RenderedFoundationStatus {
  status: "ready" | "not-ready";
  headline: string;
  detail: string;
  mode: "offline" | "service-boundary" | "offline-console" | "unknown";
  policyDenial: { capability: string; reasonCode: string } | null;
}

const SAFE_CODE = /^[a-z][a-z0-9_-]{0,63}$/i;

function safeCode(value: unknown): string | null {
  return typeof value === "string" && SAFE_CODE.test(value) ? value : null;
}

function asObject(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function safeMode(value: unknown): RenderedFoundationStatus["mode"] {
  return value === "offline" || value === "service-boundary" || value === "offline-console"
    ? value
    : "unknown";
}

export function renderFoundationStatus(payload: JsonObject): RenderedFoundationStatus {
  const policy = asObject(payload.policy_denial);
  const capability = safeCode(policy?.capability);
  const reasonCode = safeCode(policy?.reason_code);
  const policyDenial = capability && reasonCode ? { capability, reasonCode } : null;
  const ready = payload.ready === true;

  if (ready) {
    return {
      status: "ready",
      headline: "Operational status: ready",
      detail: "Local foundation diagnostics are available.",
      mode: safeMode(payload.mode),
      policyDenial: null,
    };
  }

  return {
    status: "not-ready",
    headline: "Operational status: not-ready",
    detail: policyDenial
      ? `A provider or configuration capability is denied (${policyDenial.reasonCode}).`
      : "One or more declared local dependencies are not ready.",
    mode: safeMode(payload.mode),
    policyDenial,
  };
}
