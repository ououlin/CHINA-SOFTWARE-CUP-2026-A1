<template>
  <div class="agent-page">
    <!-- 输入区 -->
    <el-card shadow="never" class="input-card">
      <div class="input-row">
        <el-input v-model="query" type="textarea" :rows="2" resize="none"
                  placeholder="输入故障描述，Agent 将自主推理诊断…（如：发动机怠速不稳，冷车易熄火）"
                  @keydown.enter.exact.prevent="startDiagnose" />
        <el-button type="primary" :loading="running" @click="startDiagnose"
                   :icon="Position" :disabled="!query.trim() && !running">
          {{ running ? '推理中…' : '启动Agent诊断' }}
        </el-button>
      </div>
      <div class="examples">
        <span class="ex-label">示例：</span>
        <el-tag v-for="q in examples" :key="q" class="ex-tag" effect="plain"
                @click="query = q" size="small">{{ q }}</el-tag>
      </div>
    </el-card>

    <el-alert v-if="safety?.requires_human_confirmation"
              type="warning" :closable="false" show-icon
              title="高风险检修操作需人工确认" :description="safety.message" />

    <!-- 推理过程区 -->
    <div v-if="steps.length > 0" class="process-area">
      <div class="process-header">
        <el-icon class="rotating" v-if="running"><Loading /></el-icon>
        <el-icon v-else color="#67c23a"><CircleCheckFilled /></el-icon>
        <span class="ph-title">ReAct 推理过程</span>
        <el-tag size="small" type="info">{{ iterationCount }} 轮推理 · {{ toolCallCount }} 次工具调用</el-tag>
        <el-tag v-if="conflicts.length" size="small" type="warning">
          {{ conflicts.length }} 处证据冲突
        </el-tag>
      </div>

      <!-- 思考链 + 工具调用 时间线 -->
      <el-timeline class="timeline">
        <el-timeline-item v-for="(step, i) in steps" :key="i"
                          :type="stepType(step)" :hollow="step.phase === 'thought'"
                          :timestamp="`第${step.iteration || i+1}步`" placement="top">
          <!-- Thought -->
          <div v-if="step.phase === 'thought'" class="step thought">
            <div class="step-head">
              <el-icon color="#409eff"><Promotion /></el-icon>
              <span class="step-title">决策依据</span>
            </div>
            <div class="step-body thought-body">{{ step.thought }}</div>
          </div>

          <!-- Action + Observation -->
          <div v-else-if="step.phase === 'action'" class="step action">
            <div class="step-head">
              <el-icon :color="step.status === 'error' ? '#f56c6c' : '#67c23a'">
                <Tools v-if="step.status === 'ok'" /><WarnTriangleFilled v-else />
              </el-icon>
              <span class="step-title">Action · 工具调用</span>
              <el-tag size="small" effect="dark" :type="toolTagType(step.tool)">
                {{ toolLabel(step.tool) }}
              </el-tag>
            </div>
            <div class="step-body">
              <div class="action-input" v-if="step.input">
                <span class="lbl">输入：</span>
                <code>{{ step.input }}</code>
              </div>
              <div class="observation">
                <span class="lbl">观察结果：</span>
                <pre>{{ step.observation }}</pre>
              </div>
              <div v-if="step.citations && step.citations.length" class="action-cites">
                <el-tag v-for="(c, ci) in step.citations" :key="ci" size="small" effect="plain">
                  [E{{ ci+1 }}] {{ c.doc_title }} ({{ c.score }})
                </el-tag>
              </div>
            </div>
          </div>

          <!-- Report -->
          <div v-else-if="step.phase === 'report'" class="step report">
            <div class="step-head">
              <el-icon color="#945fb9"><Document /></el-icon>
              <span class="step-title">诊断报告</span>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>

      <!-- 证据冲突 -->
      <el-alert v-for="(c, i) in conflicts" :key="'cf-'+i"
                type="warning" :closable="false" class="conflict-alert"
                :title="`证据冲突 #${i+1}`" :description="c.description" show-icon>
        <template #default>
          <div class="conflict-detail">
            <p>{{ c.description }}</p>
            <p><strong>消解策略：</strong>{{ c.resolution }}</p>
          </div>
        </template>
      </el-alert>
    </div>

    <!-- 结果区 -->
    <el-row :gutter="14" v-if="report || reasoningChains.length" class="result-area">
      <!-- 诊断报告 -->
      <el-col :span="report ? 14 : 24" v-if="report">
        <el-card shadow="never" class="report-card">
          <template #header>
            <div class="card-h">
              <el-icon color="#945fb9"><Document /></el-icon>
              <span>结构化诊断报告</span>
              <el-tag v-if="confidence" size="small" :type="confTagType(confidence.level)">
                置信度 {{ Math.round((confidence.score || 0) * 100) }}分
              </el-tag>
            </div>
          </template>
          <div class="report-body markdown-body" v-html="renderMarkdown(report)"></div>
          <div v-if="confidence" class="conf-box">
            <div v-if="confidence.reasons?.length" class="conf-reasons">
              <el-tag v-for="r in confidence.reasons" :key="r" size="small" effect="plain">{{ r }}</el-tag>
            </div>
            <div v-if="confidence.warnings?.length" class="conf-warnings">
              <span v-for="w in confidence.warnings" :key="w">⚠️ {{ w }}</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 推理链 Sankey -->
      <el-col :span="10" v-if="reasoningChains.length">
        <el-card shadow="never" class="chain-card">
          <template #header>
            <div class="card-h">
              <el-icon color="#7c5bbf"><Share /></el-icon>
              <span>知识图谱推理链</span>
              <el-tag size="small" type="info">{{ reasoningChains.length }} 条</el-tag>
            </div>
          </template>
          <div ref="chainEl" class="chain-chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 故障树 FTA -->
    <el-card shadow="never" v-if="ftTree" class="fta-card">
      <template #header>
        <div class="card-h">
          <el-icon color="#fa9d3b"><Connection /></el-icon>
          <span>故障树分析（FTA）</span>
          <el-tag size="small" type="warning">{{ ftStats.total_nodes }} 节点 · {{ ftStats.cause_nodes }} 原因 · {{ ftStats.measure_count }} 措施</el-tag>
        </div>
      </template>
      <div ref="ftaEl" class="fta-chart"></div>
    </el-card>

    <!-- 空状态 -->
    <div v-if="steps.length === 0 && !running" class="empty-state">
      <div class="empty-illus">
        <el-icon :size="64" color="var(--brand)"><Cpu /></el-icon>
      </div>
      <h3>ReAct 自主诊断引擎</h3>
      <p>Agent 将模拟专家诊断思路，自主选择工具、多步推理、交叉验证，输出结构化诊断报告。</p>
      <div class="flow-diagram">
        <div class="flow-step" v-for="(s, i) in flowSteps" :key="i">
          <div class="fs-icon" :style="{background: s.color}"><el-icon><component :is="s.icon" /></el-icon></div>
          <div class="fs-label">{{ s.label }}</div>
          <el-icon v-if="i < flowSteps.length - 1" class="fs-arrow"><Right /></el-icon>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  Position, Loading, CircleCheckFilled, Promotion, Tools, WarnTriangleFilled,
  Document, Share, Right, Cpu, Search, View, Setting, Files, Connection,
} from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { echarts } from '../lib/chart'
import api from '../api'
import { useAuthStore } from '../store'

marked.setOptions({ breaks: true, gfm: true })

const auth = useAuthStore()
const route = useRoute()
const query = ref('')

onMounted(() => {
  const q = route.query.q
  if (q) {
    query.value = q
    startDiagnose()
  }
})
const running = ref(false)
const steps = ref([])
const report = ref('')
const confidence = ref(null)
const safety = ref(null)
const reasoningChains = ref([])
const conflicts = ref([])
const ftTree = ref(null)
const ftStats = ref({})
const iterationCount = ref(0)
const toolCallCount = ref(0)

const chainEl = ref(null)
const ftaEl = ref(null)
let chainChart = null
let ftaChart = null

const examples = [
  '发动机怠速不稳，冷车易熄火',
  '发动机过热怎么处理',
  '螺杆空压机排气压力不足',
  '数控机床主轴轴承异响',
]

const flowSteps = [
  { label: '问题分析', icon: Promotion, color: '#409eff' },
  { label: '检索手册', icon: Files, color: '#67c23a' },
  { label: '查询图谱', icon: Share, color: '#7c5bbf' },
  { label: '交叉验证', icon: View, color: '#fa9d3b' },
  { label: '诊断报告', icon: Document, color: '#f6685e' },
]

function renderMarkdown(text) {
  if (!text) return ''
  return DOMPurify.sanitize(marked.parse(text))
}

function stepType(step) {
  if (step.phase === 'thought') return 'primary'
  if (step.phase === 'action') return step.status === 'error' ? 'danger' : 'success'
  if (step.phase === 'report') return 'warning'
  return 'info'
}

function toolLabel(tool) {
  const labels = {
    search_manual: '检索手册',
    search_case: '检索案例',
    query_graph: '查询图谱',
    query_device_history: '设备历史',
  }
  return labels[tool] || tool
}

function toolTagType(tool) {
  const types = {
    search_manual: 'success',
    search_case: 'success',
    query_graph: 'warning',
    query_device_history: 'info',
  }
  return types[tool] || ''
}

function confTagType(level) {
  return { high: 'success', medium: 'warning', low: 'danger' }[level] || 'info'
}

async function startDiagnose() {
  const q = query.value.trim()
  if (!q || running.value) return

  running.value = true
  steps.value = []
  report.value = ''
  confidence.value = null
  safety.value = null
  reasoningChains.value = []
  conflicts.value = []
  ftTree.value = null
  ftStats.value = {}
  iterationCount.value = 0
  toolCallCount.value = 0

  try {
    const resp = await fetch('/api/chat/diagnose_stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({ query: q }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail?.message || err.detail || '请求失败')
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const blocks = buf.split('\n\n')
      buf = blocks.pop()
      for (const block of blocks) {
        handleEvent(block)
      }
    }

    // 推理结束后，获取故障树
    await loadFaultTree(q)
    // 获取推理链用于可视化
    await loadReasoningChains(q)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}

function handleEvent(block) {
  const lines = block.split('\n')
  let event = 'message'
  let data = ''
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return
  try {
    const parsed = JSON.parse(data)
    if (event === 'thought') {
      steps.value.push(parsed)
      iterationCount.value = parsed.iteration || iterationCount.value + 1
    } else if (event === 'action') {
      steps.value.push(parsed)
      toolCallCount.value++
    } else if (event === 'report') {
      report.value = parsed.report || ''
      if (parsed.reasoning_chains) reasoningChains.value = parsed.reasoning_chains
      if (parsed.conflicts) conflicts.value = parsed.conflicts
      steps.value.push({ phase: 'report', iteration: iterationCount.value + 1 })
    } else if (event === 'confidence') {
      confidence.value = parsed
    } else if (event === 'safety') {
      safety.value = parsed
    } else if (event === 'error') {
      ElMessage.error(parsed)
    }
  } catch (e) {}
}

async function loadReasoningChains(q) {
  try {
    const { data } = await api.get('/kg/reasoning', { params: { query: q } })
    reasoningChains.value = data.chains || []
    if (reasoningChains.value.length) {
      await nextTick()
      renderChainChart()
    }
  } catch (e) {}
}

async function loadFaultTree(q) {
  try {
    const { data } = await api.get('/kg/fault_tree', { params: { query: q, max_depth: 3 } })
    if (data && data.tree) {
      ftTree.value = data.tree
      ftStats.value = data.stats || {}
      await nextTick()
      renderFTAChart()
    }
  } catch (e) {}
}

function renderChainChart() {
  if (!chainEl.value) return
  if (!chainChart) chainChart = echarts.init(chainEl.value)

  // 构建 Sankey 数据
  const nodeSet = new Map()
  const links = []
  const colors = { fault: '#f6685e', cause: '#fa9d3b', measure: '#945fb9' }

  for (const chain of reasoningChains.value) {
    for (let i = 0; i < chain.length; i++) {
      const name = chain[i]
      if (!nodeSet.has(name)) {
        const type = i === 0 ? 'fault' : (i === chain.length - 1 && chain.length === 3 ? 'measure' : 'cause')
        nodeSet.set(name, { name, itemStyle: { color: colors[type] || '#909399' } })
      }
    }
    for (let i = 0; i < chain.length - 1; i++) {
      links.push({ source: chain[i], target: chain[i + 1], value: 1 })
    }
  }

  chainChart.setOption({
    tooltip: { trigger: 'item' },
    series: [{
      type: 'sankey',
      layout: 'none',
      emphasis: { focus: 'adjacency' },
      nodeAlign: 'left',
      data: [...nodeSet.values()],
      links,
      lineStyle: { color: 'gradient', curveness: 0.5 },
      label: { fontSize: 12, color: 'var(--ink)' },
    }],
  })
}

function renderFTAChart() {
  if (!ftaEl.value) return
  if (!ftaChart) ftaChart = echarts.init(ftaEl.value)

  // 转换为 ECharts tree 格式
  function convert(node) {
    const colors = { fault: '#f6685e', cause: '#fa9d3b', measure: '#945fb9' }
    const result = {
      name: node.name,
      value: node.confidence,
      itemStyle: { color: colors[node.type] || '#909399' },
      label: {
        formatter: `{b}\n可信度: ${(node.confidence * 100).toFixed(0)}%`,
        fontSize: 11,
      },
    }
    if (node.measures && node.measures.length) {
      result.label = {
        ...result.label,
        formatter: `{b}\n可信度: ${(node.confidence * 100).toFixed(0)}%\n措施: ${node.measures.join(', ')}`,
      }
    }
    if (node.children && node.children.length) {
      result.children = node.children.map(convert)
    }
    return result
  }

  ftaChart.setOption({
    tooltip: { trigger: 'item', formatter: (p) => p.data.value ? `${p.name}<br/>可信度: ${(p.data.value * 100).toFixed(0)}%` : p.name },
    series: [{
      type: 'tree',
      data: [convert(ftTree.value)],
      top: '5%', left: '15%', bottom: '5%', right: '15%',
      symbolSize: 10,
      orient: 'LR',
      label: { position: 'left', verticalAlign: 'middle', align: 'right', fontSize: 11 },
      leaves: { label: { position: 'right', align: 'left' } },
      emphasis: { focus: 'descendant' },
      expandAndCollapse: true,
      animationDuration: 550,
    }],
  })
}

function onResize() {
  chainChart?.resize()
  ftaChart?.resize()
}

window.addEventListener('resize', onResize)
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chainChart?.dispose()
  ftaChart?.dispose()
})
</script>

<style scoped>
.agent-page { display: flex; flex-direction: column; gap: 14px; height: 100%; overflow-y: auto; }

.input-card :deep(.el-card__body) { padding: 14px 18px; }
.input-row { display: flex; gap: 12px; align-items: flex-start; }
.input-row .el-button { height: 60px; }
.examples { margin-top: 10px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ex-label { font-size: 12px; color: var(--muted); }
.ex-tag { cursor: pointer; }

.process-area { background: var(--bg-surface); border: 1px solid var(--bd); border-radius: 10px; padding: 16px 20px; }
.process-header { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.rotating { animation: rotateSpin 1s linear infinite; }
@keyframes rotateSpin { from { transform: rotate(0); } to { transform: rotate(360deg); } }
.ph-title { font-size: 15px; font-weight: 700; color: var(--ink); flex: 1; }

.timeline { padding-left: 10px; }
.step { padding: 4px 0; }
.step-head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.step-title { font-weight: 600; font-size: 13px; color: var(--ink); }
.step-body { font-size: 13px; color: var(--ink-soft); line-height: 1.7; padding-left: 22px; }
.thought-body { background: rgba(64,158,255,.06); border-left: 3px solid #409eff; border-radius: 0 6px 6px 0; padding: 8px 12px; margin: 4px 0 4px 22px; }

.action-input { margin-bottom: 6px; }
.action-input .lbl, .observation .lbl { font-size: 12px; color: var(--muted); font-weight: 600; }
.action-input code { font-size: 12px; background: var(--bg-surface-2); padding: 2px 6px; border-radius: 4px; }
.observation { margin-top: 4px; }
.observation pre { font-size: 12px; white-space: pre-wrap; word-break: break-word; background: rgba(103,194,58,.06); border-left: 3px solid #67c23a; border-radius: 0 6px 6px 0; padding: 8px 12px; margin: 4px 0; line-height: 1.6; }
.action-cites { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }

.conflict-alert { margin-top: 10px; }
.conflict-detail p { margin: 4px 0; font-size: 12px; }

.result-area { margin-top: 0; }
.card-h { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.report-card :deep(.el-card__header) { padding: 10px 16px; }
.report-body { line-height: 1.8; color: var(--ink); }
.report-body :deep(h2) { font-size: 16px; margin: 14px 0 8px; font-weight: 700; color: var(--ink); border-bottom: 1px solid var(--bd); padding-bottom: 4px; }
.report-body :deep(h3) { font-size: 14px; margin: 10px 0 6px; font-weight: 600; }
.report-body :deep(p) { margin: 6px 0; }
.report-body :deep(ul), .report-body :deep(ol) { padding-left: 20px; }
.report-body :deep(li) { margin: 3px 0; }
.report-body :deep(strong) { color: var(--brand-deep); }
html.dark .report-body :deep(strong) { color: var(--brand); }
.conf-box { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--bd); }
.conf-reasons { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.conf-warnings { display: flex; flex-direction: column; gap: 4px; }
.conf-warnings span { font-size: 12px; color: #e6a23c; }

.chain-card :deep(.el-card__header) { padding: 10px 16px; }
.chain-chart { height: 300px; }

.fta-card { margin-top: 0; }
.fta-card :deep(.el-card__header) { padding: 10px 16px; }
.fta-chart { height: 400px; }

.empty-state { text-align: center; padding: 40px 20px; color: var(--muted); }
.empty-illus {
  width: 96px; height: 96px; border-radius: 50%; margin: 0 auto 18px;
  background: var(--bubble-ai); display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px rgba(31,111,235,.14);
  animation: breath 2.6s ease-in-out infinite;
}
@keyframes breath { 0%,100% { transform: scale(1); } 50% { transform: scale(1.05); } }
.empty-state h3 { font-size: 20px; font-weight: 700; color: var(--ink); margin: 0 0 8px; }
.empty-state p { font-size: 14px; max-width: 520px; margin: 0 auto 24px; line-height: 1.7; }

.flow-diagram { display: flex; align-items: center; justify-content: center; gap: 0; flex-wrap: wrap; }
.flow-step { display: flex; align-items: center; gap: 6px; }
.fs-icon {
  width: 48px; height: 48px; border-radius: 12px; display: flex;
  align-items: center; justify-content: center; color: #fff; font-size: 20px;
}
.fs-label { font-size: 13px; color: var(--ink-soft); margin-right: 8px; }
.fs-arrow { color: var(--muted); font-size: 16px; margin: 0 6px; }
</style>
