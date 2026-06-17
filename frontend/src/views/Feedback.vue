<template>
  <div class="fb-page">
    <el-card shadow="never" class="stat-card">
      <div class="stats">
        <div class="stat"><span class="num up">{{ stats.up }}</span><span class="lbl">👍 有用</span></div>
        <div class="stat"><span class="num down">{{ stats.down }}</span><span class="lbl">👎 没用</span></div>
        <div class="stat"><span class="num corr">{{ stats.corrections }}</span><span class="lbl">已发布生效</span></div>
        <div class="stat"><span class="num pend">{{ stats.pending }}</span><span class="lbl">待审发布</span></div>
      </div>
      <el-switch v-model="onlyCorr" active-text="仅看含纠正" @change="load" />
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="ch">
          <span>标注与修正记录</span>
          <span class="hint">影子知识库流控：纠正提交后为「待审核」仅提交者可预览；审核员「发布」后才全局生效，可「回滚」到安全版本。</span>
        </div>
      </template>
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="query" label="原问题" min-width="180" show-overflow-tooltip />
        <el-table-column label="评价" width="92">
          <template #default="{ row }">
            <el-tag v-if="row.vote === 'up'" type="success" size="small">👍 有用</el-tag>
            <el-tag v-else-if="row.vote === 'down'" type="danger" size="small">👎 没用</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="人工纠正" min-width="240">
          <template #default="{ row }">
            <span v-if="row.correction_text" class="corr-text">{{ row.correction_text }}</span>
            <span v-else class="muted">（仅评价，无纠正）</span>
          </template>
        </el-table-column>
        <el-table-column v-if="canManage" prop="user_name" label="反馈人" width="100" />
        <el-table-column label="状态" width="118">
          <template #default="{ row }">
            <el-tag v-if="!row.correction_text" size="small" effect="plain" type="info">—</el-tag>
            <el-tag v-else-if="row.status !== 'active'" size="small" effect="plain" type="info">已下架</el-tag>
            <el-tag v-else-if="row.pub_status === 'pending_review'" size="small" type="warning">待审核</el-tag>
            <el-tag v-else-if="row.pub_status === 'published'" size="small" type="success">已发布 v{{ row.version }}</el-tag>
            <el-tag v-else size="small" effect="plain" type="info">已回滚</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canManage" label="操作" width="158">
          <template #default="{ row }">
            <template v-if="row.correction_text">
              <template v-if="row.status === 'active'">
                <el-button v-if="row.pub_status !== 'published'" size="small" type="success" plain
                           @click="publish(row)">发布</el-button>
                <el-button v-else size="small" type="warning" plain
                           @click="rollback(row)">回滚</el-button>
                <el-button size="small" type="danger" plain @click="archive(row)">下架</el-button>
              </template>
              <el-button v-else size="small" type="success" plain @click="restore(row)">恢复</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useAuthStore } from '../store'

const auth = useAuthStore()
const canManage = computed(() => ['auditor', 'admin'].includes(auth.user?.role))

const rows = ref([])
const loading = ref(false)
const onlyCorr = ref(true)
const stats = reactive({ up: 0, down: 0, corrections: 0, pending: 0 })

async function load() {
  loading.value = true
  try {
    const [list, st] = await Promise.all([
      api.get('/feedback', { params: { only_corrections: onlyCorr.value } }),
      api.get('/feedback/stats'),
    ])
    rows.value = list.data
    Object.assign(stats, st.data)
  } catch (e) {
    ElMessage.error('加载反馈失败')
  } finally {
    loading.value = false
  }
}

async function archive(row) {
  try {
    await api.post(`/feedback/${row.id}/archive`)
    ElMessage.success('已下架，该修正不再参与反馈增强')
    await load()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}
async function restore(row) {
  try {
    await api.post(`/feedback/${row.id}/restore`)
    ElMessage.success('已恢复')
    await load()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}
async function publish(row) {
  try {
    await api.post(`/feedback/${row.id}/publish`)
    ElMessage.success('已正式发布，进入全局 RAG 生效')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '发布失败')
  }
}
async function rollback(row) {
  try {
    await api.post(`/feedback/${row.id}/rollback`)
    ElMessage.success('已回滚，退出全局生效')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '回滚失败')
  }
}

onMounted(load)
</script>

<style scoped>
.fb-page { display: flex; flex-direction: column; gap: 14px; }
.stat-card :deep(.el-card__body) {
  display: flex; align-items: center; justify-content: space-between; padding: 14px 20px;
}
.stats { display: flex; gap: 40px; }
.stat { display: flex; flex-direction: column; align-items: center; }
.stat .num { font-size: 26px; font-weight: 700; line-height: 1.2; }
.stat .num.up { color: #67c23a; }
.stat .num.down { color: #f56c6c; }
.stat .num.corr { color: #14418c; }
.stat .num.pend { color: #e6a23c; }
.stat .lbl { font-size: 12px; color: #909399; margin-top: 2px; }
.ch { display: flex; align-items: baseline; gap: 12px; }
.ch .hint { font-size: 12px; color: #909399; font-weight: normal; }
.corr-text { color: #b88230; line-height: 1.6; }
.muted { color: #c0c4cc; }
</style>
