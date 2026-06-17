<template>
  <div class="dash" v-loading="loading" element-loading-background="rgba(11,15,25,.6)">
    <!-- 欢迎横幅 -->
    <div class="hero">
      <div class="hero-grid"></div>
      <div class="hero-text">
        <h2>{{ greeting }}，{{ userName }}</h2>
        <p>{{ todayStr }} · 设备检修知识检索与作业系统 · 运营总览</p>
      </div>
      <div class="hero-stats">
        <div class="hs"><div class="hsn">{{ dv('device_total') }}</div><div class="hsl">在册设备</div></div>
        <div class="hs-sep"></div>
        <div class="hs"><div class="hsn">{{ dv('qa_total') }}</div><div class="hsl">累计问答</div></div>
        <div class="hs-sep"></div>
        <div class="hs"><div class="hsn">{{ dv('case_total') }}</div><div class="hsl">沉淀案例</div></div>
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
                      :stroke="c.alert ? '#ff6b6b' : '#36a3ff'" stroke-width="2"
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
      <el-col :span="9">
        <div class="panel">
          <div class="ptitle">高故障设备榜 Top5</div>
          <div ref="faultEl" class="chart"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="panel">
          <div class="ptitle">知识图谱实体分布</div>
          <div ref="kgEl" class="chart"></div>
        </div>
      </el-col>
      <el-col :span="7">
        <div class="panel ticker-panel">
          <div class="ptitle">最新报修动态</div>
          <div class="ticker">
            <div class="ticker-track" :class="{ rolling: recent.length > 4 }">
              <div v-for="(r, i) in tickerList" :key="i" class="ticker-item">
                <span class="ti-sev" :class="'sev-' + r.severity">{{ r.severity }}</span>
                <div class="ti-main">
                  <div class="ti-top"><span class="ti-dev">{{ r.device }}</span><span class="ti-time">{{ r.time }}</span></div>
                  <div class="ti-title">{{ r.title }}</div>
                </div>
                <span class="ti-status" :class="{ done: r.status === '已完成' }">{{ r.status }}</span>
              </div>
              <div v-if="!recent.length" class="ticker-empty">暂无报修动态</div>
            </div>
          </div>
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
const recent = ref([])
const tickerList = computed(() => (recent.value.length > 4
  ? [...recent.value, ...recent.value] : recent.value))

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

// 数字滚动增长（rAF，零依赖）
const disp = reactive({})
function animateTo(key, to, dur = 950) {
  const from = disp[key] || 0
  const start = performance.now()
  function tick(now) {
    const t = Math.min(1, (now - start) / dur)
    const eased = 1 - Math.pow(1 - t, 3)
    disp[key] = from + (to - from) * eased
    if (t < 1) requestAnimationFrame(tick)
    else disp[key] = to
  }
  requestAnimationFrame(tick)
}
const dv = (key) => Math.round(disp[key] ?? 0)

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
  if (c.pct && cards[c.key] == null) return '—'
  const v = Math.round(disp[c.key] ?? 0)
  return c.pct ? v + '%' : v
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

const AXIS = '#7e8aa3'
const SPLIT = 'rgba(255,255,255,.06)'
const NEON = ['#36a3ff', '#00e0a0', '#ff6b6b', '#ffb454', '#a78bfa']
const STATUS_COLORS = { 运行中: '#00e0a0', 维修中: '#ffb454', 停机: '#5a6680', 报废: '#ff6b6b' }

function renderTrend(trend) {
  charts.trend.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['问答', '报修'], top: 4, textStyle: { color: AXIS } },
    grid: { left: 36, right: 16, top: 38, bottom: 28 },
    xAxis: { type: 'category', data: trend.dates, axisLine: { lineStyle: { color: SPLIT } },
      axisLabel: { color: AXIS } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: AXIS },
      splitLine: { lineStyle: { color: SPLIT } } },
    series: [
      { name: '问答', type: 'line', smooth: true, data: trend.qa, symbolSize: 7,
        itemStyle: { color: '#36a3ff' }, lineStyle: { width: 2.5, shadowColor: 'rgba(54,163,255,.5)', shadowBlur: 8 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
          [{ offset: 0, color: 'rgba(54,163,255,.35)' }, { offset: 1, color: 'rgba(54,163,255,0)' }]) } },
      { name: '报修', type: 'line', smooth: true, data: trend.records, symbolSize: 7,
        itemStyle: { color: '#00e0a0' }, lineStyle: { width: 2.5, shadowColor: 'rgba(0,224,160,.5)', shadowBlur: 8 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1,
          [{ offset: 0, color: 'rgba(0,224,160,.30)' }, { offset: 1, color: 'rgba(0,224,160,0)' }]) } },
    ],
  })
}

function renderStatus(list) {
  charts.status.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { color: AXIS } },
    series: [{
      type: 'pie', radius: ['42%', '66%'], center: ['50%', '46%'],
      avoidLabelOverlap: true, label: { color: AXIS, formatter: '{b}\n{c}' },
      itemStyle: { borderColor: '#0b0f19', borderWidth: 2 },
      data: list.map((d) => ({ ...d, itemStyle: { color: STATUS_COLORS[d.name] || '#5a6680' } })),
    }],
  })
}

function renderFault(list) {
  const rows = [...list].reverse()
  charts.fault.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 24, top: 14, bottom: 8, containLabel: true },
    xAxis: { type: 'value', minInterval: 1, axisLabel: { color: AXIS },
      splitLine: { lineStyle: { color: SPLIT } } },
    yAxis: { type: 'category', data: rows.map((r) => r.name),
      axisLabel: { color: AXIS, width: 96, overflow: 'truncate' } },
    series: [{
      type: 'bar', data: rows.map((r) => r.count), barWidth: 15,
      label: { show: true, position: 'right', color: AXIS },
      itemStyle: { borderRadius: [0, 8, 8, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0,
          [{ offset: 0, color: '#1f6feb' }, { offset: 1, color: '#36a3ff' }]) },
    }],
  })
}

function renderKg(list) {
  charts.kg.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    legend: { bottom: 0, textStyle: { color: AXIS } },
    series: [{
      type: 'pie', roseType: 'radius', radius: ['28%', '64%'], center: ['50%', '44%'],
      label: { color: AXIS, formatter: '{b} {c}' },
      itemStyle: { borderColor: '#0b0f19', borderWidth: 2 },
      data: list.map((d, i) => ({ ...d, itemStyle: { color: NEON[i % NEON.length] } })),
    }],
  })
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/dashboard/overview')
    Object.assign(cards, data.cards)
    recent.value = data.recent_records || []
    trendData.value = data.trend
    cardDefs.forEach((c) => animateTo(c.key, Number(cards[c.key]) || 0))
    animateTo('case_total', Number(cards.case_total) || 0)
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
/* 暗黑数据驾驶舱：填满内容区 */
.dash {
  margin: -18px; padding: 18px; min-height: calc(100vh - 56px);
  background: radial-gradient(1200px 500px at 20% -10%, #16213c 0%, #0b0f19 55%);
  display: flex; flex-direction: column; gap: 14px;
}

/* 欢迎横幅 */
.hero {
  position: relative; overflow: hidden; border-radius: 12px;
  background: linear-gradient(120deg, #11214a 0%, #1f4fb0 100%);
  color: #fff; padding: 22px 28px; display: flex; align-items: center;
  justify-content: space-between; border: 1px solid rgba(120,170,255,.18);
}
.hero-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(120,180,255,.10) 1px, transparent 1px),
    linear-gradient(90deg, rgba(120,180,255,.10) 1px, transparent 1px);
  background-size: 30px 30px;
  mask-image: linear-gradient(90deg, #000 30%, transparent 90%);
}
.hero-text { position: relative; z-index: 2; }
.hero-text h2 { margin: 0 0 6px; font-size: 23px; font-weight: 700; }
.hero-text p { margin: 0; font-size: 13px; color: rgba(255, 255, 255, .8); }
.hero-stats { position: relative; z-index: 2; display: flex; align-items: center; gap: 22px; }
.hs { text-align: center; }
.hsn { font-size: 28px; font-weight: 700; line-height: 1; color: #7fd8ff; text-shadow: 0 0 12px rgba(54,163,255,.6); }
.hsl { font-size: 12px; color: rgba(255, 255, 255, .75); margin-top: 5px; }
.hs-sep { width: 1px; height: 32px; background: rgba(255, 255, 255, .2); }

.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.card {
  background: rgba(19, 26, 43, .8); border: 1px solid rgba(120,160,220,.12); border-radius: 12px;
  padding: 15px 18px 13px; transition: all .18s;
}
.card:hover {
  transform: translateY(-2px); border-color: rgba(54,163,255,.45);
  box-shadow: 0 8px 26px rgba(0, 0, 0, .35), 0 0 0 1px rgba(54,163,255,.15);
}
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-label { font-size: 13px; color: #8b98b0; }
.card-ic { color: #46557a; font-size: 17px; }
.card-body { display: flex; align-items: baseline; gap: 4px; margin: 10px 0 8px; }
.card-num { font-size: 30px; font-weight: 700; color: #eaf2ff; line-height: 1; letter-spacing: -.6px; }
.card-unit { font-size: 13px; color: #6b7793; }
.card-foot { height: 22px; display: flex; align-items: center; }
.card-sub {
  font-size: 12px; color: #9fb0cc; background: rgba(255,255,255,.05);
  padding: 2px 9px; border-radius: 6px;
}
.spark { width: 76px; height: 22px; opacity: .95; }
.card.alert { border-color: rgba(255,107,107,.45); background: rgba(40,18,22,.7); }
.card.alert .card-label { color: #ff9b9b; }
.card.alert .card-num { color: #ff6b6b; text-shadow: 0 0 14px rgba(255,107,107,.5); }
.card.alert .card-ic { color: #ff8a8a; }

.row { margin: 0 !important; }
.panel {
  background: rgba(19, 26, 43, .8); border-radius: 10px; padding: 12px 16px 6px;
  border: 1px solid rgba(120,160,220,.12);
}
.ptitle { font-size: 14px; font-weight: 600; color: #cfe0ff; margin-bottom: 4px; }
.ptitle::before {
  content: ''; display: inline-block; width: 3px; height: 13px;
  background: #36a3ff; border-radius: 2px; margin-right: 7px; vertical-align: -1px;
  box-shadow: 0 0 8px rgba(54,163,255,.8);
}
.chart { width: 100%; height: 248px; }

/* 最新报修动态 · 无缝滚动 */
.ticker-panel { display: flex; flex-direction: column; }
.ticker { height: 248px; overflow: hidden; position: relative; }
.ticker-track.rolling { animation: tickerScroll 18s linear infinite; }
.ticker:hover .ticker-track.rolling { animation-play-state: paused; }
@keyframes tickerScroll { from { transform: translateY(0); } to { transform: translateY(-50%); } }
.ticker-item {
  display: flex; align-items: center; gap: 8px; padding: 9px 4px;
  border-bottom: 1px solid rgba(255,255,255,.05);
}
.ti-sev { font-size: 11px; padding: 2px 6px; border-radius: 4px; flex: none; }
.sev-一般 { color: #9fb0cc; background: rgba(255,255,255,.07); }
.sev-严重 { color: #ffce82; background: rgba(255,180,84,.14); }
.sev-紧急 { color: #ff9b9b; background: rgba(255,107,107,.16); }
.ti-main { flex: 1; min-width: 0; }
.ti-top { display: flex; justify-content: space-between; font-size: 11px; color: #6b7793; }
.ti-dev { color: #8fc0ff; }
.ti-title { font-size: 12.5px; color: #d6e2f5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ti-status { font-size: 11px; color: #ffb454; flex: none; }
.ti-status.done { color: #00e0a0; }
.ticker-empty { color: #6b7793; text-align: center; padding: 40px 0; }
</style>
