<template>
  <div class="dash" v-loading="loading">
    <!-- 欢迎横幅 -->
    <div class="hero">
      <div class="hero-grid"></div>
      <div class="hero-text">
        <h2>{{ greeting }}，{{ userName }}</h2>
        <p>{{ todayStr }} · 设备检修知识检索与作业系统 · 运营总览</p>
      </div>
      <div class="hero-stats">
        <div class="hs"><div class="hsn">{{ cards.device_total ?? '—' }}</div><div class="hsl">在册设备</div></div>
        <div class="hs-sep"></div>
        <div class="hs"><div class="hsn">{{ cards.qa_total ?? '—' }}</div><div class="hsl">累计问答</div></div>
        <div class="hs-sep"></div>
        <div class="hs"><div class="hsn">{{ cards.case_total ?? '—' }}</div><div class="hsl">沉淀案例</div></div>
      </div>
    </div>

    <!-- 指标卡片 -->
    <div class="cards">
      <div v-for="c in cardDefs" :key="c.key" class="card"
           :class="{ alert: c.alert && Number(cards[c.key]) > 0 }">
        <div class="card-head">
          <span class="card-label">{{ c.label }}</span>
          <el-icon class="card-ic"><component :is="c.icon" /></el-icon>
        </div>
        <div class="card-body">
          <span class="card-num">{{ cardValue(c) }}</span>
          <span v-if="c.unit" class="card-unit">{{ c.unit }}</span>
        </div>
        <div class="card-foot">
          <svg v-if="c.spark && trendData" class="spark" viewBox="0 0 100 26" preserveAspectRatio="none">
            <polyline :points="sparkPoints(c.spark)" fill="none"
                      :stroke="c.alert ? '#e24b4a' : '#1f6feb'" stroke-width="2"
                      stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span v-else-if="c.sub" class="card-sub">{{ c.sub() }}</span>
        </div>
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
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Monitor, Warning, Collection, EditPen, Tickets, ChatDotRound, Star, Share,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api from '../api'
import { useAuthStore } from '../store'

const loading = ref(false)
const cards = reactive({})

const auth = useAuthStore()
const userName = computed(() => auth.user?.display_name || '用户')
const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 6 ? '凌晨好' : h < 12 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'
})
const todayStr = computed(() => {
  const d = new Date()
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日 · 星期${week}`
})

const cardDefs = [
  { key: 'device_total', label: '设备总数', icon: Monitor, unit: '台',
    sub: () => `维修中 ${cards.open_records || 0}` },
  { key: 'open_records', label: '未结报修', icon: Warning, unit: '项', alert: true, spark: 'records' },
  { key: 'doc_total', label: '知识库文档', icon: Collection, unit: '篇' },
  { key: 'case_total', label: '检修案例', icon: EditPen, unit: '例',
    sub: () => `待审 ${cards.case_pending || 0}` },
  { key: 'sop_total', label: '作业指引', icon: Tickets, unit: '套',
    sub: () => `已执行 ${cards.sop_run_total || 0}` },
  { key: 'qa_total', label: '智能问答', icon: ChatDotRound, unit: '次', spark: 'qa' },
  { key: 'satisfaction', label: '问答满意度', icon: Star, pct: true },
  { key: 'kg_entities', label: '图谱实体', icon: Share, unit: '个',
    sub: () => `关系 ${cards.kg_relations || 0}` },
]
function cardValue(c) {
  const v = cards[c.key]
  if (c.pct) return v == null ? '—' : v + '%'
  return v ?? 0
}

const trendData = ref(null)
function sparkPoints(key) {
  const arr = trendData.value?.[key] || []
  if (!arr.length) return ''
  const max = Math.max(...arr, 1)
  const n = arr.length
  return arr.map((v, i) => `${(n === 1 ? 50 : (i / (n - 1)) * 100).toFixed(1)},${(26 - (v / max) * 22 - 2).toFixed(1)}`).join(' ')
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
    trendData.value = data.trend
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

/* 欢迎横幅 */
.hero {
  position: relative; overflow: hidden; border-radius: 12px;
  background: linear-gradient(120deg, #14418c 0%, #1f6feb 100%);
  color: #fff; padding: 22px 28px; display: flex; align-items: center;
  justify-content: space-between;
}
.hero-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, .07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, .07) 1px, transparent 1px);
  background-size: 30px 30px;
  mask-image: linear-gradient(90deg, #000 30%, transparent 90%);
}
.hero-text { position: relative; z-index: 2; }
.hero-text h2 { margin: 0 0 6px; font-size: 23px; font-weight: 700; }
.hero-text p { margin: 0; font-size: 13px; color: rgba(255, 255, 255, .82); }
.hero-stats { position: relative; z-index: 2; display: flex; align-items: center; gap: 22px; }
.hs { text-align: center; }
.hsn { font-size: 26px; font-weight: 700; line-height: 1; }
.hsl { font-size: 12px; color: rgba(255, 255, 255, .8); margin-top: 5px; }
.hs-sep { width: 1px; height: 32px; background: rgba(255, 255, 255, .25); }

.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.card {
  background: #fff; border: 1px solid #ebeef5; border-radius: 12px;
  padding: 15px 18px 13px; transition: all .18s;
  box-shadow: 0 1px 3px rgba(20, 40, 80, .04);
}
.card:hover {
  transform: translateY(-2px); border-color: #d2ddf2;
  box-shadow: 0 10px 24px rgba(20, 40, 80, .10);
}
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-label { font-size: 13px; color: #6b7280; }
.card-ic { color: #c4ccda; font-size: 17px; }
.card-body { display: flex; align-items: baseline; gap: 4px; margin: 10px 0 8px; }
.card-num { font-size: 30px; font-weight: 700; color: #1f2329; line-height: 1; letter-spacing: -.6px; }
.card-unit { font-size: 13px; color: #a0a4ab; }
.card-foot { height: 22px; display: flex; align-items: center; }
.card-sub {
  font-size: 12px; color: #7d8595; background: #f4f6fa;
  padding: 2px 9px; border-radius: 6px;
}
.spark { width: 76px; height: 22px; opacity: .9; }
.card.alert { border-color: #f1c7c7; background: #fffafa; }
.card.alert .card-label { color: #c0504a; }
.card.alert .card-num { color: #e24b4a; }
.card.alert .card-ic { color: #ec9a9a; }
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
