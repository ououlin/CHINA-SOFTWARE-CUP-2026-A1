<template>
  <div class="devices-page">
    <el-card shadow="never">
      <template #header>
        <div class="head">
          <div class="left">
            <span class="ttl">设备台账（一机一档）</span>
            <el-radio-group v-model="statusFilter" size="small" @change="load">
              <el-radio-button label="">全部</el-radio-button>
              <el-radio-button label="normal">运行中</el-radio-button>
              <el-radio-button label="repairing">维修中</el-radio-button>
              <el-radio-button label="stopped">停机</el-radio-button>
            </el-radio-group>
          </div>
          <el-button v-if="canEdit" type="primary" :icon="Plus" size="small"
                     @click="openCreate">建档</el-button>
        </div>
      </template>

      <el-table :data="devices" v-loading="loading" stripe>
        <el-table-column prop="code" label="资产编号" width="116" />
        <el-table-column prop="name" label="设备名称" min-width="190" show-overflow-tooltip />
        <el-table-column prop="device_model" label="型号" width="110" />
        <el-table-column prop="location" label="位置" width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="92">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="累计故障" width="86" align="center">
          <template #default="{ row }">
            <el-badge :value="row.fault_count" :max="99" :hidden="!row.fault_count"
                      type="info" class="cnt" />
            <span v-if="!row.fault_count" class="muted">0</span>
          </template>
        </el-table-column>
        <el-table-column label="未结" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.open_count" type="danger" size="small">{{ row.open_count }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190">
          <template #default="{ row }">
            <el-button size="small" text :icon="View" @click="openDetail(row.id)">档案</el-button>
            <el-button size="small" text type="warning" :icon="Warning"
                       @click="openReport(row)">报修</el-button>
            <el-button v-if="canEdit" size="small" text type="danger" :icon="Delete"
                       @click="doDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 设备档案抽屉 -->
    <el-drawer v-model="detailDrawer" :title="current?.name || '设备档案'" size="640px"
               :destroy-on-close="true">
      <div v-if="current" class="detail" v-loading="detailLoading">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="资产编号">{{ current.code }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(current.status)" size="small">{{ statusLabel(current.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="设备类型">{{ current.device_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="型号">{{ current.device_model || '—' }}</el-descriptions-item>
          <el-descriptions-item label="安装位置">{{ current.location || '—' }}</el-descriptions-item>
          <el-descriptions-item label="投运日期">{{ fmtDate(current.commissioned_at) }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ current.note || '—' }}</el-descriptions-item>
        </el-descriptions>

        <div class="overview">
          <div class="stat"><span class="num">{{ current.fault_count }}</span><span class="lbl">累计故障</span></div>
          <div class="stat"><span class="num warn">{{ current.open_count }}</span><span class="lbl">未结报修</span></div>
          <div class="stat"><span class="num">{{ current.linked_cases.length }}</span><span class="lbl">关联案例</span></div>
          <div class="stat"><span class="num">{{ current.linked_sops.length }}</span><span class="lbl">适用指引</span></div>
          <div class="acts">
            <el-button type="warning" plain :icon="Warning" size="small"
                       @click="openReport(current)">提交报修</el-button>
            <el-button type="primary" plain :icon="Document" size="small"
                       :loading="reportDocLoading" @click="genReportDoc">生成检修报告</el-button>
          </div>
        </div>

        <el-tabs v-model="tab">
          <el-tab-pane label="检修时间线" name="timeline">
            <el-empty v-if="!current.records.length" description="暂无报修/检修记录" :image-size="70" />
            <el-timeline v-else>
              <el-timeline-item v-for="r in current.records" :key="r.id"
                                :timestamp="fmtTime(r.created_at)" placement="top"
                                :type="recordDotType(r)">
                <el-card shadow="never" class="rec-card">
                  <div class="rec-head">
                    <span class="rec-title">{{ r.title }}</span>
                    <el-tag :type="sevType(r.severity)" size="small" effect="plain">{{ sevLabel(r.severity) }}</el-tag>
                    <el-tag :type="recStatusType(r.status)" size="small">{{ recStatusLabel(r.status) }}</el-tag>
                  </div>
                  <p v-if="r.fault_desc" class="rec-line"><b>现象：</b>{{ r.fault_desc }}</p>
                  <p v-if="r.handling" class="rec-line"><b>处理：</b>{{ r.handling }}</p>
                  <div class="rec-foot">
                    <span>报修：{{ r.reporter_name || '—' }}</span>
                    <span v-if="r.handler_name">· 处理：{{ r.handler_name }}</span>
                    <el-button v-if="canEdit && r.status !== 'done'" size="small" type="success"
                               text @click="handleRecord(r)">登记处理</el-button>
                  </div>
                </el-card>
              </el-timeline-item>
            </el-timeline>
          </el-tab-pane>

          <el-tab-pane label="适用知识" name="knowledge">
            <el-divider content-position="left">同型号检修案例</el-divider>
            <el-empty v-if="!current.linked_cases.length" description="暂无关联案例" :image-size="60" />
            <ul v-else class="klist">
              <li v-for="c in current.linked_cases" :key="c.id">
                <el-icon><Document /></el-icon>{{ c.title }}
                <el-tag size="small" effect="plain">{{ c.device_model || '通用' }}</el-tag>
              </li>
            </ul>
            <el-divider content-position="left">适用作业指引（SOP）</el-divider>
            <el-empty v-if="!current.linked_sops.length" description="暂无适用指引" :image-size="60" />
            <ul v-else class="klist">
              <li v-for="s in current.linked_sops" :key="s.id">
                <el-icon><Tickets /></el-icon>{{ s.name }}
                <el-tag size="small" type="success" effect="plain">{{ s.repair_level || '通用' }}</el-tag>
              </li>
            </ul>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-drawer>

    <!-- 建档对话框 -->
    <el-dialog v-model="editDialog" title="设备建档" width="520px">
      <el-form label-width="84px">
        <el-form-item label="资产编号"><el-input v-model="form.code" placeholder="如：MTO-2304" /></el-form-item>
        <el-form-item label="设备名称"><el-input v-model="form.name" placeholder="如：本田 CG125 发动机" /></el-form-item>
        <el-form-item label="设备类型"><el-input v-model="form.device_type" placeholder="如：摩托车发动机" /></el-form-item>
        <el-form-item label="型号"><el-input v-model="form.device_model" placeholder="如：通用四冲程" /></el-form-item>
        <el-form-item label="安装位置"><el-input v-model="form.location" placeholder="如：实训楼 A-101" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status">
            <el-option label="运行中" value="normal" />
            <el-option label="维修中" value="repairing" />
            <el-option label="停机" value="stopped" />
            <el-option label="报废" value="scrapped" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 报修对话框 -->
    <el-dialog v-model="reportDialog" :title="`报修 · ${reportTarget?.name || ''}`" width="500px">
      <el-form label-width="72px">
        <el-form-item label="标题"><el-input v-model="reportForm.title" placeholder="如：怠速不稳、易熄火" /></el-form-item>
        <el-form-item label="严重度">
          <el-radio-group v-model="reportForm.severity">
            <el-radio-button label="general">一般</el-radio-button>
            <el-radio-button label="serious">严重</el-radio-button>
            <el-radio-button label="urgent">紧急</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="故障描述">
          <el-input v-model="reportForm.fault_desc" type="textarea" :rows="4"
                    placeholder="描述故障现象、发生条件……" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reportDialog = false">取消</el-button>
        <el-button type="warning" :loading="reporting" @click="doReport">提交报修</el-button>
      </template>
    </el-dialog>

    <!-- 智能检修报告 -->
    <el-dialog v-model="reportDocDialog" title="设备检修报告（AI 生成）" width="700px" top="6vh">
      <div v-loading="reportDocLoading" element-loading-text="大模型正在汇总检修报告……"
           class="report-wrap">
        <div class="report-md">{{ reportDocText }}</div>
      </div>
      <template #footer>
        <el-button @click="reportDocDialog = false">关闭</el-button>
        <el-button type="primary" :icon="Download" :disabled="!reportDocText"
                   @click="downloadReportDoc">下载 Markdown</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, View, Warning, Delete, Document, Tickets, Download } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

const auth = useAuthStore()
const canEdit = computed(() => ['auditor', 'admin'].includes(auth.user?.role))

const devices = ref([])
const loading = ref(false)
const statusFilter = ref('')

const STATUS = {
  normal: { label: '运行中', type: 'success' },
  repairing: { label: '维修中', type: 'warning' },
  stopped: { label: '停机', type: 'info' },
  scrapped: { label: '报废', type: 'danger' },
}
const statusLabel = (s) => STATUS[s]?.label || s
const statusType = (s) => STATUS[s]?.type || ''

const SEV = {
  general: { label: '一般', type: 'info' },
  serious: { label: '严重', type: 'warning' },
  urgent: { label: '紧急', type: 'danger' },
}
const sevLabel = (s) => SEV[s]?.label || s
const sevType = (s) => SEV[s]?.type || 'info'

const REC_STATUS = {
  open: { label: '待处理', type: 'danger' },
  processing: { label: '处理中', type: 'warning' },
  done: { label: '已完成', type: 'success' },
}
const recStatusLabel = (s) => REC_STATUS[s]?.label || s
const recStatusType = (s) => REC_STATUS[s]?.type || ''
const recordDotType = (r) => r.status === 'done' ? 'success'
  : (r.severity === 'urgent' ? 'danger' : 'warning')

function fmtTime(s) {
  if (!s) return ''
  const d = new Date(s.endsWith('Z') ? s : s + 'Z')
  return d.toLocaleString('zh-CN', { hour12: false })
}
function fmtDate(s) {
  if (!s) return '—'
  const d = new Date(s.endsWith('Z') ? s : s + 'Z')
  return d.toLocaleDateString('zh-CN')
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    const { data } = await api.get('/devices', { params })
    devices.value = data
  } catch (e) {
    ElMessage.error('加载设备台账失败')
  } finally {
    loading.value = false
  }
}

// ---- 档案详情 ----
const detailDrawer = ref(false)
const detailLoading = ref(false)
const current = ref(null)
const tab = ref('timeline')
async function openDetail(id) {
  detailDrawer.value = true
  detailLoading.value = true
  tab.value = 'timeline'
  try {
    const { data } = await api.get(`/devices/${id}`)
    current.value = data
  } catch (e) {
    ElMessage.error('加载档案失败')
  } finally {
    detailLoading.value = false
  }
}

// ---- 建档 ----
const editDialog = ref(false)
const saving = ref(false)
const form = reactive({ code: '', name: '', device_type: '', device_model: '', location: '', status: 'normal', note: '' })
function openCreate() {
  Object.assign(form, { code: '', name: '', device_type: '摩托车发动机', device_model: '通用四冲程', location: '', status: 'normal', note: '' })
  editDialog.value = true
}
async function doSave() {
  if (!form.code.trim() || !form.name.trim()) {
    ElMessage.warning('请填写资产编号与设备名称')
    return
  }
  saving.value = true
  try {
    await api.post('/devices', { ...form })
    ElMessage.success('已建档')
    editDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function doDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除设备「${row.name}」及其全部报修记录？`, '删除设备',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await api.delete(`/devices/${row.id}`)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ---- 报修 ----
const reportDialog = ref(false)
const reporting = ref(false)
const reportTarget = ref(null)
const reportForm = reactive({ title: '', severity: 'general', fault_desc: '' })
function openReport(device) {
  reportTarget.value = device
  Object.assign(reportForm, { title: '', severity: 'general', fault_desc: '' })
  reportDialog.value = true
}
async function doReport() {
  if (!reportForm.title.trim()) {
    ElMessage.warning('请填写报修标题')
    return
  }
  reporting.value = true
  try {
    await api.post(`/devices/${reportTarget.value.id}/records`, { ...reportForm })
    ElMessage.success('报修已提交')
    reportDialog.value = false
    await load()
    if (detailDrawer.value && current.value?.id === reportTarget.value.id) {
      await openDetail(current.value.id)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '报修失败')
  } finally {
    reporting.value = false
  }
}

// ---- 处理报修 ----
async function handleRecord(r) {
  let handling = ''
  try {
    const res = await ElMessageBox.prompt('请填写处理措施', '登记处理', {
      confirmButtonText: '标记完成', cancelButtonText: '取消', inputType: 'textarea',
    })
    handling = res.value || ''
  } catch { return }
  try {
    await api.post(`/devices/records/${r.id}/handle`, { handling, status: 'done' })
    ElMessage.success('已登记处理')
    await openDetail(current.value.id)
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

// ---- 智能检修报告（G5）----
const reportDocDialog = ref(false)
const reportDocLoading = ref(false)
const reportDocText = ref('')
const reportDocMeta = reactive({ code: '', device: '' })
async function genReportDoc() {
  if (!current.value) return
  reportDocLoading.value = true
  reportDocDialog.value = true
  reportDocText.value = ''
  try {
    const { data } = await api.post(`/devices/${current.value.id}/report`)
    reportDocText.value = data.report
    reportDocMeta.code = data.code
    reportDocMeta.device = data.device
  } catch (e) {
    reportDocDialog.value = false
    ElMessage.error(e.response?.data?.detail || '报告生成失败')
  } finally {
    reportDocLoading.value = false
  }
}
function downloadReportDoc() {
  if (!reportDocText.value) return
  const today = new Date().toISOString().slice(0, 10)
  const blob = new Blob([reportDocText.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `检修报告_${reportDocMeta.code || 'device'}_${today}.md`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; }
.left { display: flex; align-items: center; gap: 16px; }
.ttl { font-weight: 600; }
.muted { color: #c0c4cc; }
.cnt { margin-top: 4px; }
.detail { padding: 2px 4px; }
.overview { display: flex; align-items: center; gap: 28px; margin: 18px 4px; }
.overview .stat { display: flex; flex-direction: column; align-items: center; }
.overview .num { font-size: 26px; font-weight: 700; color: #1f2329; letter-spacing: -.4px; }
.overview .num.warn { color: #e6a23c; }
.overview .lbl { font-size: 12px; color: #909399; }
.overview .acts { margin-left: auto; display: flex; gap: 8px; }
.report-wrap { min-height: 180px; max-height: 60vh; overflow-y: auto; }
.report-md {
  white-space: pre-wrap; line-height: 1.75; color: #303133; font-size: 14px;
  padding: 4px 2px;
}
.rec-card { margin-bottom: 2px; }
.rec-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.rec-title { font-weight: 600; }
.rec-line { margin: 3px 0; color: #303133; line-height: 1.6; }
.rec-foot { display: flex; align-items: center; gap: 8px; color: #909399; font-size: 12px; margin-top: 6px; }
.rec-foot .el-button { margin-left: auto; }
.klist { list-style: none; padding: 0; margin: 0; }
.klist li { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f0f2f5; }
</style>
