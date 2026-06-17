<template>
  <div class="audit-page">
    <div class="panel">
      <div class="head">
        <span class="ptitle">操作审计日志</span>
        <el-select v-model="actionFilter" placeholder="全部操作" clearable size="small"
                   style="width: 200px" @change="load">
          <el-option v-for="a in actionOpts" :key="a.value" :label="a.label" :value="a.value" />
        </el-select>
      </div>
      <el-table :data="logs" v-loading="loading" size="small" stripe max-height="620">
        <el-table-column prop="id" label="ID" width="66" />
        <el-table-column label="时间" width="172">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="username" label="操作人" width="120" />
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="actionType(row.action)">{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="300" show-overflow-tooltip />
      </el-table>
      <el-empty v-if="!loading && !logs.length" description="暂无审计记录" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const ACTIONS = {
  'case.approve': { label: '采纳案例', type: 'success' },
  'case.reject': { label: '退回案例', type: 'info' },
  'sop.create': { label: '新建流程', type: 'primary' },
  'sop.publish': { label: '发布流程', type: 'success' },
  'sop.delete': { label: '删除流程', type: 'danger' },
  'feedback.archive': { label: '下架修正', type: 'warning' },
  'feedback.restore': { label: '恢复修正', type: 'info' },
  'device.create': { label: '设备建档', type: 'primary' },
  'device.delete': { label: '删除设备', type: 'danger' },
  'device.repair_handle': { label: '处理报修', type: '' },
}
const actionOpts = Object.entries(ACTIONS).map(([value, v]) => ({ value, label: v.label }))
const actionLabel = (a) => ACTIONS[a]?.label || a
const actionType = (a) => ACTIONS[a]?.type ?? ''

const logs = ref([])
const loading = ref(false)
const actionFilter = ref('')

function fmtTime(s) {
  if (!s) return ''
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z')
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (actionFilter.value) params.action = actionFilter.value
    const { data } = await api.get('/audit', { params })
    logs.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载审计日志失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.panel {
  background: #fff; border-radius: 10px; padding: 14px 16px;
  border: 1px solid #ebeef5; box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
}
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.ptitle { font-size: 14px; font-weight: 600; color: #303133; }
.ptitle::before {
  content: ''; display: inline-block; width: 3px; height: 13px;
  background: #14418c; border-radius: 2px; margin-right: 7px; vertical-align: -1px;
}
</style>
