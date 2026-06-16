<template>
  <div class="alert-page" v-loading="loading">
    <!-- 风险概览 -->
    <div class="summary">
      <div class="sum-card high">
        <div class="n">{{ summary.high }}</div><div class="l">高风险设备</div>
      </div>
      <div class="sum-card mid">
        <div class="n">{{ summary.medium }}</div><div class="l">中风险设备</div>
      </div>
      <div class="sum-card low">
        <div class="n">{{ summary.low }}</div><div class="l">低风险设备</div>
      </div>
    </div>

    <el-row :gutter="14" class="row">
      <el-col :span="14">
        <div class="panel">
          <div class="ptitle">设备风险评分</div>
          <el-table :data="riskDevices" size="small" max-height="320" stripe>
            <el-table-column prop="name" label="设备" min-width="150" show-overflow-tooltip />
            <el-table-column prop="device_model" label="型号" width="100" />
            <el-table-column label="风险" width="72">
              <template #default="{ row }">
                <el-tag :type="levelType(row.level)" size="small">{{ row.level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="score" label="评分" width="62" align="center" />
            <el-table-column prop="reason" label="风险说明" min-width="180" show-overflow-tooltip />
          </el-table>
          <el-empty v-if="!riskDevices.length" description="暂无风险数据" :image-size="56" />
        </div>
      </el-col>
      <el-col :span="10">
        <div class="panel">
          <div class="ptitle">故障分布（按型号）</div>
          <div ref="faultEl" class="chart"></div>
        </div>
      </el-col>
    </el-row>

    <div class="panel advice-panel">
      <div class="ptitle-row">
        <span class="ptitle">AI 预测性维护建议</span>
        <div class="adv-acts">
          <el-button v-if="adviceText" text :icon="Download" size="small"
                     @click="downloadAdvice">下载</el-button>
          <el-button type="primary" size="small" :icon="MagicStick"
                     :loading="adviceLoading" @click="genAdvice">
            {{ adviceText ? '重新生成' : '生成建议' }}
          </el-button>
        </div>
      </div>
      <div v-if="adviceLoading" class="adv-loading">大模型正在分析风险并生成维护建议……</div>
      <el-empty v-else-if="!adviceText" :image-size="66"
                description="点击「生成建议」由大模型基于风险数据给出预测性维护方案" />
      <div v-else class="advice-md">{{ adviceText }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Download } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api from '../api'

const loading = ref(false)
const riskDevices = ref([])
const summary = reactive({ high: 0, medium: 0, low: 0 })
const faultEl = ref(null)
let chart = null

const levelType = (l) => ({ 高: 'danger', 中: 'warning', 低: 'info' }[l] || 'info')

function renderFault(list) {
  if (!chart) return
  const rows = [...list].reverse()
  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 28, top: 14, bottom: 8, containLabel: true },
    xAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#f0f2f5' } } },
    yAxis: { type: 'category', data: rows.map((r) => r.name),
      axisLabel: { width: 110, overflow: 'truncate' } },
    series: [{
      type: 'bar', data: rows.map((r) => r.value), barWidth: 18,
      label: { show: true, position: 'right' },
      itemStyle: { borderRadius: [0, 8, 8, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0,
          [{ offset: 0, color: '#fa9d3b' }, { offset: 1, color: '#f6685e' }]) },
    }],
  })
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/alert/overview')
    riskDevices.value = data.risk_devices
    Object.assign(summary, data.summary)
    await nextTick()
    renderFault(data.fault_by_model)
  } catch (e) {
    ElMessage.error('加载预警数据失败')
  } finally {
    loading.value = false
  }
}

const adviceLoading = ref(false)
const adviceText = ref('')
async function genAdvice() {
  adviceLoading.value = true
  try {
    const { data } = await api.post('/alert/advice')
    adviceText.value = data.advice
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '建议生成失败')
  } finally {
    adviceLoading.value = false
  }
}
function downloadAdvice() {
  if (!adviceText.value) return
  const today = new Date().toISOString().slice(0, 10)
  const blob = new Blob([adviceText.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `预测性维护建议_${today}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function onResize() { chart && chart.resize() }
onMounted(async () => {
  await nextTick()
  chart = echarts.init(faultEl.value)
  window.addEventListener('resize', onResize)
  await load()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart && chart.dispose()
})
</script>

<style scoped>
.alert-page { display: flex; flex-direction: column; gap: 14px; }
.summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.sum-card {
  background: #fff; border-radius: 10px; padding: 16px 20px;
  border: 1px solid #ebeef5; border-left: 4px solid #909399;
  box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
}
.sum-card.high { border-left-color: #f56c6c; }
.sum-card.mid { border-left-color: #e6a23c; }
.sum-card.low { border-left-color: #909399; }
.sum-card .n { font-size: 28px; font-weight: 700; color: #1f2d3d; }
.sum-card.high .n { color: #f56c6c; }
.sum-card.mid .n { color: #e6a23c; }
.sum-card .l { font-size: 13px; color: #909399; margin-top: 2px; }
.row { margin: 0 !important; }
.panel {
  background: #fff; border-radius: 10px; padding: 12px 16px;
  border: 1px solid #ebeef5; box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
}
.ptitle { font-size: 14px; font-weight: 600; color: #303133; }
.ptitle::before {
  content: ''; display: inline-block; width: 3px; height: 13px;
  background: #14418c; border-radius: 2px; margin-right: 7px; vertical-align: -1px;
}
.chart { width: 100%; height: 300px; }
.advice-panel { min-height: 120px; }
.ptitle-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.adv-acts { display: flex; align-items: center; gap: 4px; }
.adv-loading { color: #909399; padding: 24px; text-align: center; }
.advice-md {
  white-space: pre-wrap; line-height: 1.75; color: #303133; font-size: 14px;
  padding: 4px 2px; max-height: 50vh; overflow-y: auto;
}
</style>
