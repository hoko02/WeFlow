<script setup lang="ts">
import { onMounted, ref } from "vue";

import type { JsonObject } from "@weflow/contracts";
import {
  loadEvaluationSurface,
  renderEvaluationSurface,
  type EvaluationRenderModel,
  type EvaluationSurfaceState,
} from "./evaluation-report.js";
import { renderFoundationStatus, type RenderedFoundationStatus } from "./foundation-status.js";
import {
  loadOperatorCaseSurface,
  renderOperatorCaseSurface,
  type OperatorCaseRenderModel,
  type OperatorCaseSurfaceState,
} from "./operator-case.js";

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
const evaluationState = ref<EvaluationSurfaceState>({ status: "loading" });
const evaluation = ref<EvaluationRenderModel>(renderEvaluationSurface(evaluationState.value));
const selectedEvaluationTaskId = ref<string | undefined>(undefined);
const operatorState = ref<OperatorCaseSurfaceState>({ status: "loading" });
const operatorCase = ref<OperatorCaseRenderModel>(
  renderOperatorCaseSurface(operatorState.value),
);
const selectedOperatorEntryId = ref<string | undefined>(undefined);

function selectEvaluationTask(evaluationTaskId: string): void {
  selectedEvaluationTaskId.value = evaluationTaskId;
  evaluation.value = renderEvaluationSurface(evaluationState.value, evaluationTaskId);
}

function selectOperatorEntry(entryId: string): void {
  selectedOperatorEntryId.value = entryId;
  operatorCase.value = renderOperatorCaseSurface(operatorState.value, entryId);
}

onMounted(async () => {
  const evaluationRequest = loadEvaluationSurface();
  const operatorRequest = loadOperatorCaseSurface();
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
  evaluationState.value = await evaluationRequest;
  if (evaluationState.value.status === "ready") {
    selectedEvaluationTaskId.value = evaluationState.value.snapshot.tasks[0]?.evaluation_task_id;
  }
  evaluation.value = renderEvaluationSurface(
    evaluationState.value,
    selectedEvaluationTaskId.value,
  );
  operatorState.value = await operatorRequest;
  if (operatorState.value.status === "ready") {
    selectedOperatorEntryId.value = operatorState.value.snapshot.timeline[0]?.entry_id;
  }
  operatorCase.value = renderOperatorCaseSurface(
    operatorState.value,
    selectedOperatorEntryId.value,
  );
});
</script>

<template>
  <main class="shell">
    <section class="hero">
      <p class="eyebrow">WeFlow / Offline Operator Evidence</p>
      <h1>Operator Case &amp; Evaluation Console</h1>
      <p>This local console presents one source-linked API-503 Case timeline and a revalidated 12-task Replay benchmark beside foundation readiness. It never treats fixture delivery as a provider send, customer receipt, incident resolution, completion, or authorization.</p>
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

    <section class="operator-case" :data-status="operatorCase.status">
      <p class="eyebrow">Operator Case / Offline synthetic evidence</p>
      <h2>{{ operatorCase.headline }}</h2>
      <p>{{ operatorCase.detail }}</p>

      <template v-if="operatorCase.status === 'ready'">
        <dl class="operator-meta">
          <div>
            <dt>Fixture</dt>
            <dd>{{ operatorCase.fixtureId }}</dd>
          </div>
          <div>
            <dt>Current fixture state</dt>
            <dd>{{ operatorCase.currentStateLabel }}</dd>
          </div>
          <div class="hash-row">
            <dt>Case / revision</dt>
            <dd><code>{{ operatorCase.caseId }} / {{ operatorCase.revisionId }} (r{{ operatorCase.revision }})</code></dd>
          </div>
          <div class="hash-row">
            <dt>Workflow</dt>
            <dd><code>{{ operatorCase.workflowId }} (v{{ operatorCase.workflowVersion }})</code></dd>
          </div>
          <div class="hash-row">
            <dt>Snapshot / source report hash</dt>
            <dd><code>{{ operatorCase.snapshotHash }} / {{ operatorCase.reportHash }}</code></dd>
          </div>
          <div class="hash-row">
            <dt>Evidence root / Replay result</dt>
            <dd><code>{{ operatorCase.evidenceRoot }} / {{ operatorCase.replayHash }}</code></dd>
          </div>
        </dl>

        <div class="capability-badges" aria-label="Operator Case capability boundaries">
          <span v-for="label in operatorCase.capabilityLabels" :key="label">{{ label }}</span>
        </div>

        <div class="operator-grid">
          <nav class="timeline-list" aria-label="API-503 source-linked Case timeline">
            <button
              v-for="entry in operatorCase.timeline"
              :key="entry.entryId"
              type="button"
              :class="{ selected: entry.entryId === selectedOperatorEntryId }"
              @click="selectOperatorEntry(entry.entryId)"
            >
              <span><strong>{{ entry.sequence }}</strong> · {{ entry.phase }} / {{ entry.sourceKind }}</span>
              <small>{{ entry.transitionLabel }} · gate {{ entry.gateLabel }} · recovery {{ entry.recoveryLabel }}</small>
            </button>
          </nav>

          <article class="operator-detail">
            <p class="eyebrow">Selected source-linked entry</p>
            <h3>{{ operatorCase.selectedEntry.phase }} / {{ operatorCase.selectedEntry.sourceKind }}</h3>
            <p>{{ operatorCase.selectedEntry.transitionLabel }} · {{ operatorCase.selectedEntry.result }}</p>
            <dl>
              <div>
                <dt>Sequence</dt>
                <dd>{{ operatorCase.selectedEntry.sequence }}</dd>
              </div>
              <div class="hash-row">
                <dt>Entry identity</dt>
                <dd><code>{{ operatorCase.selectedEntry.entryId }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>Source identity</dt>
                <dd><code>{{ operatorCase.selectedEntry.sourceId }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>Source hash</dt>
                <dd><code>{{ operatorCase.selectedEntry.sourceHash }}</code></dd>
              </div>
              <div>
                <dt>Classification</dt>
                <dd>{{ operatorCase.selectedEntry.classification }}</dd>
              </div>
              <div>
                <dt>Observation / result</dt>
                <dd>{{ operatorCase.selectedEntry.observation }} / {{ operatorCase.selectedEntry.result }}</dd>
              </div>
              <div>
                <dt>Gate / recovery</dt>
                <dd>{{ operatorCase.selectedEntry.gateLabel }} / {{ operatorCase.selectedEntry.recoveryLabel }}</dd>
              </div>
              <div>
                <dt>Reason code</dt>
                <dd>{{ operatorCase.selectedEntry.reasonCode }}</dd>
              </div>
            </dl>

            <h4>Bounded source counts</h4>
            <ul class="evidence-list">
              <li v-for="count in operatorCase.countLabels" :key="count.label">
                <strong>{{ count.label }}</strong>: {{ count.value }}
              </li>
            </ul>
          </article>
        </div>

        <aside class="unsupported operator-limits">
          <h3>Explicit capability limits</h3>
          <ul>
            <li v-for="limit in operatorCase.limitations" :key="limit">{{ limit }}</li>
          </ul>
        </aside>
      </template>
    </section>

    <section class="evaluation" :data-status="evaluation.status">
      <h2>{{ evaluation.headline }}</h2>
      <p>{{ evaluation.detail }}</p>

      <template v-if="evaluation.status === 'ready'">
        <dl class="suite-meta">
          <div>
            <dt>Suite / profile</dt>
            <dd>{{ evaluation.suiteId }} / {{ evaluation.profile }}</dd>
          </div>
          <div>
            <dt>Acceptance</dt>
            <dd>{{ evaluation.acceptedLabel }}</dd>
          </div>
          <div>
            <dt>Determinism</dt>
            <dd>{{ evaluation.determinismLabel }}</dd>
          </div>
          <div>
            <dt>Results</dt>
            <dd>{{ evaluation.counts.passed }} passed · {{ evaluation.counts.failed }} failed · {{ evaluation.counts.unscored }} unscored / {{ evaluation.counts.total }}</dd>
          </div>
          <div class="hash-row">
            <dt>Report hash</dt>
            <dd><code>{{ evaluation.reportHash }}</code></dd>
          </div>
          <div class="hash-row">
            <dt>Snapshot hash</dt>
            <dd><code>{{ evaluation.snapshotHash }}</code></dd>
          </div>
        </dl>

        <div class="capability-badges" aria-label="Evaluation capability boundaries">
          <span v-for="label in evaluation.capabilityLabels" :key="label">{{ label }}</span>
        </div>

        <div class="evaluation-grid">
          <nav class="task-list" aria-label="Offline evaluation tasks">
            <button
              v-for="task in evaluation.tasks"
              :key="task.evaluationTaskId"
              type="button"
              :class="{ selected: task.evaluationTaskId === selectedEvaluationTaskId }"
              @click="selectEvaluationTask(task.evaluationTaskId)"
            >
              <span>{{ task.evaluationTaskId }}</span>
              <small>{{ task.result }} · gate {{ task.hardGateLabel }}</small>
            </button>
          </nav>

          <article class="task-detail">
            <p class="eyebrow">Selected task</p>
            <h3>{{ evaluation.selectedTask.evaluationTaskId }}</h3>
            <p>
              {{ evaluation.selectedTask.state }} → {{ evaluation.selectedTask.outcome }} ·
              quality {{ evaluation.selectedTask.qualityLabel }}
            </p>
            <dl>
              <div>
                <dt>Fixture</dt>
                <dd>{{ evaluation.selectedTask.fixtureId }}</dd>
              </div>
              <div class="hash-row">
                <dt>Safe source</dt>
                <dd><code>{{ evaluation.selectedTask.fixtureSourcePath }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>Fixture / task hash</dt>
                <dd><code>{{ evaluation.selectedTask.fixtureHash }} / {{ evaluation.selectedTask.taskHash }}</code></dd>
              </div>
              <div>
                <dt>Oracle</dt>
                <dd>{{ evaluation.selectedTask.oracleId }}</dd>
              </div>
              <div class="hash-row">
                <dt>Oracle hash</dt>
                <dd><code>{{ evaluation.selectedTask.oracleHash }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>Evaluation result</dt>
                <dd><code>{{ evaluation.selectedTask.evaluationResultId }}</code></dd>
              </div>
              <div>
                <dt>Failure classification</dt>
                <dd>{{ evaluation.selectedTask.failureClassification }}</dd>
              </div>
              <div>
                <dt>Evidence / approval</dt>
                <dd>{{ evaluation.selectedTask.evidenceLabel }} / {{ evaluation.selectedTask.approvalLabel }}</dd>
              </div>
              <div>
                <dt>Local effect</dt>
                <dd>{{ evaluation.selectedTask.localEffectLabel }}</dd>
              </div>
            </dl>

            <h4>Hard gates</h4>
            <ul class="evidence-list">
              <li v-for="gate in evaluation.selectedTask.gates" :key="gate.name">
                <strong>{{ gate.name }}</strong>: {{ gate.status }} ({{ gate.reasonCode }})
              </li>
            </ul>

            <h4>Quality dimensions</h4>
            <ul class="evidence-list">
              <li v-for="dimension in evaluation.selectedTask.dimensions" :key="dimension.name">
                <strong>{{ dimension.name }}</strong>: {{ dimension.score }}/100
              </li>
            </ul>

            <h4>Offline counters</h4>
            <ul class="evidence-list">
              <li v-for="counter in evaluation.selectedTask.counters" :key="counter.label">
                <strong>{{ counter.label }}</strong>: {{ counter.value }}
              </li>
            </ul>
          </article>
        </div>

        <aside class="unsupported">
          <h3>Unsupported live and customer metrics</h3>
          <ul>
            <li v-for="metric in evaluation.unsupportedMetrics" :key="metric">{{ metric }}</li>
          </ul>
        </aside>
      </template>
    </section>

    <section class="limits">
      <h2>Verified local limits</h2>
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
  max-width: 1180px;
  min-height: 100vh;
  padding: 72px 24px;
}

.hero, .status, .operator-case, .evaluation, .limits {
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

.evaluation[data-status="ready"] {
  border-color: #49b392;
}

.operator-case[data-status="ready"] {
  border-color: #49b392;
}

.operator-case[data-status="not-found"],
.operator-case[data-status="identity-denied"],
.operator-case[data-status="integrity-not-ready"],
.evaluation[data-status="not-found"],
.evaluation[data-status="identity-denied"],
.evaluation[data-status="integrity-not-ready"] {
  border-color: #d99b4b;
}

.suite-meta {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.operator-meta {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.hash-row {
  align-items: flex-start;
  flex-direction: column;
}

code {
  color: #9fb4d1;
  font-family: "Cascadia Code", "SFMono-Regular", monospace;
  font-size: 0.78rem;
  overflow-wrap: anywhere;
}

.capability-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 20px 0;
}

.capability-badges span {
  border: 1px solid #3c806f;
  border-radius: 999px;
  color: #9ce4d4;
  padding: 6px 10px;
}

.evaluation-grid {
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(250px, 0.85fr) minmax(0, 2fr);
}

.operator-grid {
  display: grid;
  gap: 20px;
  grid-template-columns: minmax(300px, 1fr) minmax(0, 1.4fr);
}

.task-list, .timeline-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.timeline-list {
  max-height: 760px;
  overflow: auto;
  padding-right: 4px;
}

.task-list button, .timeline-list button {
  background: #101827;
  border: 1px solid #2d3c56;
  border-radius: 10px;
  color: #e8edf8;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  text-align: left;
}

.task-list button.selected, .timeline-list button.selected {
  border-color: #49b392;
  box-shadow: inset 3px 0 #49b392;
}

.task-list small, .timeline-list small {
  color: #9fb4d1;
}

.task-detail, .operator-detail, .unsupported {
  background: #101827;
  border: 1px solid #2d3c56;
  border-radius: 12px;
  padding: 20px;
}

.task-detail h3, .task-detail h4,
.operator-detail h3, .operator-detail h4 {
  margin-bottom: 10px;
}

.evidence-list {
  color: #b7c5d9;
  padding-left: 20px;
}

.unsupported {
  margin-top: 20px;
}

.operator-limits {
  border-color: #6a5334;
}

.unsupported li {
  color: #d8bf99;
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

@media (max-width: 760px) {
  .shell {
    padding: 32px 16px;
  }

  .suite-meta, .operator-meta, .evaluation-grid, .operator-grid {
    grid-template-columns: 1fr;
  }
}
</style>
