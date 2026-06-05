<template>
  <div class="sop-page">
    <!-- 筛选 + 操作栏（个性化推送：按设备类型 + 检修等级） -->
    <el-card shadow="never" class="filter-bar">
      <div class="bar">
        <div class="filters">
          <el-select v-model="filter.device_type" placeholder="设备类型" clearable
                     style="width: 180px" @change="load">
            <el-option v-for="d in deviceTypes" :key="d" :label="d" :value="d" />
          </el-select>
          <el-select v-model="filter.repair_level" placeholder="检修等级" clearable
                     style="width: 160px" @change="load">
            <el-option v-for="l in repairLevels" :key="l" :label="l" :value="l" />
          </el-select>
        </div>
        <div class="actions">
          <el-button :icon="Document" @click="openRecords">作业记录</el-button>
          <el-button v-if="canEdit" type="primary" :icon="MagicStick"
                     @click="genDialog = true">
            AI 生成流程草稿
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 模板卡片列表 -->
    <div v-loading="loading" class="cards">
      <el-empty v-if="!loading && templates.length === 0" description="暂无作业流程" />
      <el-card v-for="t in templates" :key="t.id" shadow="hover" class="tpl-card">
        <div class="tpl-head">
          <span class="tpl-name">{{ t.name }}</span>
          <el-tag v-if="t.status === 'draft'" type="warning" size="small">AI草稿·待发布</el-tag>
          <el-tag v-else type="success" size="small" effect="plain">已发布</el-tag>
        </div>
        <div class="tpl-meta">
          <el-tag size="small" effect="plain">{{ t.device_type || '通用' }}</el-tag>
          <el-tag size="small" effect="plain" type="info">{{ t.repair_level || '—' }}</el-tag>
          <span class="step-count">{{ t.step_count }} 步</span>
          <el-tag v-if="t.source === 'ai'" size="small" type="primary" effect="plain">AI 生成</el-tag>
        </div>
        <div class="tpl-summary">{{ t.summary || '（无说明）' }}</div>
        <div class="tpl-actions">
          <template v-if="t.status === 'approved'">
            <el-button type="primary" size="small" :icon="VideoPlay"
                       @click="startRun(t)">开始作业</el-button>
            <el-button size="small" :icon="View" @click="preview(t)">预览</el-button>
          </template>
          <template v-else>
            <el-button size="small" :icon="View" @click="preview(t)">校核预览</el-button>
            <el-button v-if="canEdit" type="success" size="small"
                       @click="publish(t)">发布</el-button>
            <el-button v-if="canEdit" type="danger" size="small" plain
                       @click="remove(t)">删除</el-button>
          </template>
        </div>
      </el-card>
    </div>

    <!-- 执行 / 预览 抽屉 -->
    <el-drawer v-model="drawer" :title="current?.name || '作业流程'" size="660px"
               :destroy-on-close="true">
      <div v-if="current" class="run">
        <el-alert v-if="mode === 'execute'" type="info" :closable="false" show-icon
                  class="run-tip"
                  title="逐步执行，带★的为合规必检项，需勾选确认后方可进入下一步。" />
        <el-steps :active="active" direction="vertical" finish-status="success">
          <el-step v-for="(s, idx) in current.steps" :key="s.id"
                   :status="stepStatus(idx)">
            <template #title>
              <span class="step-title">
                {{ s.order_no }}. {{ s.title }}
                <el-tag v-if="s.is_required" type="danger" size="small" effect="dark">★必检</el-tag>
              </span>
            </template>
            <template #description>
              <div v-if="idx === active || mode === 'preview'" class="step-body">
                <p class="instruction">{{ s.instruction }}</p>
                <el-alert v-if="s.risk" :title="`风险提示：${s.risk}`" type="warning"
                          :closable="false" show-icon />
                <div v-if="s.tools" class="tools">
                  <span class="label">所需工具：</span>
                  <el-tag v-for="tool in splitTools(s.tools)" :key="tool"
                          size="small" effect="plain">{{ tool }}</el-tag>
                </div>
                <div v-if="s.is_required" class="check">
                  <el-checkbox v-if="mode === 'execute'" v-model="checked[s.id]">
                    <span class="cp">合规确认：{{ s.checkpoint || '已按要求完成本步骤' }}</span>
                  </el-checkbox>
                  <div v-else class="cp-preview">
                    <el-icon><Select /></el-icon>
                    合规确认项：{{ s.checkpoint || '（未填写）' }}
                  </div>
                </div>
              </div>
            </template>
          </el-step>
        </el-steps>
      </div>

      <template #footer>
        <div v-if="mode === 'execute' && current" class="footer">
          <span class="progress">第 {{ active + 1 }} / {{ current.steps.length }} 步</span>
          <el-button :disabled="active === 0" @click="active--">上一步</el-button>
          <el-button v-if="active < current.steps.length - 1" type="primary"
                     :disabled="!canNext" @click="next">下一步</el-button>
          <el-button v-else type="success" :loading="submitting"
                     :disabled="!allRequiredChecked" @click="finish">完成作业</el-button>
        </div>
        <div v-else class="footer">
          <el-button @click="drawer = false">关闭</el-button>
          <el-button v-if="canEdit && current?.status === 'draft'" type="success"
                     @click="publish(current)">发布该流程</el-button>
        </div>
      </template>
    </el-drawer>

    <!-- AI 生成草稿对话框 -->
    <el-dialog v-model="genDialog" title="AI 生成作业流程草稿" width="460px">
      <el-form label-width="84px">
        <el-form-item label="设备类型">
          <el-input v-model="gen.device_type" placeholder="如：摩托车发动机" />
        </el-form-item>
        <el-form-item label="设备型号">
          <el-input v-model="gen.device_model" placeholder="可选，如：通用四冲程" />
        </el-form-item>
        <el-form-item label="检修等级">
          <el-select v-model="gen.repair_level" style="width: 100%">
            <el-option v-for="l in repairLevels" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" show-icon
                title="将依据知识库手册片段，由大模型生成流程草稿；保存为草稿后可校核再发布。" />
      <template #footer>
        <el-button @click="genDialog = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="doGenerate">生成草稿</el-button>
      </template>
    </el-dialog>

    <!-- 我的作业记录（审计闭环：已完成且合规通过的作业） -->
    <el-drawer v-model="recordsDrawer" title="我的作业记录" size="560px"
               :destroy-on-close="true">
      <div v-loading="recordsLoading" class="records">
        <el-empty v-if="!recordsLoading && records.length === 0" description="暂无作业记录" />
        <el-table v-else :data="records" stripe>
          <el-table-column prop="template_name" label="作业流程" min-width="170"
                           show-overflow-tooltip />
          <el-table-column label="设备型号" width="110">
            <template #default="{ row }">{{ row.device_model || '—' }}</template>
          </el-table-column>
          <el-table-column label="合规" width="92" align="center">
            <template #default>
              <el-tag type="success" size="small" effect="plain">校验通过</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="完成时间" width="150">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, VideoPlay, View, Select, Document } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

const auth = useAuthStore()
const canEdit = computed(() => ['auditor', 'admin'].includes(auth.user?.role))

const repairLevels = ['日常保养', '一级维护', '二级维护', '大修']
const deviceTypes = ['摩托车发动机']

const templates = ref([])
const loading = ref(false)
const filter = reactive({ device_type: '', repair_level: '' })

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filter.device_type) params.device_type = filter.device_type
    if (filter.repair_level) params.repair_level = filter.repair_level
    const { data } = await api.get('/sop/templates', { params })
    templates.value = data
  } catch (e) {
    ElMessage.error('加载作业流程失败')
  } finally {
    loading.value = false
  }
}

function splitTools(tools) {
  return tools.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
}

// ---- 抽屉：执行 / 预览 ----
const drawer = ref(false)
const mode = ref('execute') // execute | preview
const current = ref(null)
const active = ref(0)
const checked = reactive({})
const submitting = ref(false)

async function openTemplate(t, m) {
  try {
    const { data } = await api.get(`/sop/templates/${t.id}`)
    current.value = data
    mode.value = m
    Object.keys(checked).forEach((k) => delete checked[k])
    active.value = m === 'preview' ? data.steps.length : 0
    drawer.value = true
  } catch (e) {
    ElMessage.error('加载流程详情失败')
  }
}
const startRun = (t) => openTemplate(t, 'execute')
const preview = (t) => openTemplate(t, 'preview')

const currentStep = computed(() => current.value?.steps?.[active.value])
const canNext = computed(() => {
  const s = currentStep.value
  return !s || !s.is_required || !!checked[s.id]
})
const allRequiredChecked = computed(() =>
  (current.value?.steps || []).every((s) => !s.is_required || checked[s.id])
)
function stepStatus(idx) {
  if (mode.value === 'preview') return 'success'
  if (idx < active.value) return 'success'
  if (idx === active.value) return 'process'
  return 'wait'
}
function next() {
  if (!canNext.value) {
    ElMessage.warning('请先勾选确认本步骤的合规必检项')
    return
  }
  if (active.value < current.value.steps.length - 1) active.value++
}

async function finish() {
  submitting.value = true
  try {
    const checkedIds = current.value.steps.filter((s) => checked[s.id]).map((s) => s.id)
    await api.post('/sop/runs', {
      template_id: current.value.id,
      device_model: current.value.device_model,
      checked_step_ids: checkedIds,
      note: '',
    })
    ElMessage.success('作业完成，合规校验通过，已归档')
    drawer.value = false
  } catch (e) {
    const detail = e.response?.data?.detail
    if (detail && detail.missing) {
      const list = detail.missing
        .map((m) => `· 第${m.order_no}步：${m.checkpoint}`)
        .join('<br/>')
      ElMessageBox.alert(list, '合规校验未通过 · 缺项拦截', {
        type: 'error',
        dangerouslyUseHTMLString: true,
      })
    } else {
      ElMessage.error(typeof detail === 'string' ? detail : '提交失败')
    }
  } finally {
    submitting.value = false
  }
}

// ---- 发布 / 删除（审核员、管理员）----
async function publish(t) {
  try {
    await api.post(`/sop/templates/${t.id}/publish`)
    ElMessage.success('已发布')
    drawer.value = false
    await load()
  } catch (e) {
    ElMessage.error('发布失败')
  }
}
async function remove(t) {
  try {
    await ElMessageBox.confirm(`确认删除流程「${t.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/sop/templates/${t.id}`)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// ---- AI 生成草稿 ----
const genDialog = ref(false)
const generating = ref(false)
const gen = reactive({ device_type: '摩托车发动机', device_model: '', repair_level: '二级维护' })

async function doGenerate() {
  if (!gen.device_type) {
    ElMessage.warning('请填写设备类型')
    return
  }
  generating.value = true
  try {
    const { data } = await api.post('/sop/generate', {
      device_type: gen.device_type,
      device_model: gen.device_model || null,
      repair_level: gen.repair_level,
    })
    ElMessage.success(`已生成草稿：${data.name}`)
    genDialog.value = false
    await load()
    // 直接打开草稿供校核
    current.value = data
    mode.value = 'preview'
    active.value = data.steps.length
    drawer.value = true
  } catch (e) {
    const detail = e.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '生成失败，请重试')
  } finally {
    generating.value = false
  }
}

// ---- 我的作业记录（消费 GET /api/sop/runs）----
const recordsDrawer = ref(false)
const records = ref([])
const recordsLoading = ref(false)

async function openRecords() {
  recordsDrawer.value = true
  recordsLoading.value = true
  try {
    const { data } = await api.get('/sop/runs')
    records.value = data
  } catch (e) {
    ElMessage.error('加载作业记录失败')
  } finally {
    recordsLoading.value = false
  }
}

function formatTime(s) {
  if (!s) return ''
  // 后端 created_at 为 UTC（无时区后缀），补 Z 以正确换算为本地时间
  const iso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s) ? s : `${s}Z`
  const d = new Date(iso)
  if (isNaN(d.getTime())) return s
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.sop-page { display: flex; flex-direction: column; gap: 14px; }
.filter-bar :deep(.el-card__body) { padding: 12px 16px; }
.bar { display: flex; align-items: center; justify-content: space-between; }
.filters { display: flex; gap: 10px; }
.actions { display: flex; gap: 10px; }
.records { padding: 2px; }

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 14px;
}
.tpl-card :deep(.el-card__body) {
  display: flex; flex-direction: column; gap: 10px;
}
.tpl-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tpl-name { font-size: 15px; font-weight: 600; color: #1f2d3d; }
.tpl-meta { display: flex; align-items: center; gap: 8px; }
.step-count { color: #909399; font-size: 13px; }
.tpl-summary {
  color: #606266; font-size: 13px; line-height: 1.55; min-height: 40px;
}
.tpl-actions { display: flex; gap: 8px; }

.run { padding: 4px 6px; }
.run-tip { margin-bottom: 14px; }
.step-title { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; }
.step-body {
  padding: 8px 0 16px; display: flex; flex-direction: column; gap: 10px;
}
.instruction { margin: 0; color: #303133; line-height: 1.65; }
.tools { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.tools .label { color: #909399; font-size: 13px; }
.check { margin-top: 2px; }
.cp { font-weight: 500; }
.cp-preview {
  display: inline-flex; align-items: center; gap: 6px;
  color: #67c23a; font-size: 13px;
}
.footer { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.progress { margin-right: auto; color: #909399; font-size: 13px; }
</style>
