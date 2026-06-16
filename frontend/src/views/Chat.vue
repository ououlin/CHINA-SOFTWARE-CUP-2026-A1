<template>
  <div class="chat-page">
    <div class="messages" ref="msgBox">
      <div v-if="messages.length === 0" class="empty">
        <el-icon :size="46" color="#c0c4cc"><ChatDotRound /></el-icon>
        <p>输入设备故障现象、上传故障图片，或指定设备型号，例如：</p>
        <div class="examples">
          <el-tag v-for="q in examples" :key="q" class="example"
                  @click="useExample(q)">{{ q }}</el-tag>
        </div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <div class="avatar">
          <el-icon v-if="m.role === 'user'"><UserFilled /></el-icon>
          <el-icon v-else><Service /></el-icon>
        </div>
        <div class="bubble">
          <img v-if="m.image" :src="m.image" class="msg-image" />

          <div v-if="m.appliedCorrections && m.appliedCorrections.length"
               class="applied-corr">
            <el-tag type="warning" size="small" effect="dark">
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

          <div class="content" v-text="m.content || (m.loading ? '正在思考…' : '')"></div>

          <el-collapse v-if="m.vl" class="vl-box">
            <el-collapse-item>
              <template #title>
                <el-icon><View /></el-icon>&nbsp;图片识别结果（Qwen-VL）
              </template>
              <div class="vl-content">{{ m.vl }}</div>
            </el-collapse-item>
          </el-collapse>

          <div v-if="m.citations && m.citations.length" class="citations">
            <div class="cite-title">参考来源</div>
            <div v-for="(c, idx) in m.citations" :key="idx" class="cite">
              <el-tag size="small" type="primary" effect="plain">[{{ idx + 1 }}]</el-tag>
              <span class="cite-src">{{ c.doc_title }}{{ c.page ? ` · 第${c.page}页` : '' }}</span>
              <el-tag size="small" type="info" effect="plain">
                相似度 {{ c.score }}
              </el-tag>
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
        <el-input v-model="deviceModel" class="device" placeholder="设备型号(可选)"
                  clearable>
          <template #prefix><el-icon><Cpu /></el-icon></template>
        </el-input>
        <el-upload :auto-upload="false" :show-file-list="false" accept="image/*"
                   :on-change="onPickImage" class="img-upload">
          <el-button :icon="Picture">故障图片</el-button>
        </el-upload>
        <el-button class="voice-btn" :class="{ rec: listening }" :icon="Microphone"
                   :type="listening ? 'danger' : ''" @click="toggleVoice">
          {{ listening ? '聆听中…' : '语音输入' }}
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
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Picture, CircleClose, View, EditPen, MagicStick, CircleCheck, Microphone,
} from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

const auth = useAuthStore()
const messages = ref([])
const input = ref('')
const deviceModel = ref('')
const sending = ref(false)
const msgBox = ref(null)

const pickedFile = ref(null)
const pickedPreview = ref('')

const examples = [
  '发动机怠速不稳怎么排查？',
  '火花塞电极发黑说明什么问题？',
  '气门间隙标准是多少，过大有什么影响？',
  '发动机过热如何处理？',
]

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
    role: 'assistant', content: '', citations: [], vl: '', loading: true,
    qaId: null, appliedCorrections: [], vote: '',
    feedbackOpen: false, correctionText: '', feedbackSaved: false, saving: false,
  }
  messages.value.push(assistant)
  sending.value = true
  const hasImage = !!pickedFile.value
  input.value = ''
  await scrollBottom()

  try {
    let resp
    if (hasImage) {
      const fd = new FormData()
      fd.append('image', pickedFile.value)
      if (query) fd.append('query', query)
      if (deviceModel.value) fd.append('device_model', deviceModel.value)
      resp = await fetch('/api/chat/ask_image', {
        method: 'POST',
        headers: { Authorization: `Bearer ${auth.token}` },
        body: fd,
      })
      clearImage()
    } else {
      resp = await fetch('/api/chat/ask_stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${auth.token}`,
        },
        body: JSON.stringify({ query, device_model: deviceModel.value || null, history }),
      })
    }
    if (!resp.ok) {
      let detail = '请求失败'
      try { detail = (await resp.json()).detail || detail } catch (e) {}
      throw new Error(detail)
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
  } catch (e) {
    assistant.content = '抱歉：' + e.message
    ElMessage.error(e.message)
  } finally {
    assistant.loading = false
    sending.value = false
    await scrollBottom()
  }
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
    } else if (event === 'citations') {
      assistant.citations = JSON.parse(data)
    } else if (event === 'corrections') {
      assistant.appliedCorrections = JSON.parse(data)
    } else if (event === 'delta') {
      assistant.loading = false
      assistant.content += JSON.parse(data)
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
  flex: 1; overflow-y: auto; padding: 8px 4px; background: #fff;
  border-radius: 10px; border: 1px solid #ebeef5;
}
.empty { text-align: center; color: #8a8f99; margin-top: 60px; }
.examples { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 12px; }
.example { cursor: pointer; }
.msg { display: flex; gap: 10px; padding: 14px 16px; }
.msg.user { flex-direction: row-reverse; }
.avatar {
  width: 34px; height: 34px; border-radius: 8px; flex: none;
  display: flex; align-items: center; justify-content: center; color: #fff;
}
.msg.user .avatar { background: #1f6feb; }
.msg.assistant .avatar { background: #16a34a; }
.bubble { max-width: 78%; }
.msg-image {
  max-width: 220px; max-height: 180px; border-radius: 8px;
  margin-bottom: 8px; display: block; border: 1px solid #e4e7ed;
}
.content {
  background: #f2f6fc; padding: 10px 14px; border-radius: 10px;
  white-space: pre-wrap; line-height: 1.7; word-break: break-word;
}
.msg.user .content { background: #e3f0ff; }
.vl-box { margin-top: 8px; border-radius: 8px; }
.vl-content { color: #606266; line-height: 1.7; white-space: pre-wrap; }
.citations {
  margin-top: 10px; background: #fafafa; border: 1px solid #eee;
  border-radius: 8px; padding: 10px 12px;
}
.cite-title { font-size: 12px; color: #8a8f99; margin-bottom: 8px; }
.cite { margin-bottom: 10px; font-size: 13px; }
.cite-src { margin: 0 6px; color: #14418c; }
.cite-content { color: #606266; margin-top: 4px; line-height: 1.6; }

/* M5 反馈增强：采纳的人工修正 */
.applied-corr { margin-bottom: 8px; }
.ac-collapse { margin-top: 4px; border: none; }
.ac-collapse :deep(.el-collapse-item__header) {
  height: 28px; line-height: 28px; font-size: 12px; color: #b88230; border: none;
}
.ac-collapse :deep(.el-collapse-item__wrap) { border: none; }
.ac-item {
  background: #fdf6ec; border: 1px solid #faecd8; border-radius: 6px;
  padding: 8px 10px; margin-bottom: 6px;
}
.ac-q { font-size: 12px; color: #909399; margin-bottom: 3px; }
.ac-t { color: #b88230; line-height: 1.6; }

/* M5 反馈条 */
.feedback {
  display: flex; align-items: center; gap: 8px; margin-top: 10px;
  flex-wrap: wrap;
}
.fb-label { font-size: 12px; color: #909399; }
.fb-saved { font-size: 12px; color: #67c23a; display: inline-flex; align-items: center; gap: 3px; }
.correction-box {
  margin-top: 8px; background: #fafafa; border: 1px solid #eee;
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
  max-height: 64px; border-radius: 6px; border: 1px solid #e4e7ed; display: block;
}
.preview .remove {
  position: absolute; top: -8px; right: -8px; cursor: pointer;
  background: #fff; border-radius: 50%; color: #f56c6c; font-size: 18px;
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
</style>
