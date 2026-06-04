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
              <span class="cite-src">{{ c.doc_title }} · 第{{ c.page }}页</span>
              <el-tag size="small" type="info" effect="plain">
                相似度 {{ c.score }}
              </el-tag>
              <div class="cite-content">{{ c.content }}</div>
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
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Picture, CircleClose, View,
} from '@element-plus/icons-vue'
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

async function scrollBottom() {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}

async function send() {
  const query = input.value.trim()
  if ((!query && !pickedFile.value) || sending.value) return

  const userMsg = { role: 'user', content: query }
  if (pickedFile.value) userMsg.image = pickedPreview.value
  messages.value.push(userMsg)

  const assistant = { role: 'assistant', content: '', citations: [], vl: '', loading: true }
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
        body: JSON.stringify({ query, device_model: deviceModel.value || null }),
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
    } else if (event === 'delta') {
      assistant.loading = false
      assistant.content += JSON.parse(data)
    }
  } catch (e) {}
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
</style>
