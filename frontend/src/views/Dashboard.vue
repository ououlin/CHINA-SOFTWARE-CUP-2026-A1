<template>
  <div class="dash" v-loading="loading">
    <!-- 指标卡片 -->
    <div class="cards">
      <div v-for="c in cardDefs" :key="c.key" class="card" :style="{ '--accent': c.color }">
        <div class="ic"><el-icon :size="22"><component :is="c.icon" /></el-icon></div>
        <div class="info">
          <div class="num">{{ cardValue(c) }}</div>
          <div class="lbl">{{ c.label }}</div>
        </div>
        <div v-if="c.sub" class="sub">{{ c.sub() }}</div>
      </div>
    </div>

    <!-- 图表区 -->
    <el-row :gutter="14" class="row">
      <el-col :span="16">
        <div class="panel">
          <div class="ptitle">近 7 天问答 / 报修趋势</div>
          <div ref="trendEl" class="chart"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="panel">
          <div class="ptitle">设备状态分布</div>
          <div ref="statusEl" class="chart"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="14" class="row">
      <el-col :span="12">
        <div class="panel">
          <div class="ptitle">高故障设备榜 Top5</div>
          <div ref="faultEl" class="chart"></div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="panel">
          <div class="ptitle">知识图谱实体分布</div>
          <div ref="kgEl" class="chart"></div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Monitor, Warning, Collection, EditPen, Tickets, ChatDotRound, Star, Share,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api from '../api'

const loading = ref(false)
const cards = reactive({})

const cardDefs = [
  { key: 'device_total', label: '设备总数', icon: Monitor, color: '#14418c' },
  { key: 'open_records', label: '未结报修', icon: Warning, color: '#f56c6c' },
  { key: 'doc_total', label: '知识库文档', icon: Collection, color: '#409eff' },
  { key: 'case_total', label: '检修案例', icon: EditPen, color: '#67c23a',
    sub: () => `待审 ${cards.case_pending || 0}` },
  { key: 'sop_total', label: '作业指引', icon: Tickets, color: '#e6a23c',
    sub: () => `已执行 ${cards.sop_run_total || 0}` },
  { key: 'qa_total', label: '智能问答', icon: ChatDotRound, color: '#9254de' },
  { key: 'satisfaction', label: '问答满意度', icon: Star, color: '#13c2c2', pct: true },
  { key: 'kg_entities', label: '图谱实体', icon: Share, color: '#5ad8a6',
    sub: () => `关系 ${cards.kg_relations || 0}` },
]
function cardValue(c) {
  const v = cards[c.key]
  if (c.pct) return v == null ? '—' : v + '%'
  return v ?? 0
}

const trendEl = ref(null)
const statusEl = ref(null)
const faultEl = ref(null)
const kgEl = ref(null)
const charts = {}

const TYPE_COLORS = ['#5b8ff9', '#5ad8a6', '#f6685e', '#fa9d3b', '#945fb9']
const STATUS_COLORS = { 运行中: '#5ad8a6', 维修中: '#fa9d3b', 停机: '#c0c4cc', 报废: '#f6685e' }

function renderTrend(trend) {
  charts.trend.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['问答', '报修'], top: 4, textStyle: { color: '#666' } },
    grid: { left: 36, right: 16, top: 38, bottom: 28 },
    xAxis: { type: 'category', data: trend.dates, axisLine: { lineStyle: { color: '#ccc' } } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f2f5' } } },
    series: [
      { name: '问答', type: 'line', smooth: true, data: trend.qa, symbolSize: 7,
        itemStyle: { color: '#14418c' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
          [{ offset: 0, color: 'rgba(20,65,140,.28)' }, { offset: 1, color: 'rgba(20,65,140,0)' }]) } },
      { name: '报修', type: 'line', smooth: true, data: trend.records, symbolSize: 7,
        itemStyle: { color: '#e6a23c' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
          [{ offset: 0, color: 'rgba(230,162,60,.28)' }, { offset: 1, color: 'rgba(230,162,60,0)' }]) } },
    ],
  })
}

function renderStatus(list) {
  charts.status.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { color: '#666' } },
    series: [{
      type: 'pie', radius: ['42%', '66%'], center: ['50%', '46%'],
      avoidLabelOverlap: true, label: { formatter: '{b}\n{c}' },
      data: list.map((d) => ({ ...d, itemStyle: { color: STATUS_COLORS[d.name] || '#909399' } })),
    }],
  })
}

function renderFault(list) {
  const rows = [...list].reverse()
  charts.fault.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 24, top: 14, bottom: 8, containLabel: true },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f2f5' } } },
    yAxis: { type: 'category', data: rows.map((r) => r.name),
      axisLabel: { width: 130, overflow: 'truncate' } },
    series: [{
      type: 'bar', data: rows.map((r) => r.count), barWidth: 16,
      label: { show: true, position: 'right' },
      itemStyle: { borderRadius: [0, 8, 8, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0,
          [{ offset: 0, color: '#5b8ff9' }, { offset: 1, color: '#14418c' }]) },
    }],
  })
}

function renderKg(list) {
  charts.kg.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    legend: { bottom: 0, textStyle: { color: '#666' } },
    series: [{
      type: 'pie', roseType: 'radius', radius: ['28%', '64%'], center: ['50%', '44%'],
      label: { formatter: '{b} {c}' },
      data: list.map((d, i) => ({ ...d, itemStyle: { color: TYPE_COLORS[i % TYPE_COLORS.length] } })),
    }],
  })
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/dashboard/overview')
    Object.assign(cards, data.cards)
    await nextTick()
    renderTrend(data.trend)
    renderStatus(data.device_status)
    renderFault(data.fault_top)
    renderKg(data.kg_dist)
  } catch (e) {
    ElMessage.error('加载数据看板失败')
  } finally {
    loading.value = false
  }
}

function onResize() {
  Object.values(charts).forEach((c) => c && c.resize())
}

onMounted(async () => {
  await nextTick()
  charts.trend = echarts.init(trendEl.value)
  charts.status = echarts.init(statusEl.value)
  charts.fault = echarts.init(faultEl.value)
  charts.kg = echarts.init(kgEl.value)
  window.addEventListener('resize', onResize)
  await load()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  Object.values(charts).forEach((c) => c && c.dispose())
})
</script>

<style scoped>
.dash { display: flex; flex-direction: column; gap: 14px; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.card {
  position: relative; display: flex; align-items: center; gap: 14px;
  background: #fff; border-radius: 10px; padding: 16px 18px;
  border: 1px solid #ebeef5; border-left: 4px solid var(--accent);
  box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
}
.card .ic {
  width: 44px; height: 44px; border-radius: 10px; display: flex;
  align-items: center; justify-content: center;
  color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, #fff);
}
.card .num { font-size: 26px; font-weight: 700; color: #1f2d3d; line-height: 1.1; }
.card .lbl { font-size: 13px; color: #909399; margin-top: 2px; }
.card .sub {
  position: absolute; top: 12px; right: 14px; font-size: 12px;
  color: #a0a4ab; background: #f5f7fa; border-radius: 10px; padding: 1px 8px;
}
.row { margin: 0 !important; }
.panel {
  background: #fff; border-radius: 10px; padding: 12px 16px 6px;
  border: 1px solid #ebeef5; box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
}
.ptitle { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 4px; }
.ptitle::before {
  content: ''; display: inline-block; width: 3px; height: 13px;
  background: #14418c; border-radius: 2px; margin-right: 7px; vertical-align: -1px;
}
.chart { width: 100%; height: 248px; }
</style>
