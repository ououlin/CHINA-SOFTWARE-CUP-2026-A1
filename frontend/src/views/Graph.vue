<template>
  <div class="kg-page">
    <el-card shadow="never" class="toolbar">
      <div class="bar">
        <div class="stats">
          <span class="title">设备检修知识图谱</span>
          <el-tag v-for="t in TYPES" :key="t.key" :color="t.color" effect="dark"
                  class="stat-tag" size="small">
            {{ t.label }} {{ stats[t.key] || 0 }}
          </el-tag>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="loadGraph">刷新</el-button>
      </div>
    </el-card>

    <div class="graph-wrap" v-loading="loading">
      <div ref="chartEl" class="chart"></div>
      <el-empty v-if="!loading && nodes.length === 0" class="empty"
                description="暂无知识图谱，请先在「检修案例」中采纳案例" />
    </div>

    <!-- 节点溯源抽屉 -->
    <el-drawer v-model="drawer" size="420px" :destroy-on-close="true">
      <template #header>
        <div class="dh">
          <el-tag :color="typeColor(current?.etype)" effect="dark" size="small">
            {{ typeLabel(current?.etype) }}
          </el-tag>
          <span class="dname">{{ current?.name }}</span>
        </div>
      </template>
      <div v-loading="nodeLoading" class="node-detail">
        <el-divider content-position="left">相关案例（溯源）</el-divider>
        <el-empty v-if="cases.length === 0" :image-size="60" description="暂无关联案例" />
        <div v-for="c in cases" :key="c.id" class="case-row">
          <el-icon><Document /></el-icon>
          <span class="ct">{{ c.title }}</span>
          <el-tag size="small" effect="plain" type="info">{{ c.device_model || '—' }}</el-tag>
        </div>

        <el-divider content-position="left">相邻实体</el-divider>
        <div class="neighbors">
          <el-tag v-for="n in neighbors" :key="n.id" :color="typeColor(n.etype)"
                  effect="plain" class="nb" @click="jumpNode(n)">
            {{ n.name }}
          </el-tag>
          <span v-if="neighbors.length === 0" class="muted">无</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Document } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api from '../api'

const TYPES = [
  { key: 'device', label: '设备', color: '#5b8ff9' },
  { key: 'part', label: '部件', color: '#5ad8a6' },
  { key: 'fault', label: '故障', color: '#f6685e' },
  { key: 'cause', label: '原因', color: '#fa9d3b' },
  { key: 'measure', label: '措施', color: '#945fb9' },
]
const typeIndex = (k) => TYPES.findIndex((t) => t.key === k)
const typeLabel = (k) => TYPES.find((t) => t.key === k)?.label || k
const typeColor = (k) => TYPES.find((t) => t.key === k)?.color || '#909399'

const chartEl = ref(null)
let chart = null
const loading = ref(false)
const nodes = ref([])
const links = ref([])
const stats = reactive({})

function renderChart() {
  if (!chart) return
  const option = {
    color: TYPES.map((t) => t.color),
    tooltip: {
      formatter: (p) => (p.dataType === 'edge'
        ? `${p.data.srcName} —${p.data.rel}→ ${p.data.dstName}`
        : `${typeLabel(p.data.etype)}：${p.data.name}`),
    },
    legend: [{
      data: TYPES.map((t) => t.label), top: 8,
      textStyle: { color: '#555' },
    }],
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      categories: TYPES.map((t) => ({ name: t.label })),
      label: { show: true, position: 'right', fontSize: 12, color: '#303133' },
      edgeLabel: { show: true, formatter: (p) => p.data.rel, fontSize: 10, color: '#909399' },
      force: { repulsion: 320, edgeLength: 120, gravity: 0.05 },
      lineStyle: { color: '#c0c4cc', width: 1.2, curveness: 0.06 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
      data: nodes.value.map((n) => ({
        id: String(n.id), name: n.name, etype: n.etype,
        category: typeIndex(n.etype),
        symbolSize: 22 + (n.degree || 0) * 7,
        value: n.degree,
      })),
      links: links.value.map((l) => ({
        source: String(l.source), target: String(l.target), rel: l.rel,
        srcName: nameOf(l.source), dstName: nameOf(l.target),
      })),
    }],
  }
  chart.setOption(option)
}

function nameOf(id) {
  return nodes.value.find((n) => n.id === id)?.name || id
}

async function loadGraph() {
  loading.value = true
  try {
    const { data } = await api.get('/kg/graph')
    nodes.value = data.nodes || []
    links.value = data.links || []
    Object.keys(stats).forEach((k) => delete stats[k])
    Object.assign(stats, data.stats || {})
    await nextTick()
    renderChart()
  } catch (e) {
    ElMessage.error('加载知识图谱失败')
  } finally {
    loading.value = false
  }
}

// ---- 节点溯源 ----
const drawer = ref(false)
const nodeLoading = ref(false)
const current = ref(null)
const cases = ref([])
const neighbors = ref([])

async function openNode(id) {
  drawer.value = true
  nodeLoading.value = true
  cases.value = []
  neighbors.value = []
  try {
    const { data } = await api.get(`/kg/entities/${id}/cases`)
    current.value = data.entity
    cases.value = data.cases || []
    neighbors.value = data.neighbors || []
  } catch (e) {
    ElMessage.error('加载节点详情失败')
  } finally {
    nodeLoading.value = false
  }
}
const jumpNode = (n) => openNode(n.id)

function onResize() {
  chart && chart.resize()
}

onMounted(async () => {
  await nextTick()
  chart = echarts.init(chartEl.value)
  chart.on('click', (p) => {
    if (p.dataType === 'node') openNode(Number(p.data.id))
  })
  window.addEventListener('resize', onResize)
  await loadGraph()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart && chart.dispose()
  chart = null
})
</script>

<style scoped>
.kg-page { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.toolbar :deep(.el-card__body) { padding: 10px 16px; }
.bar { display: flex; align-items: center; justify-content: space-between; }
.stats { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.stats .title { font-weight: 600; margin-right: 6px; }
.stat-tag { color: #fff; border: none; }
.graph-wrap {
  position: relative; flex: 1; min-height: 520px;
  background: #fff; border-radius: 8px; border: 1px solid #ebeef5;
}
.chart { width: 100%; height: 100%; min-height: 520px; }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
.dh { display: flex; align-items: center; gap: 10px; }
.dname { font-size: 16px; font-weight: 600; }
.node-detail { padding: 2px 4px; }
.stat-tag, .dh :deep(.el-tag) { color: #fff; border: none; }
.case-row {
  display: flex; align-items: center; gap: 8px; padding: 7px 0;
  color: #303133; font-size: 14px;
}
.case-row .ct { flex: 1; }
.neighbors { display: flex; flex-wrap: wrap; gap: 8px; }
.neighbors .nb { color: #fff; border: none; cursor: pointer; }
.muted { color: #c0c4cc; }
</style>
