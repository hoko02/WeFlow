import type { JsonObject } from "@weflow/contracts";

export interface RenderedFoundationStatus {
  status: "ready" | "not-ready";
  headline: string;
  detail: string;
  mode: "offline" | "service-boundary" | "offline-console" | "unknown";
  modeLabel: string;
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

function modeLabel(mode: RenderedFoundationStatus["mode"]): string {
  const labels: Record<RenderedFoundationStatus["mode"], string> = {
    offline: "离线（offline）",
    "service-boundary": "服务边界（service-boundary）",
    "offline-console": "离线控制台（offline-console）",
    unknown: "未知（unknown）",
  };
  return labels[mode];
}

export function renderFoundationStatus(payload: JsonObject): RenderedFoundationStatus {
  const policy = asObject(payload.policy_denial);
  const capability = safeCode(policy?.capability);
  const reasonCode = safeCode(policy?.reason_code);
  const policyDenial = capability && reasonCode ? { capability, reasonCode } : null;
  const ready = payload.ready === true;
  const mode = safeMode(payload.mode);

  if (ready) {
    return {
      status: "ready",
      headline: "运行状态：已就绪",
      detail: "本地基础设施诊断可用。",
      mode,
      modeLabel: modeLabel(mode),
      policyDenial: null,
    };
  }

  return {
    status: "not-ready",
    headline: "运行状态：未就绪",
    detail: policyDenial
      ? `提供方或配置能力被拒绝（${policyDenial.reasonCode}）。`
      : "一个或多个声明的本地依赖尚未就绪。",
    mode,
    modeLabel: modeLabel(mode),
    policyDenial,
  };
}
