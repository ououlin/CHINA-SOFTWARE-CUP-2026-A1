<template>
  <div class="cases-page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <div class="left">
            <span class="ttl">检修案例库</span>
            <el-radio-group v-if="canReview" v-model="statusFilter" size="small"
                            @change="load">
              <el-radio-button label="">全部</el-radio-button>
              <el-radio-button label="pending">待审核</el-radio-button>
              <el-radio-button label="approved">已采纳</el-radio-button>
              <el-radio-button label="rejected">已退回</el-radio-button>
            </el-radio-group>
          </div>
          <el-button type="primary" :icon="Plus" size="small" @click="openSubmit">
            提交案例
          </el-button>
        </div>
      </template>

      <el-table :data="cases" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="62" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="device_type" label="设备类型" width="128" />
        <el-table-column prop="device_model" label="型号" width="108" />
        <el-table-column v-if="canReview" prop="author_name" label="提交人" width="100" />
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="206">
          <template #default="{ row }">
            <el-button size="small" text :icon="View" @click="openDetail(row)">查看</el-button>
            <template v-if="canReview && row.status === 'pending'">
              <el-button size="small" type="success" @click="doReview(row, 'approve')">采纳</el-button>
              <el-button size="small" type="danger" plain @click="doReview(row, 'reject')">退回</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 提交案例 -->
    <el-dialog v-model="submitDialog" title="提交检修案例 / 经验" width="560px">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="如：化油器溢油故障检修" />
        </el-form-item>
        <el-form-item label="设备类型">
          <el-input v-model="form.device_type" placeholder="如：摩托车发动机" />
        </el-form-item>
        <el-form-item label="设备型号">
          <el-input v-model="form.device_model" placeholder="可选，如：通用四冲程" />
        </el-form-item>
        <el-form-item label="案例正文">
          <el-input v-model="form.content" type="textarea" :rows="6"
                    placeholder="描述故障现象、排查过程与处理措施……" />
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" show-icon
                title="提交后进入待审核队列；审核员采纳后将自动切块入向量库并抽取知识图谱。" />
      <template #footer>
        <el-button @click="submitDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="doSubmit">提交</el-button>
      </template>
    </el-dialog>

    <!-- 案例详情 -->
    <el-drawer v-model="detailDrawer" :title="current?.title || '案例详情'" size="600px"
               :destroy-on-close="true">
      <div v-if="current" class="detail">
        <div class="meta">
          <el-tag size="small" effect="plain">{{ current.device_type || '通用' }}</el-tag>
          <el-tag size="small" effect="plain" type="info">{{ current.device_model || '—' }}</el-tag>
          <el-tag :type="statusType(current.status)" size="small">
            {{ statusLabel(current.status) }}
          </el-tag>
          <span class="author">提交人：{{ current.author_name || '—' }}</span>
        </div>
        <el-divider content-position="left">案例正文</el-divider>
        <p class="content">{{ current.content }}</p>

        <template v-if="current.status === 'approved'">
          <el-divider content-position="left">知识沉淀</el-divider>
          <div class="kg-info">
            <div class="stat"><span class="num">{{ current.entity_count }}</span><span class="lbl">抽取实体</span></div>
            <div class="stat"><span class="num">{{ current.relation_count }}</span><span class="lbl">抽取关系</span></div>
            <el-tag type="success" effect="plain">已入向量库 · doc #{{ current.doc_id }}</el-tag>
          </div>
          <el-alert type="success" :closable="false" show-icon
                    title="该案例已可在「智能检修问答」中被检索并作为引用来源。" />
        </template>

        <template v-if="current.review_note">
          <el-divider content-position="left">审核意见</el-divider>
          <p class="note">{{ current.review_note }}</p>
        </template>
      </div>
      <template #footer>
        <div v-if="canReview && current?.status === 'pending'" class="dfooter">
          <el-button type="danger" plain @click="doReview(current, 'reject')">退回</el-button>
          <el-button type="success" @click="doReview(current, 'approve')">采纳入库</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'
import { Plus, View } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

const auth = useAuthStore()
const canReview = computed(() => ['auditor', 'admin'].includes(auth.user?.role))

const cases = ref([])
const loading = ref(false)
const statusFilter = ref('')

const STATUS = {
  pending: { label: '待审核', type: 'warning' },
  approved: { label: '已采纳', type: 'success' },
  rejected: { label: '已退回', type: 'info' },
}
const statusLabel = (s) => STATUS[s]?.label || s
const statusType = (s) => STATUS[s]?.type || ''

async function load() {
  loading.value = true
  try {
    const params = {}
    if (canReview.value && statusFilter.value) params.status = statusFilter.value
    const { data } = await api.get('/cases', { params })
    cases.value = data
  } catch (e) {
    ElMessage.error('加载案例失败')
  } finally {
    loading.value = false
  }
}

// ---- 提交 ----
const submitDialog = ref(false)
const submitting = ref(false)
const form = reactive({ title: '', device_type: '', device_model: '', content: '' })
function openSubmit() {
  Object.assign(form, { title: '', device_type: '', device_model: '', content: '' })
  submitDialog.value = true
}
async function doSubmit() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写标题与案例正文')
    return
  }
  submitting.value = true
  try {
    await api.post('/cases', { ...form })
    ElMessage.success('已提交，等待审核')
    submitDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

// ---- 详情 ----
const detailDrawer = ref(false)
const current = ref(null)
async function openDetail(row) {
  try {
    const { data } = await api.get(`/cases/${row.id}`)
    current.value = data
    detailDrawer.value = true
  } catch (e) {
    ElMessage.error('加载详情失败')
  }
}

// ---- 审核 ----
async function doReview(row, action) {
  if (action === 'reject') {
    let note = ''
    try {
      const r = await ElMessageBox.prompt('请填写退回意见（可选）', '退回案例', {
        confirmButtonText: '确认退回', cancelButtonText: '取消', inputType: 'textarea',
      })
      note = r.value || ''
    } catch {
      return
    }
    await runReview(row, 'reject', note)
    return
  }
  try {
    await ElMessageBox.confirm(
      '采纳后将把案例切块入向量库，并调用大模型抽取知识图谱实体与关系。是否继续？',
      '采纳入库', { type: 'warning', confirmButtonText: '采纳', cancelButtonText: '取消' })
  } catch {
    return
  }
  await runReview(row, 'approve')
}

async function runReview(row, action, note = '') {
  const loadingInst = action === 'approve'
    ? ElLoading.service({ lock: true, text: '正在采纳并抽取知识图谱……' })
    : null
  try {
    const { data } = await api.post(`/cases/${row.id}/review`, { action, note })
    ElMessage.success(action === 'approve'
      ? `已采纳：抽取实体 ${data.entity_count} 个、关系 ${data.relation_count} 条`
      : '已退回')
    detailDrawer.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    if (loadingInst) loadingInst.close()
  }
}

onMounted(load)
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; }
.left { display: flex; align-items: center; gap: 16px; }
.ttl { font-weight: 600; }
.detail { padding: 2px 4px; }
.meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.meta .author { color: #909399; font-size: 13px; margin-left: auto; }
.content, .note { color: #303133; line-height: 1.75; white-space: pre-wrap; }
.note { color: #606266; }
.kg-info { display: flex; align-items: center; gap: 24px; margin-bottom: 14px; }
.kg-info .stat { display: flex; flex-direction: column; align-items: center; }
.kg-info .num { font-size: 24px; font-weight: 700; color: #14418c; }
.kg-info .lbl { font-size: 12px; color: #909399; }
.dfooter { display: flex; justify-content: flex-end; gap: 10px; }
</style>
