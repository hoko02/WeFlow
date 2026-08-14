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
const message = ref("正在检查本地 Platform API fixture 控制端点。");
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
    message.value = "Platform API 尚未运行。请使用 scripts/dev.py up --mode offline 启动本地服务。";
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
      <p class="eyebrow">WEFLOW / 离线运营证据</p>
      <h1>运营案例与评测控制台</h1>
      <p>此本地控制台展示一条源记录关联的 API-503 案例时间线、重新验证的 12 项 Replay 基准，以及基础设施就绪状态。它不会将 fixture 投递记录视为真实提供方发送、客户签收、事件解决、完成或授权。</p>
    </section>

    <section class="status" :data-status="status">
      <h2>{{ renderedStatus?.headline ?? `运行状态：${status === "checking" ? "检查中" : "未就绪"}` }}</h2>
      <p>{{ message }}</p>
      <p v-if="renderedStatus">运行模式：{{ renderedStatus.modeLabel }}</p>
      <p v-if="renderedStatus?.policyDenial">
        提供方/配置能力被拒绝：{{ renderedStatus.policyDenial.capability }}（{{ renderedStatus.policyDenial.reasonCode }}）
      </p>
      <dl v-if="capabilities">
        <div>
          <dt>业务工作流已实现</dt>
          <dd>{{ capabilities.business_workflow_implemented ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>已启用外部写入</dt>
          <dd>{{ capabilities.external_writes_enabled ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>合成案例接入已实现</dt>
          <dd>{{ capabilities.synthetic_case_intake_implemented ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>fixture-local 持久化工作流已实现</dt>
          <dd>{{ capabilities.durable_support_workflow_implemented ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>Replay 调查 Agent 已实现</dt>
          <dd>{{ capabilities.replay_investigation_agent_implemented ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>回复候选验证器已实现</dt>
          <dd>{{ capabilities.response_candidate_verification_implemented ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>已启用实时提供方</dt>
          <dd>{{ capabilities.real_provider_enabled ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>fixture 策略/审批/投递已实现</dt>
          <dd>{{ capabilities.fixture_policy_approval_delivery_implemented ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>已启用 fixture 审批和本地投递</dt>
          <dd>{{ (capabilities.fixture_approval_enabled && capabilities.fixture_outbound_delivery_enabled) ? "是" : "否" }}</dd>
        </div>
        <div>
          <dt>已启用实时审批、实时投递或客户问题解决</dt>
          <dd>{{ (capabilities.live_approval_enabled || capabilities.live_outbound_delivery_enabled || capabilities.customer_resolution_enabled) ? "是" : "否" }}</dd>
        </div>
      </dl>
    </section>

    <section class="operator-case" :data-status="operatorCase.status">
      <p class="eyebrow">运营案例 / 离线合成证据</p>
      <h2>{{ operatorCase.headline }}</h2>
      <p>{{ operatorCase.detail }}</p>

      <template v-if="operatorCase.status === 'ready'">
        <dl class="operator-meta">
          <div>
            <dt>测试数据（fixture）</dt>
            <dd>{{ operatorCase.fixtureId }}</dd>
          </div>
          <div>
            <dt>当前 fixture 状态</dt>
            <dd>{{ operatorCase.currentStateLabel }}</dd>
          </div>
          <div class="hash-row">
            <dt>案例 / 修订</dt>
            <dd><code>{{ operatorCase.caseId }} / {{ operatorCase.revisionId }} (r{{ operatorCase.revision }})</code></dd>
          </div>
          <div class="hash-row">
            <dt>工作流</dt>
            <dd><code>{{ operatorCase.workflowId }} (v{{ operatorCase.workflowVersion }})</code></dd>
          </div>
          <div class="hash-row">
            <dt>快照 / 源报告哈希</dt>
            <dd><code>{{ operatorCase.snapshotHash }} / {{ operatorCase.reportHash }}</code></dd>
          </div>
          <div class="hash-row">
            <dt>证据根 / Replay 结果</dt>
            <dd><code>{{ operatorCase.evidenceRoot }} / {{ operatorCase.replayHash }}</code></dd>
          </div>
        </dl>

        <div class="capability-badges" aria-label="运营案例能力边界">
          <span v-for="label in operatorCase.capabilityLabels" :key="label">{{ label }}</span>
        </div>

        <div class="operator-grid">
          <nav class="timeline-list" aria-label="API-503 源记录关联案例时间线">
            <button
              v-for="entry in operatorCase.timeline"
              :key="entry.entryId"
              type="button"
              :class="{ selected: entry.entryId === selectedOperatorEntryId }"
              @click="selectOperatorEntry(entry.entryId)"
            >
              <span><strong>{{ entry.sequence }}</strong> · {{ entry.phase }} / {{ entry.sourceKind }}</span>
              <small>{{ entry.transitionLabel }} · 门禁 {{ entry.gateLabel }} · 恢复 {{ entry.recoveryLabel }}</small>
            </button>
          </nav>

          <article class="operator-detail">
            <p class="eyebrow">选中的源记录关联条目</p>
            <h3>{{ operatorCase.selectedEntry.phase }} / {{ operatorCase.selectedEntry.sourceKind }}</h3>
            <p>{{ operatorCase.selectedEntry.transitionLabel }} · {{ operatorCase.selectedEntry.result }}</p>
            <dl>
              <div>
                <dt>序号</dt>
                <dd>{{ operatorCase.selectedEntry.sequence }}</dd>
              </div>
              <div class="hash-row">
                <dt>条目 ID</dt>
                <dd><code>{{ operatorCase.selectedEntry.entryId }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>源记录 ID</dt>
                <dd><code>{{ operatorCase.selectedEntry.sourceId }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>源记录哈希</dt>
                <dd><code>{{ operatorCase.selectedEntry.sourceHash }}</code></dd>
              </div>
              <div>
                <dt>分类</dt>
                <dd>{{ operatorCase.selectedEntry.classification }}</dd>
              </div>
              <div>
                <dt>观测值 / 结果</dt>
                <dd>{{ operatorCase.selectedEntry.observation }} / {{ operatorCase.selectedEntry.result }}</dd>
              </div>
              <div>
                <dt>门禁 / 恢复</dt>
                <dd>{{ operatorCase.selectedEntry.gateLabel }} / {{ operatorCase.selectedEntry.recoveryLabel }}</dd>
              </div>
              <div>
                <dt>原因码</dt>
                <dd>{{ operatorCase.selectedEntry.reasonCode }}</dd>
              </div>
            </dl>

            <h4>受限源记录计数</h4>
            <ul class="evidence-list">
              <li v-for="count in operatorCase.countLabels" :key="count.label">
                <strong>{{ count.label }}</strong>: {{ count.value }}
              </li>
            </ul>
          </article>
        </div>

        <aside class="unsupported operator-limits">
          <h3>明确的能力限制</h3>
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
            <dt>评测套件 / 配置</dt>
            <dd>{{ evaluation.suiteId }} / {{ evaluation.profile }}</dd>
          </div>
          <div>
            <dt>验收</dt>
            <dd>{{ evaluation.acceptedLabel }}</dd>
          </div>
          <div>
            <dt>确定性</dt>
            <dd>{{ evaluation.determinismLabel }}</dd>
          </div>
          <div>
            <dt>结果</dt>
            <dd>{{ evaluation.counts.passed }} 通过 · {{ evaluation.counts.failed }} 失败 · {{ evaluation.counts.unscored }} 未评分 / {{ evaluation.counts.total }}</dd>
          </div>
          <div class="hash-row">
            <dt>报告哈希</dt>
            <dd><code>{{ evaluation.reportHash }}</code></dd>
          </div>
          <div class="hash-row">
            <dt>快照哈希</dt>
            <dd><code>{{ evaluation.snapshotHash }}</code></dd>
          </div>
        </dl>

        <div class="capability-badges" aria-label="评测能力边界">
          <span v-for="label in evaluation.capabilityLabels" :key="label">{{ label }}</span>
        </div>

        <div class="evaluation-grid">
          <nav class="task-list" aria-label="离线评测任务">
            <button
              v-for="task in evaluation.tasks"
              :key="task.evaluationTaskId"
              type="button"
              :class="{ selected: task.evaluationTaskId === selectedEvaluationTaskId }"
              @click="selectEvaluationTask(task.evaluationTaskId)"
            >
              <span>{{ task.evaluationTaskId }}</span>
              <small>{{ task.result }} · 门禁 {{ task.hardGateLabel }}</small>
            </button>
          </nav>

          <article class="task-detail">
            <p class="eyebrow">选中的任务</p>
            <h3>{{ evaluation.selectedTask.evaluationTaskId }}</h3>
            <p>
              {{ evaluation.selectedTask.state }} → {{ evaluation.selectedTask.outcome }} ·
              质量 {{ evaluation.selectedTask.qualityLabel }}
            </p>
            <dl>
              <div>
                <dt>测试数据（fixture）</dt>
                <dd>{{ evaluation.selectedTask.fixtureId }}</dd>
              </div>
              <div class="hash-row">
                <dt>安全源路径</dt>
                <dd><code>{{ evaluation.selectedTask.fixtureSourcePath }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>测试数据 / 任务哈希</dt>
                <dd><code>{{ evaluation.selectedTask.fixtureHash }} / {{ evaluation.selectedTask.taskHash }}</code></dd>
              </div>
              <div>
                <dt>评分规则（Oracle）</dt>
                <dd>{{ evaluation.selectedTask.oracleId }}</dd>
              </div>
              <div class="hash-row">
                <dt>评分规则哈希</dt>
                <dd><code>{{ evaluation.selectedTask.oracleHash }}</code></dd>
              </div>
              <div class="hash-row">
                <dt>评测结果</dt>
                <dd><code>{{ evaluation.selectedTask.evaluationResultId }}</code></dd>
              </div>
              <div>
                <dt>失败分类</dt>
                <dd>{{ evaluation.selectedTask.failureClassification }}</dd>
              </div>
              <div>
                <dt>证据 / 审批</dt>
                <dd>{{ evaluation.selectedTask.evidenceLabel }} / {{ evaluation.selectedTask.approvalLabel }}</dd>
              </div>
              <div>
                <dt>本地副作用</dt>
                <dd>{{ evaluation.selectedTask.localEffectLabel }}</dd>
              </div>
            </dl>

            <h4>硬门禁</h4>
            <ul class="evidence-list">
              <li v-for="gate in evaluation.selectedTask.gates" :key="gate.name">
                <strong>{{ gate.name }}</strong>: {{ gate.status }} ({{ gate.reasonCode }})
              </li>
            </ul>

            <h4>质量维度</h4>
            <ul class="evidence-list">
              <li v-for="dimension in evaluation.selectedTask.dimensions" :key="dimension.name">
                <strong>{{ dimension.name }}</strong>: {{ dimension.score }}/100
              </li>
            </ul>

            <h4>离线计数器</h4>
            <ul class="evidence-list">
              <li v-for="counter in evaluation.selectedTask.counters" :key="counter.label">
                <strong>{{ counter.label }}</strong>: {{ counter.value }}
              </li>
            </ul>
          </article>
        </div>

        <aside class="unsupported">
          <h3>不支持的实时与客户指标</h3>
          <ul>
            <li v-for="metric in evaluation.unsupportedMetrics" :key="metric">{{ metric }}</li>
          </ul>
        </aside>
      </template>
    </section>

    <section class="limits">
      <h2>已验证的本地限制</h2>
      <ul>
        <li>仅一个确定性 Replay Agent 可使用已检入的 API-503 fixture。</li>
        <li>只有 CRM、监控和知识库 fixture 的只读查询可以生成脱敏证据哈希。</li>
        <li>确定性验证器最多推进到 RESPONSE_READY；只有显式且哈希绑定的 fixture 激活才可继续进入审批。</li>
        <li>一个 fixture-local 适配器可在策略和审批后记录幂等本地投递；它不是网络调用，也不代表客户成功。</li>
        <li>实时提供方、凭据、多 Agent 协作、真实审批、真实投递、外部写入和客户问题解决仍保持禁用。</li>
      </ul>
    </section>
  </main>
</template>

<style>
:root {
  color: #e8edf8;
  background: #101827;
  font-family: Inter, "Microsoft YaHei", "Segoe UI", sans-serif;
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
