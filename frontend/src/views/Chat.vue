<template>
  <div class="chat-page">
    <div class="messages" ref="msgBox">
      <div v-if="messages.length === 0" class="empty">
        <div class="empty-illus">
          <el-icon :size="64" color="var(--brand)"><ChatDotRound /></el-icon>
        </div>
        <h3 class="empty-title">您好，我是检修智能助手</h3>
        <p class="empty-desc">支持文本提问、故障图片识别、语音输入；可指定设备型号获得更精准的检索结果。</p>
        <div class="examples">
          <div v-for="q in examples" :key="q" class="example"
               @click="useExample(q)">
            <el-icon class="ex-icon"><Promotion /></el-icon>
            <span>{{ q }}</span>
            <el-icon class="ex-arrow"><Right /></el-icon>
          </div>
        </div>
      </div>

      <!-- SSE 断线重连提示条 -->
      <div v-if="reconnect.status" class="reconnect-bar" :class="reconnect.status">
        <el-icon v-if="reconnect.status === 'reconnecting'" class="is-loading">
          <Loading />
        </el-icon>
        <el-icon v-else-if="reconnect.status === 'failed'"><WarnTriangleFilled /></el-icon>
        <span>{{ reconnectMsg }}</span>
        <el-button v-if="reconnect.status === 'failed'" size="small" type="primary"
                   @click="retryLastSend">点击重试</el-button>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="avatar">
          <el-icon v-if="m.role === 'user'"><UserFilled /></el-icon>
          <el-icon v-else><Service /></el-icon>
        </div>
        <div class="bubble">
          <img v-if="m.image" :src="m.image" class="msg-image" />

          <!-- AI 思考中的骨架屏（取代"正在思考…"文字） -->
          <div v-if="m.role === 'assistant' && m.loading && !m.content"
               class="think-skeleton">
            <div class="ts-line skeleton-box w-90"></div>
            <div class="ts-line skeleton-box w-100"></div>
            <div class="ts-line skeleton-box w-70"></div>
            <div class="ts-line skeleton-box w-100"></div>
            <div class="ts-line skeleton-box w-50"></div>
            <div class="ts-hint">
              <span class="dot-loader"><i></i><i></i><i></i></span>
              AI 正在检索知识库与生成回答…
            </div>
          </div>

          <div v-if="m.appliedCorrections && m.appliedCorrections.length"
               class="applied-corr">
            <el-tag type="warning" size="small" effect="dark" class="corr-badge">
              <el-icon><MagicStick /></el-icon>&nbsp;本回答已采纳
              {{ m.appliedCorrections.length }} 条人工修正知识
            </el-tag>
            <el-collapse class="ac-collapse">
              <el-collapse-item title="查看采纳的修正">
                <div v-for="(c, ci) in m.appliedCorrections" :key="ci" class="ac-item">
                  <div class="ac-q">原相似问题：{{ c.query }}</div>
                  <div class="ac-t">{{ c.correction_text }}</div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>

          <div v-if="m.role === 'user'" class="content">{{ m.content }}</div>
          <!-- AI 思考中无内容时仅显示骨架屏；流式输出时显示打字光标 -->
          <div v-else-if="m.streaming && m.content" class="content typing">
            {{ m.content }}<span class="type-cursor"></span>
          </div>
          <div v-else-if="!m.loading && m.content" class="markdown-body"
               v-html="renderMarkdown(m.content || '')"
               @click="onCiteClick($event, m)"></div>

          <div v-if="m.confidence" class="confidence-box" :class="`conf-${m.confidence.level}`">
            <div class="conf-head">
              <el-icon><CircleCheck /></el-icon>
              <span>回答可信度：{{ confidenceLabel(m.confidence.level) }} · {{ Math.round((m.confidence.score || 0) * 100) }}分</span>
            </div>
            <div v-if="m.confidence.reasons && m.confidence.reasons.length" class="conf-tags">
              <el-tag v-for="r in m.confidence.reasons" :key="r" size="small" effect="plain">{{ r }}</el-tag>
            </div>
            <div v-if="m.confidence.warnings && m.confidence.warnings.length" class="conf-warnings">
              <span v-for="w in m.confidence.warnings" :key="w">{{ w }}</span>
            </div>
          </div>

          <el-alert v-if="m.safety?.requires_human_confirmation"
                    class="safety-alert" type="warning" :closable="false" show-icon
                    title="高风险作业需人工确认" :description="m.safety.message" />

          <div v-if="m.rewritten" class="rewrite-hint">
            <el-icon><Search /></el-icon>
            <span>已按工业术语优化检索：{{ m.rewritten }}</span>
          </div>

          <el-collapse v-if="m.vl" class="vl-box">
            <el-collapse-item>
              <template #title>
                <el-icon><View /></el-icon>&nbsp;图片识别结果（Qwen-VL）
              </template>
              <div class="vl-content">{{ m.vl }}</div>
            </el-collapse-item>
          </el-collapse>

          <div v-if="m.graph && m.graph.length" class="graph-box">
            <div class="graph-title">
              <el-icon><Share /></el-icon>&nbsp;知识图谱关联（Graph RAG · {{ m.graph.length }} 条）
            </div>
            <div class="graph-rels">
              <span v-for="(g, gi) in m.graph" :key="gi" class="graph-rel">{{ g }}</span>
            </div>
          </div>

          <div v-if="m.recommended_sops && m.recommended_sops.length" class="sop-box">
            <div class="sop-title">
              <el-icon><Tickets /></el-icon>&nbsp;推荐作业指引
            </div>
            <div v-for="s in m.recommended_sops" :key="s.id" class="sop-item">
              <div class="sop-head">
                <strong>{{ s.name }}</strong>
                <el-tag size="small" type="success" effect="plain">{{ Math.round((s.score || 0) * 100) }}%</el-tag>
              </div>
              <div class="sop-meta">{{ s.device_type || '通用类型' }} · {{ s.repair_level || '未指定等级' }}</div>
              <div class="sop-summary">{{ s.summary }}</div>
            </div>
          </div>

          <div v-if="m.citations && m.citations.length" class="citations">
            <div class="cite-title">参考来源 · 混合重排</div>
            <div v-for="(c, idx) in m.citations" :key="idx" class="cite"
                 :class="{ 'cite-hl': m.highlightCite === idx + 1 }">
              <div class="cite-head">
                <el-tag size="small" type="primary" effect="plain">[{{ idx + 1 }}]</el-tag>
                <span class="cite-src">{{ c.doc_title }}{{ c.page ? ` · 第${c.page}页` : '' }}</span>
                <div v-if="c.vec_score !== undefined" class="cite-scores">
                  <span class="sc-comp">综合 {{ c.score }}</span>
                  <span class="mini" title="语义相似度">
                    <i class="lbl">语义</i>
                    <span class="bar"><b :style="{ width: pct(c.vec_score), background: '#3b82f6' }"></b></span>
                  </span>
                  <span class="mini" title="字面词项重叠">
                    <i class="lbl">字面</i>
                    <span class="bar"><b :style="{ width: pct(c.lex_score), background: '#22c55e' }"></b></span>
                  </span>
                </div>
              </div>
              <div class="cite-content">{{ c.content }}</div>
            </div>
          </div>

          <!-- M5 标注修正：点赞/点踩 + 文字纠正 -->
          <div v-if="m.role === 'assistant' && m.qaId && !m.loading" class="feedback">
            <span class="fb-label">这条回答有帮助吗？</span>
            <el-button size="small" plain :type="m.vote === 'up' ? 'success' : ''"
                       @click="vote(m, 'up')">👍 有用</el-button>
            <el-button size="small" plain :type="m.vote === 'down' ? 'danger' : ''"
                       @click="vote(m, 'down')">👎 没用</el-button>
            <el-button size="small" text :icon="EditPen"
                       @click="m.feedbackOpen = !m.feedbackOpen">纠正</el-button>
            <span v-if="m.feedbackSaved" class="fb-saved">
              <el-icon><CircleCheck /></el-icon> 已记录反馈
            </span>
          </div>
          <div v-if="m.feedbackOpen" class="correction-box">
            <el-input v-model="m.correctionText" type="textarea" :rows="2"
                      placeholder="请填写对该回答的纠正，将沉淀为修正知识用于优化后续相似问题…" />
            <div class="cb-actions">
              <el-button size="small" @click="m.feedbackOpen = false">取消</el-button>
              <el-button size="small" type="primary" :loading="m.saving"
                         @click="saveCorrection(m)">提交纠正</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="composer">
      <div class="composer-left">
        <el-select v-model="selectedDeviceId" class="device" placeholder="选择设备(可选)"
                   filterable clearable @change="onDeviceChange">
          <el-option v-for="d in devices" :key="d.id" :label="`${d.name} · ${d.code}`"
                     :value="d.id">
            <span>{{ d.name }} · {{ d.code }}</span>
            <small class="dev-opt">{{ d.device_model || d.device_type }}</small>
          </el-option>
        </el-select>
        <el-upload :auto-upload="false" :show-file-list="false" accept="image/*"
                   :on-change="onPickImage" class="img-upload">
          <el-button :icon="Picture">故障图片</el-button>
        </el-upload>
        <el-button class="voice-btn" :class="{ rec: listening }"
                   :type="listening ? 'danger' : ''" @click="toggleVoice">
          <template v-if="!listening">
            <el-icon><Microphone /></el-icon>&nbsp;语音输入
          </template>
          <span v-else class="wave"><i></i><i></i><i></i><i></i><i></i></span>
        </el-button>
      </div>
      <div class="composer-main">
        <div v-if="pickedPreview" class="preview">
          <img :src="pickedPreview" />
          <el-icon class="remove" @click="clearImage"><CircleClose /></el-icon>
        </div>
        <el-input v-model="input" type="textarea" :rows="2" resize="none"
                  placeholder="请输入检修问题；可只传图片。Enter 发送 / Shift+Enter 换行"
                  @keydown.enter.exact.prevent="send" />
      </div>
      <el-button type="primary" :loading="sending" @click="send">发送</el-button>
      <el-button type="warning" plain @click="goAgent" :icon="Position">Agent 诊断</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Picture, CircleClose, View, EditPen, MagicStick, CircleCheck, Microphone, Search, Share, Tickets,
  Loading, WarnTriangleFilled, Promotion, Right, Position,
} from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import api from '../api'
import { useAuthStore } from '../store'

marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text) {
  if (!text) return ''
  const html = DOMPurify.sanitize(marked.parse(text))
  // 句末引用标记 [1][2] 转为可点击锚点（点击高亮对应来源卡片）
  return html.replace(/\[(\d{1,2})\]/g, '<span class="cite-ref" data-idx="$1">[$1]</span>')
}

const pct = (v) => `${Math.round((v || 0) * 100)}%`
const confidenceLabel = (level) => ({ high: '高', medium: '中', low: '低' }[level] || '中')

function onCiteClick(e, m) {
  const ref = e.target.closest('.cite-ref')
  if (!ref) return
  const idx = parseInt(ref.dataset.idx, 10)
  if (!idx || !m.citations || idx > m.citations.length) return
  m.highlightCite = idx
  setTimeout(() => { if (m.highlightCite === idx) m.highlightCite = 0 }, 1600)
}

const auth = useAuthStore()
const router = useRouter()

function goAgent() {
  router.push({ path: '/agent', query: input.value.trim() ? { q: input.value.trim() } : {} })
}
const messages = ref([])
const input = ref('')
const deviceModel = ref('')
const selectedDeviceId = ref(null)
const devices = ref([])
const sending = ref(false)
const msgBox = ref(null)

const pickedFile = ref(null)
const pickedPreview = ref('')

// ---- SSE 断线重连状态 ----
// status: '' | 'reconnecting' | 'failed'
// 重连最多 3 次，间隔递增 1s / 2s / 4s
const reconnect = reactive({ status: '', attempt: 0 })
const reconnectMsg = computed(() => {
  if (reconnect.status === 'reconnecting') {
    return `连接中断，正在重连…（第 ${reconnect.attempt} / 3 次）`
  }
  if (reconnect.status === 'failed') return '网络异常，请刷新页面或点击重试'
  return ''
})
// 缓存最近一次请求参数，便于断线后重试
let lastRequest = null

const examples = [
  '发动机怠速不稳怎么排查？',
  '火花塞电极发黑说明什么问题？',
  '气门间隙标准是多少，过大有什么影响？',
  '发动机过热如何处理？',
]

async function loadDevices() {
  try {
    const { data } = await api.get('/devices')
    devices.value = data || []
  } catch (e) {
    devices.value = []
  }
}

function onDeviceChange(id) {
  const d = devices.value.find((x) => x.id === id)
  deviceModel.value = d ? d.device_model : ''
}

onMounted(loadDevices)

function useExample(q) {
  input.value = q
}

function onPickImage(uploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  if (!raw.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件')
    return
  }
  pickedFile.value = raw
  pickedPreview.value = URL.createObjectURL(raw)
}

function clearImage() {
  pickedFile.value = null
  pickedPreview.value = ''
}

// ---- G4 语音输入（Web Speech API，纯前端）----
const listening = ref(false)
const voiceSupported = !!(window.SpeechRecognition || window.webkitSpeechRecognition)
let recognition = null
let voiceBase = ''   // 开始录音时输入框已有内容

function initRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SR) return null
  const r = new SR()
  r.lang = 'zh-CN'
  r.interimResults = true
  r.continuous = false
  r.onresult = (e) => {
    let finalText = ''
    let interim = ''
    for (let i = 0; i < e.results.length; i++) {
      const t = e.results[i][0].transcript
      if (e.results[i].isFinal) finalText += t
      else interim += t
    }
    input.value = voiceBase + finalText + interim
  }
  r.onend = () => { listening.value = false }
  r.onerror = (ev) => {
    listening.value = false
    if (ev.error === 'not-allowed') ElMessage.warning('麦克风权限被拒绝，请在浏览器允许后重试')
    else if (ev.error !== 'no-speech' && ev.error !== 'aborted') ElMessage.warning('语音识别出错：' + ev.error)
  }
  return r
}

function toggleVoice() {
  if (!voiceSupported) {
    ElMessage.warning('当前浏览器不支持语音识别，建议使用 Chrome / Edge')
    return
  }
  if (listening.value) {
    recognition && recognition.stop()
    listening.value = false
    return
  }
  if (!recognition) recognition = initRecognition()
  voiceBase = input.value ? input.value.trimEnd() + ' ' : ''
  try {
    recognition.start()
    listening.value = true
  } catch (e) { /* start 在已运行时会抛错，忽略 */ }
}

onBeforeUnmount(() => {
  if (recognition && listening.value) recognition.abort()
})

async function scrollBottom() {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}

async function send() {
  const query = input.value.trim()
  if ((!query && !pickedFile.value) || sending.value) return

  // 多轮上下文：取已完成的历史轮次（不含本次），最近 6 条
  const history = messages.value
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.content && !m.loading)
    .map((m) => ({ role: m.role, content: m.content }))
    .slice(-6)

  const userMsg = { role: 'user', content: query }
  if (pickedFile.value) userMsg.image = pickedPreview.value
  messages.value.push(userMsg)

  const assistant = {
    role: 'assistant', content: '', citations: [], vl: '', rewritten: '', graph: [],
    confidence: null, recommended_sops: [], safety: null,
    loading: true, streaming: true, highlightCite: 0,
    qaId: null, appliedCorrections: [], vote: '',
    feedbackOpen: false, correctionText: '', feedbackSaved: false, saving: false,
  }
  messages.value.push(assistant)
  sending.value = true
  const hasImage = !!pickedFile.value

  // 缓存请求参数，便于断线后重试
  lastRequest = {
    hasImage,
    query,
    history,
    file: pickedFile.value,
    preview: pickedPreview.value,
    deviceModel: deviceModel.value,
    deviceId: selectedDeviceId.value,
  }
  input.value = ''
  if (hasImage) clearImage()
  await scrollBottom()

  await runStream(assistant, lastRequest)
}

// 执行 SSE 请求与流式解析；遇到网络异常时触发自动重连
async function runStream(assistant, req) {
  try {
    let resp
    if (req.hasImage) {
      const fd = new FormData()
      fd.append('image', req.file)
      if (req.query) fd.append('query', req.query)
      if (req.deviceModel) fd.append('device_model', req.deviceModel)
      if (req.deviceId) fd.append('device_id', String(req.deviceId))
      resp = await fetch('/api/chat/ask_image', {
        method: 'POST',
        headers: { Authorization: `Bearer ${auth.token}` },
        body: fd,
      })
    } else {
      resp = await fetch('/api/chat/ask_stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${auth.token}`,
        },
        body: JSON.stringify({
          query: req.query,
          device_model: req.deviceModel || null,
          device_id: req.deviceId || null,
          history: req.history,
        }),
      })
    }
    if (!resp.ok) {
      let body = null
      try { body = await resp.json() } catch (e) {}
      const detail = body && body.detail
      // 故障图片双重校验被拦截：弹窗警告，不当作普通错误
      if (detail && typeof detail === 'object' && detail.reject) {
        assistant.loading = false
        assistant.streaming = false
        assistant.content = `⚠️ ${detail.message}（识别置信度 ${detail.confidence}）`
        ElMessageBox.alert(detail.message, '图片未通过校验', {
          type: 'warning', confirmButtonText: '重新拍摄',
        }).catch(() => {})
        return
      }
      throw new Error((detail && (detail.message || detail)) || '请求失败')
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const blocks = buf.split('\n\n')
      buf = blocks.pop()
      for (const block of blocks) handleEvent(block, assistant)
      await scrollBottom()
    }
    // 流正常结束：清理重连状态
    reconnect.status = ''
    reconnect.attempt = 0
  } catch (e) {
    // 网络异常 / 流中断：进入自动重连流程
    const isNetworkErr = e instanceof TypeError
      || /fetch|network|Failed to fetch/i.test(e.message)
    if (isNetworkErr && reconnect.attempt < 3) {
      reconnect.attempt += 1
      reconnect.status = 'reconnecting'
      await scrollBottom()
      // 间隔递增：1s / 2s / 4s
      const delay = 1000 * Math.pow(2, reconnect.attempt - 1)
      await new Promise((r) => setTimeout(r, delay))
      // 重连前重置助手消息状态，避免残留半截内容
      assistant.loading = true
      assistant.streaming = true
      assistant.content = ''
      assistant.citations = []
      assistant.vl = ''
      assistant.rewritten = ''
      assistant.graph = []
      assistant.confidence = null
      assistant.recommended_sops = []
      assistant.safety = null
      await runStream(assistant, req)
    } else if (isNetworkErr) {
      // 重连失败：提示用户手动重试
      reconnect.status = 'failed'
      assistant.loading = false
      assistant.streaming = false
      assistant.content = '⚠️ 网络异常，AI 回答中断。请点击上方"点击重试"按钮重新生成。'
      await scrollBottom()
    } else {
      reconnect.status = ''
      assistant.content = '抱歉：' + e.message
      ElMessage.error(e.message)
    }
  } finally {
    assistant.loading = false
    assistant.streaming = false
    sending.value = false
    await scrollBottom()
  }
}

// 用户点击重试按钮：重置重连计数，重新发起请求
async function retryLastSend() {
  if (!lastRequest) return
  reconnect.attempt = 0
  reconnect.status = 'reconnecting'
  // 取最后一条助手消息复用；若已被删除则新建
  let assistant = messages.value[messages.value.length - 1]
  if (!assistant || assistant.role !== 'assistant') {
    assistant = {
      role: 'assistant', content: '', citations: [], vl: '', rewritten: '', graph: [],
      confidence: null, recommended_sops: [], safety: null,
      loading: true, streaming: true, highlightCite: 0,
      qaId: null, appliedCorrections: [], vote: '',
      feedbackOpen: false, correctionText: '', feedbackSaved: false, saving: false,
    }
    messages.value.push(assistant)
  } else {
    assistant.loading = true
    assistant.streaming = true
    assistant.content = ''
    assistant.citations = []
    assistant.vl = ''
    assistant.rewritten = ''
    assistant.graph = []
    assistant.confidence = null
    assistant.recommended_sops = []
    assistant.safety = null
  }
  sending.value = true
  await scrollBottom()
  await runStream(assistant, lastRequest)
}

function handleEvent(block, assistant) {
  const lines = block.split('\n')
  let event = 'message'
  let data = ''
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return
  try {
    if (event === 'vl') {
      assistant.vl = JSON.parse(data)
    } else if (event === 'rewrite') {
      assistant.rewritten = JSON.parse(data)
    } else if (event === 'graph') {
      assistant.graph = JSON.parse(data)
    } else if (event === 'sops') {
      assistant.recommended_sops = JSON.parse(data)
    } else if (event === 'safety') {
      assistant.safety = JSON.parse(data)
    } else if (event === 'confidence') {
      assistant.confidence = JSON.parse(data)
    } else if (event === 'citations') {
      assistant.citations = JSON.parse(data)
    } else if (event === 'corrections') {
      assistant.appliedCorrections = JSON.parse(data)
    } else if (event === 'delta') {
      assistant.loading = false
      assistant.content += JSON.parse(data)
    } else if (event === 'error') {
      assistant.loading = false
      assistant.content += `\n\n⚠️ ${JSON.parse(data)}`
    } else if (event === 'done') {
      const d = JSON.parse(data)
      if (d && d.qa_id) assistant.qaId = d.qa_id
    }
  } catch (e) {}
}

// ---- M5 标注与修正 ----
async function vote(m, v) {
  const next = m.vote === v ? '' : v   // 再次点击同一项则取消
  try {
    await api.post('/feedback', { qa_id: m.qaId, vote: next })
    m.vote = next
    m.feedbackSaved = true
  } catch (e) {
    ElMessage.error('反馈提交失败')
  }
}

async function saveCorrection(m) {
  const text = (m.correctionText || '').trim()
  if (!text) {
    ElMessage.warning('请填写纠正内容')
    return
  }
  m.saving = true
  try {
    // 提交纠正默认同时记为“没用”，更契合纠正语义
    await api.post('/feedback', {
      qa_id: m.qaId, correction_text: text, vote: m.vote || 'down',
    })
    m.vote = m.vote || 'down'
    m.feedbackOpen = false
    m.feedbackSaved = true
    ElMessage.success('已提交纠正，将用于优化后续相似问题')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    m.saving = false
  }
}
</script>

<style scoped>
.chat-page { height: 100%; display: flex; flex-direction: column; }
.messages {
  flex: 1; overflow-y: auto; padding: 8px 4px; background: var(--bg-surface);
  border-radius: 10px; border: 1px solid var(--bd);
}
.empty {
  text-align: center; color: var(--muted); margin-top: 8vh; padding: 0 16px;
  display: flex; flex-direction: column; align-items: center;
}
.empty-illus {
  width: 96px; height: 96px; border-radius: 50%;
  background: var(--bubble-ai); display: flex; align-items: center; justify-content: center;
  margin-bottom: 18px; box-shadow: 0 6px 20px rgba(31, 111, 235, .14);
  animation: emptyBreath 2.6s ease-in-out infinite;
}
@keyframes emptyBreath {
  0%, 100% { transform: scale(1); box-shadow: 0 6px 20px rgba(31, 111, 235, .14); }
  50% { transform: scale(1.05); box-shadow: 0 8px 28px rgba(31, 111, 235, .22); }
}
.empty-title { font-size: 20px; font-weight: 700; color: var(--ink); margin: 0 0 6px; }
.empty-desc { font-size: 13.5px; color: var(--muted); margin: 0 0 22px; max-width: 520px; line-height: 1.7; }
.examples {
  display: flex; flex-direction: column; gap: 10px; width: 100%;
  max-width: 540px;
}
.example {
  cursor: pointer; display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border: 1px solid var(--bd); border-radius: 10px;
  background: var(--bg-surface); color: var(--ink-soft);
  transition: all .18s ease; font-size: 14px; text-align: left;
}
.example:hover {
  border-color: var(--brand); color: var(--brand);
  background: var(--bubble-user); transform: translateX(3px);
  box-shadow: 0 4px 12px rgba(31, 111, 235, .12);
}
.example .ex-icon { color: var(--brand); flex: none; }
.example span { flex: 1; }
.example .ex-arrow { color: var(--muted); flex: none; transition: transform .18s; }
.example:hover .ex-arrow { transform: translateX(3px); color: var(--brand); }

/* SSE 断线重连提示条 */
.reconnect-bar {
  display: flex; align-items: center; gap: 10px; justify-content: center;
  margin: 8px 16px; padding: 9px 14px; border-radius: 8px; font-size: 13px;
}
.reconnect-bar.reconnecting {
  background: #fdf6ec; color: #9a651f; border: 1px solid #faecd8;
}
html.dark .reconnect-bar.reconnecting {
  background: rgba(154, 101, 31, .14); color: #ffce82; border-color: rgba(255, 180, 84, .3);
}
.reconnect-bar.failed {
  background: #fef0f0; color: #b42318; border: 1px solid #fde2e2;
}
html.dark .reconnect-bar.failed {
  background: rgba(180, 35, 24, .14); color: #ff9b9b; border-color: rgba(255, 107, 107, .3);
}
.reconnect-bar .is-loading { animation: rotateSpin 1s linear infinite; }
@keyframes rotateSpin { from { transform: rotate(0); } to { transform: rotate(360deg); } }

/* AI 思考骨架屏 */
.think-skeleton {
  background: var(--bubble-ai); padding: 14px 16px; border-radius: 10px;
  margin-bottom: 6px;
}
.ts-line { height: 11px; margin-bottom: 9px; }
.ts-line:last-of-type { margin-bottom: 12px; }
.ts-hint {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--muted);
}
.dot-loader { display: inline-flex; gap: 3px; }
.dot-loader i {
  width: 5px; height: 5px; border-radius: 50%; background: var(--brand);
  animation: dotBounce 1.2s ease-in-out infinite;
}
.dot-loader i:nth-child(2) { animation-delay: .15s; }
.dot-loader i:nth-child(3) { animation-delay: .3s; }
@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(.6); opacity: .4; }
  40% { transform: scale(1); opacity: 1; }
}
.msg { display: flex; gap: 10px; padding: 14px 16px; }
.msg.user { flex-direction: row-reverse; }
.avatar {
  width: 34px; height: 34px; border-radius: 8px; flex: none;
  display: flex; align-items: center; justify-content: center; color: #fff;
}
.msg.user .avatar { background: var(--brand); }
.msg.assistant .avatar { background: #16a34a; }
.bubble { max-width: 78%; }
.msg-image {
  max-width: 220px; max-height: 180px; border-radius: 8px;
  margin-bottom: 8px; display: block; border: 1px solid var(--bd);
}
.content {
  background: var(--bubble-ai); padding: 10px 14px; border-radius: 10px;
  white-space: pre-wrap; line-height: 1.7; word-break: break-word;
  color: var(--ink-soft);
}
.msg.user .content { background: var(--bubble-user); }
.type-cursor {
  display: inline-block; width: 7px; height: 15px; margin-left: 2px;
  background: var(--brand); vertical-align: -2px; border-radius: 1px;
  animation: cursorBlink 1s steps(1) infinite;
}
@keyframes cursorBlink { 0%, 50% { opacity: 1; } 50.01%, 100% { opacity: 0; } }
.corr-badge { animation: corrBreath 2.2s ease-in-out infinite; }
@keyframes corrBreath {
  0%, 100% { box-shadow: 0 0 0 0 rgba(230, 162, 60, .5); }
  50% { box-shadow: 0 0 7px 2px rgba(230, 162, 60, .35); }
}

/* 打字机：流式光标 */
.content.typing { display: block; }
.type-cursor {
  display: inline-block; width: 7px; height: 16px; margin-left: 2px;
  background: var(--brand); border-radius: 1px; vertical-align: -3px;
  animation: blink 1s steps(2, start) infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* Markdown 渲染样式（完成后渐显，避免逐字 reflow 抖动）*/
.markdown-body {
  background: var(--bubble-ai); padding: 12px 16px; border-radius: 10px;
  line-height: 1.75; word-break: break-word; color: var(--ink);
  animation: mdFade .35s ease;
}
@keyframes mdFade { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
.markdown-body :deep(p) { margin: 6px 0; }
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) { margin: 12px 0 6px; font-weight: 700; line-height: 1.4; color: var(--ink); }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 22px; margin: 6px 0; }
.markdown-body :deep(li) { margin: 3px 0; }
.markdown-body :deep(strong) { color: var(--brand-deep); }
html.dark .markdown-body :deep(strong) { color: var(--brand); }
.markdown-body :deep(code) {
  background: var(--code-bg); color: var(--code-color); padding: 1px 6px;
  border-radius: 5px; font-size: 13px;
}
.markdown-body :deep(pre) {
  background: var(--pre-bg); color: var(--pre-color); padding: 12px 14px;
  border-radius: 8px; overflow-x: auto; margin: 8px 0;
}
.markdown-body :deep(pre code) { background: none; color: var(--pre-color); padding: 0; }
.markdown-body :deep(blockquote) {
  margin: 8px 0; padding: 6px 12px; color: var(--quote-text);
  background: var(--quote-bg); border-left: 4px solid var(--brand); border-radius: 0 6px 6px 0;
}
.markdown-body :deep(table) { border-collapse: collapse; margin: 8px 0; }
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid var(--bd); padding: 5px 10px; }
.markdown-body :deep(th) { background: var(--bg-surface-2); color: var(--ink); }

/* M5 修正横幅：呼吸灯 Badge */
.corr-badge { animation: breathe 2.4s ease-in-out infinite; }
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 0 0 rgba(230, 162, 60, .5); }
  50% { box-shadow: 0 0 0 5px rgba(230, 162, 60, 0); }
}
.confidence-box {
  margin-top: 8px; border-radius: 8px; padding: 9px 12px; border: 1px solid var(--bd);
  background: var(--bg-surface-2); font-size: 12px;
}
.conf-head { display: flex; align-items: center; gap: 5px; font-weight: 600; margin-bottom: 6px; }
.conf-high { border-color: #b7ebc6; background: #f0f9f2; color: #237a3b; }
.conf-medium { border-color: #faecd8; background: #fdf6ec; color: #9a651f; }
.conf-low { border-color: #fde2e2; background: #fef0f0; color: #b42318; }
html.dark .conf-high { border-color: rgba(35, 122, 59, .4); background: rgba(35, 122, 59, .14); }
html.dark .conf-medium { border-color: rgba(154, 101, 31, .4); background: rgba(154, 101, 31, .14); }
html.dark .conf-low { border-color: rgba(180, 35, 24, .4); background: rgba(180, 35, 24, .14); }
.conf-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 4px; }
.conf-warnings { display: flex; flex-direction: column; gap: 2px; color: #b42318; }
.rewrite-hint {
  display: flex; align-items: center; gap: 5px; margin-top: 8px;
  font-size: 12px; color: var(--muted); background: var(--bg-surface-2);
  border: 1px solid var(--bd); border-radius: 6px; padding: 5px 10px;
}
.graph-box {
  margin-top: 10px; background: rgba(124, 91, 191, .08); border: 1px solid rgba(124, 91, 191, .25);
  border-radius: 8px; padding: 10px 12px;
}
.graph-title { font-size: 12px; color: #7c5bbf; display: flex; align-items: center; margin-bottom: 8px; }
html.dark .graph-title { color: #b69ce6; }
.graph-rels { display: flex; flex-wrap: wrap; gap: 6px; }
.graph-rel {
  font-size: 12px; color: #5b4196; background: var(--bg-surface);
  border: 1px solid rgba(124, 91, 191, .25); border-radius: 12px; padding: 3px 10px;
}
html.dark .graph-rel { color: #c4aef5; }
.vl-box { margin-top: 8px; border-radius: 8px; }
.vl-content { color: var(--ink-soft); line-height: 1.7; white-space: pre-wrap; }
.citations {
  margin-top: 10px; background: var(--bg-surface-2); border: 1px solid var(--bd);
  border-radius: 8px; padding: 10px 12px;
}
.cite-title { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.cite {
  margin-bottom: 8px; font-size: 13px; padding: 8px 10px; border-radius: 8px;
  border: 1px solid transparent; transition: background .4s, border-color .4s;
}
.cite-hl { animation: citeFlash 1.6s ease-out; }
@keyframes citeFlash {
  0% { background: #fff7d6; border-color: #f6c945; }
  100% { background: transparent; border-color: transparent; }
}
.cite-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cite-src { color: var(--brand-deep); flex: 1; min-width: 120px; }
html.dark .cite-src { color: var(--brand); }
.cite-scores { display: flex; align-items: center; gap: 10px; }
.sc-comp {
  font-size: 12px; font-weight: 600; color: var(--ink);
  background: var(--bg-surface-2); border-radius: 5px; padding: 1px 7px;
}
.cite-scores .mini { display: flex; align-items: center; gap: 4px; }
.cite-scores .lbl { font-size: 11px; color: var(--muted); font-style: normal; }
.cite-scores .bar {
  width: 46px; height: 6px; border-radius: 3px; background: var(--bg-hover); overflow: hidden;
}
.cite-scores .bar b { display: block; height: 100%; border-radius: 3px; transition: width .5s ease; }
.cite-content { color: var(--ink-soft); margin-top: 5px; line-height: 1.6; }
.cite-ref {
  color: var(--brand); cursor: pointer; font-weight: 600;
  padding: 0 1px; border-radius: 3px; transition: background .15s;
}
.cite-ref:hover { background: var(--bubble-user); }

/* M5 反馈增强：采纳的人工修正 */
.applied-corr { margin-bottom: 8px; }
.ac-collapse { margin-top: 4px; border: none; }
.ac-collapse :deep(.el-collapse-item__header) {
  height: 28px; line-height: 28px; font-size: 12px; color: #b88230; border: none;
  background: transparent;
}
.ac-collapse :deep(.el-collapse-item__wrap) { border: none; background: transparent; }
.ac-item {
  background: rgba(184, 130, 48, .08); border: 1px solid rgba(184, 130, 48, .25); border-radius: 6px;
  padding: 8px 10px; margin-bottom: 6px;
}
.ac-q { font-size: 12px; color: var(--muted); margin-bottom: 3px; }
.ac-t { color: #b88230; line-height: 1.6; }

/* M5 反馈条 */
.feedback {
  display: flex; align-items: center; gap: 8px; margin-top: 10px;
  flex-wrap: wrap;
}
.fb-label { font-size: 12px; color: var(--muted); }
.fb-saved { font-size: 12px; color: #67c23a; display: inline-flex; align-items: center; gap: 3px; }
.correction-box {
  margin-top: 8px; background: var(--bg-surface-2); border: 1px solid var(--bd);
  border-radius: 8px; padding: 10px;
}
.cb-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.composer {
  margin-top: 12px; display: flex; gap: 10px; align-items: flex-start;
}
.composer-left { display: flex; flex-direction: column; gap: 8px; width: 160px; flex: none; }
.composer-main { flex: 1; }
.preview {
  position: relative; display: inline-block; margin-bottom: 6px;
}
.preview img {
  max-height: 64px; border-radius: 6px; border: 1px solid var(--bd); display: block;
}
.preview .remove {
  position: absolute; top: -8px; right: -8px; cursor: pointer;
  background: var(--bg-surface); border-radius: 50%; color: #f56c6c; font-size: 18px;
}
.composer .el-button { height: 60px; }
.img-upload :deep(.el-upload) { width: 100%; }
.img-upload :deep(.el-button) { width: 100%; height: 32px; }
.composer-left .voice-btn { width: 100%; height: 32px; margin-left: 0; }
.composer-left .voice-btn.rec { animation: voicePulse 1.1s ease-in-out infinite; }
@keyframes voicePulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 108, 108, .5); }
  50% { box-shadow: 0 0 0 6px rgba(245, 108, 108, 0); }
}
.wave { display: inline-flex; align-items: center; gap: 3px; height: 16px; }
.wave i {
  width: 3px; height: 100%; border-radius: 2px; background: #fff;
  animation: wave 0.9s ease-in-out infinite;
}
.wave i:nth-child(1) { animation-delay: 0s; }
.wave i:nth-child(2) { animation-delay: .15s; }
.wave i:nth-child(3) { animation-delay: .3s; }
.wave i:nth-child(4) { animation-delay: .45s; }
.wave i:nth-child(5) { animation-delay: .6s; }
@keyframes wave {
  0%, 100% { transform: scaleY(.35); }
  50% { transform: scaleY(1); }
}
</style>
