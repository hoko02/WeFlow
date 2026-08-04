<script setup lang="ts">
import { onMounted, ref } from "vue";

import type { JsonObject } from "@weflow/contracts";
import { renderFoundationStatus, type RenderedFoundationStatus } from "./foundation-status.js";

type FoundationCapabilities = JsonObject & {
  business_workflow_implemented: boolean;
  durable_support_workflow_implemented: boolean;
  replay_investigation_agent_implemented: boolean;
  response_candidate_verification_implemented: boolean;
  fixture_policy_approval_delivery_implemented: boolean;
  fixture_approval_enabled: boolean;
  fixture_outbound_delivery_enabled: boolean;
  live_approval_enabled: boolean;
  live_outbound_delivery_enabled: boolean;
  real_provider_enabled: boolean;
  multi_agent_enabled: boolean;
  approval_enabled: boolean;
  outbound_delivery_enabled: boolean;
  customer_resolution_enabled: boolean;
  external_writes_enabled: boolean;
  operational_ready: boolean;
  synthetic_case_intake_implemented: boolean;
};

const status = ref<"checking" | "ready" | "not-ready">("checking");
const message = ref("Checking the local Platform API fixture-control endpoint.");
const capabilities = ref<FoundationCapabilities | null>(null);
const renderedStatus = ref<RenderedFoundationStatus | null>(null);

onMounted(async () => {
  try {
    const healthResponse = await fetch("http://127.0.0.1:8000/health/ready");
    const healthPayload = (await healthResponse.json()) as JsonObject;
    renderedStatus.value = renderFoundationStatus(healthPayload);
    status.value = renderedStatus.value.status;
    message.value = renderedStatus.value.detail;

    const capabilitiesResponse = await fetch("http://127.0.0.1:8000/foundation/capabilities");
    if (capabilitiesResponse.ok) {
      capabilities.value = (await capabilitiesResponse.json()) as FoundationCapabilities;
    }
  } catch {
    status.value = "not-ready";
    message.value = "Platform API is not running. Start the local services with scripts/dev.py up --mode offline.";
  }
});
</script>

<template>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">WeFlow / Change 4</p>
      <h1>Fixture Policy and Approval Console</h1>
      <p>This console reports local service, synthetic Case intake, durable workflow, replay investigation, and fixture-only policy/approval/delivery safety status. It never claims a live external write, customer receipt, or resolution outcome.</p>
    </section>

    <section class="status" :data-status="status">
      <h2>{{ renderedStatus?.headline ?? `Operational status: ${status}` }}</h2>
      <p>{{ message }}</p>
      <p v-if="renderedStatus">Mode: {{ renderedStatus.mode }}</p>
      <p v-if="renderedStatus?.policyDenial">
        Provider/configuration denial: {{ renderedStatus.policyDenial.capability }} ({{ renderedStatus.policyDenial.reasonCode }})
      </p>
      <dl v-if="capabilities">
        <div>
          <dt>Business workflow implemented</dt>
          <dd>{{ capabilities.business_workflow_implemented ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>External writes enabled</dt>
          <dd>{{ capabilities.external_writes_enabled ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Synthetic Case intake implemented</dt>
          <dd>{{ capabilities.synthetic_case_intake_implemented ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Fixture-local durable workflow implemented</dt>
          <dd>{{ capabilities.durable_support_workflow_implemented ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Replay investigation Agent implemented</dt>
          <dd>{{ capabilities.replay_investigation_agent_implemented ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Response-candidate verifier implemented</dt>
          <dd>{{ capabilities.response_candidate_verification_implemented ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Live provider enabled</dt>
          <dd>{{ capabilities.real_provider_enabled ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Fixture policy/approval/delivery implemented</dt>
          <dd>{{ capabilities.fixture_policy_approval_delivery_implemented ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Fixture approval and local delivery enabled</dt>
          <dd>{{ (capabilities.fixture_approval_enabled && capabilities.fixture_outbound_delivery_enabled) ? "yes" : "no" }}</dd>
        </div>
        <div>
          <dt>Live approval, live delivery, or customer resolution enabled</dt>
          <dd>{{ (capabilities.live_approval_enabled || capabilities.live_outbound_delivery_enabled || capabilities.customer_resolution_enabled) ? "yes" : "no" }}</dd>
        </div>
      </dl>
    </section>

    <section class="limits">
      <h2>Change 4 limits</h2>
      <ul>
        <li>Exactly one deterministic Replay Agent may use checked-in API-503 fixtures.</li>
        <li>Only CRM, monitoring, and knowledge fixture reads can produce redacted evidence hashes.</li>
        <li>The deterministic verifier may advance to RESPONSE_READY; only an explicit, hash-bound fixture activation may continue to approval.</li>
        <li>One fixture-local adapter can record an idempotent local delivery after policy and approval; it is not a network call or customer-success claim.</li>
        <li>Live providers, credentials, multi-Agent coordination, real approval, real delivery, external writes, and customer resolution remain disabled.</li>
      </ul>
    </section>
  </main>
</template>

<style>
:root {
  color: #e8edf8;
  background: #101827;
  font-family: Inter, "Segoe UI", sans-serif;
}

body {
  margin: 0;
}

.shell {
  box-sizing: border-box;
  margin: 0 auto;
  max-width: 880px;
  min-height: 100vh;
  padding: 72px 24px;
}

.hero, .status, .limits {
  border: 1px solid #2d3c56;
  border-radius: 16px;
  background: #152238;
  padding: 28px;
  margin-bottom: 20px;
}

.eyebrow {
  color: #78d4c7;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1, h2, p {
  margin-top: 0;
}

.status[data-status="ready"] {
  border-color: #49b392;
}

.status[data-status="not-ready"] {
  border-color: #d99b4b;
}

dl {
  display: grid;
  gap: 12px;
}

dl div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

dt {
  color: #b7c5d9;
}

dd {
  margin: 0;
  font-weight: 700;
}

li + li {
  margin-top: 8px;
}
</style>
