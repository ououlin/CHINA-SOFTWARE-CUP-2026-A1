<template>
  <div class="scan-page">
    <el-row :gutter="14">
      <el-col :span="11">
        <div class="panel">
          <div class="ptitle">扫码 / 输入编号报修</div>
          <el-tabs v-model="mode" @tab-change="onTabChange">
            <el-tab-pane label="摄像头扫码" name="camera">
              <div v-show="scanning" id="qr-reader" class="qr-reader"></div>
              <div class="scan-acts">
                <el-button v-if="!scanning" type="primary" :icon="VideoCamera"
                           @click="startScan">启动摄像头扫码</el-button>
                <el-button v-else @click="stopScan">停止</el-button>
              </div>
              <el-text v-if="!scanning" size="small" type="info">
                若设备无摄像头，请切换「手动输入」标签页。
              </el-text>
            </el-tab-pane>
            <el-tab-pane label="手动输入" name="manual">
              <el-input v-model="codeInput" placeholder="输入资产编号，如 MTO-2301" clearable
                        @keyup.enter="queryByCode(codeInput)">
                <template #append>
                  <el-button :icon="Search" @click="queryByCode(codeInput)">查询</el-button>
                </template>
              </el-input>
            </el-tab-pane>
          </el-tabs>

          <!-- 查到设备 -->
          <div v-if="device" class="found">
            <el-divider content-position="left">{{ device.name }}</el-divider>
            <div class="dev-meta">
              <el-tag size="small">{{ device.code }}</el-tag>
              <el-tag size="small" effect="plain">{{ device.device_model || '通用' }}</el-tag>
              <el-tag :type="statusType(device.status)" size="small">{{ statusLabel(device.status) }}</el-tag>
              <span class="loc">{{ device.location || '' }}</span>
            </div>
            <div class="dev-hint" v-if="device.open_count">
              <el-icon><Warning /></el-icon> 该设备当前有 {{ device.open_count }} 项未结报修
            </div>
            <el-form label-width="64px" class="rep-form">
              <el-form-item label="标题">
                <el-input v-model="rep.title" placeholder="如：怠速不稳、易熄火" />
              </el-form-item>
              <el-form-item label="严重度">
                <el-radio-group v-model="rep.severity">
                  <el-radio-button label="general">一般</el-radio-button>
                  <el-radio-button label="serious">严重</el-radio-button>
                  <el-radio-button label="urgent">紧急</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="rep.fault_desc" type="textarea" :rows="3"
                          placeholder="描述故障现象……" />
              </el-form-item>
            </el-form>
            <div class="rep-submit">
              <el-button @click="device = null">重新扫码</el-button>
              <el-button type="warning" :loading="submitting" @click="submitReport">提交报修</el-button>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :span="13">
        <div class="panel">
          <div class="ptitle">设备二维码（打印张贴，扫码即报修）</div>
          <div class="qr-wall" v-loading="loading">
            <div v-for="d in devices" :key="d.id" class="qr-item">
              <img v-if="qrMap[d.code]" :src="qrMap[d.code]" class="qr-img" />
              <div class="qr-code">{{ d.code }}</div>
              <div class="qr-name" :title="d.name">{{ d.name }}</div>
              <el-button text size="small" :icon="Download" @click="downloadQR(d)">下载</el-button>
            </div>
            <el-empty v-if="!loading && !devices.length" description="暂无设备" :image-size="56" />
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoCamera, Search, Download, Warning } from '@element-plus/icons-vue'
import QRCode from 'qrcode'
import { Html5Qrcode } from 'html5-qrcode'
import api from '../api'

const STATUS = {
  normal: { label: '运行中', type: 'success' },
  repairing: { label: '维修中', type: 'warning' },
  stopped: { label: '停机', type: 'info' },
  scrapped: { label: '报废', type: 'danger' },
}
const statusLabel = (s) => STATUS[s]?.label || s
const statusType = (s) => STATUS[s]?.type || ''

const mode = ref('manual')
const codeInput = ref('')
const device = ref(null)

const devices = ref([])
const qrMap = reactive({})
const loading = ref(false)

async function loadDevices() {
  loading.value = true
  try {
    const { data } = await api.get('/devices')
    devices.value = data
    for (const d of data) {
      qrMap[d.code] = await QRCode.toDataURL(d.code, { width: 132, margin: 1 })
    }
  } catch (e) {
    ElMessage.error('加载设备失败')
  } finally {
    loading.value = false
  }
}

function downloadQR(d) {
  if (!qrMap[d.code]) return
  const a = document.createElement('a')
  a.href = qrMap[d.code]
  a.download = `二维码_${d.code}.png`
  a.click()
}

// ---- 查询设备 ----
function parseCode(text) {
  // 二维码内容可能是纯编号或含 code 参数的 URL
  const m = String(text).match(/[?&]code=([^&]+)/)
  return m ? decodeURIComponent(m[1]) : String(text).trim()
}

async function queryByCode(raw) {
  const code = parseCode(raw)
  if (!code) { ElMessage.warning('请输入资产编号'); return }
  try {
    const { data } = await api.get(`/devices/by-code/${encodeURIComponent(code)}`)
    device.value = data
    Object.assign(rep, { title: '', severity: 'general', fault_desc: '' })
  } catch (e) {
    device.value = null
    ElMessage.error(e.response?.data?.detail || `未找到设备 ${code}`)
  }
}

// ---- 摄像头扫码 ----
const scanning = ref(false)
let html5Qr = null

async function startScan() {
  scanning.value = true
  await nextTick()
  try {
    html5Qr = new Html5Qrcode('qr-reader')
    await html5Qr.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: 220 },
      (decoded) => { onScanned(decoded) },
      () => {},
    )
  } catch (e) {
    scanning.value = false
    ElMessage.warning('无法启动摄像头，请改用「手动输入」：' + (e?.message || e))
  }
}

async function stopScan() {
  if (html5Qr) {
    try { await html5Qr.stop() } catch (e) { /* ignore */ }
    try { html5Qr.clear() } catch (e) { /* ignore */ }
    html5Qr = null
  }
  scanning.value = false
}

function onScanned(text) {
  stopScan()
  queryByCode(text)
}

function onTabChange(name) {
  if (name !== 'camera') stopScan()
}

// ---- 报修 ----
const submitting = ref(false)
const rep = reactive({ title: '', severity: 'general', fault_desc: '' })
async function submitReport() {
  if (!rep.title.trim()) { ElMessage.warning('请填写报修标题'); return }
  submitting.value = true
  try {
    await api.post(`/devices/${device.value.id}/records`, { ...rep })
    ElMessage.success('报修已提交')
    device.value = null
    await loadDevices()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '报修失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadDevices)
onBeforeUnmount(stopScan)
</script>

<style scoped>
.scan-page { display: flex; flex-direction: column; }
.panel {
  background: #fff; border-radius: 10px; padding: 14px 16px;
  border: 1px solid #ebeef5; box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
  min-height: 460px;
}
.ptitle { font-size: 14px; font-weight: 600; color: #303133; margin-bottom: 8px; }
.ptitle::before {
  content: ''; display: inline-block; width: 3px; height: 13px;
  background: #14418c; border-radius: 2px; margin-right: 7px; vertical-align: -1px;
}
.qr-reader { width: 100%; max-width: 320px; margin: 0 auto 10px; }
.scan-acts { margin: 10px 0 6px; }
.found { margin-top: 6px; }
.dev-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dev-meta .loc { color: #909399; font-size: 13px; margin-left: auto; }
.dev-hint { color: #e6a23c; font-size: 13px; margin: 8px 0; display: flex; align-items: center; gap: 4px; }
.rep-form { margin-top: 12px; }
.rep-submit { display: flex; justify-content: flex-end; gap: 8px; }
.qr-wall {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 14px; padding: 4px;
}
.qr-item {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  border: 1px solid #ebeef5; border-radius: 8px; padding: 10px 6px;
}
.qr-img { width: 116px; height: 116px; }
.qr-code { font-weight: 600; font-size: 13px; color: #14418c; }
.qr-name {
  font-size: 12px; color: #909399; max-width: 116px; text-align: center;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
</style>
