<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span>知识库文档</span>
          <el-button v-if="canUpload" type="primary" :icon="Upload" size="small"
                     @click="dialog = true">导入 PDF 手册</el-button>
        </div>
      </template>
      <el-table :data="docs" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" min-width="220" />
        <el-table-column prop="device_type" label="设备类型" width="150" />
        <el-table-column prop="device_model" label="设备型号" width="150" />
        <el-table-column prop="source_type" label="来源" width="100">
          <template #default="{ row }">
            {{ row.source_type === 'manual' ? '手册' : '案例' }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'approved' ? 'success' : 'warning'"
                    size="small">
              {{ row.status === 'approved' ? '已入库' : '待审核' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" title="导入 PDF 检修手册" width="460px">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="留空则用文件名" />
        </el-form-item>
        <el-form-item label="设备类型">
          <el-input v-model="form.device_type" placeholder="如：摩托车发动机" />
        </el-form-item>
        <el-form-item label="设备型号">
          <el-input v-model="form.device_model" placeholder="如：通用四冲程" />
        </el-form-item>
        <el-form-item label="PDF 文件">
          <el-upload :auto-upload="false" :show-file-list="true" accept=".pdf"
                     :limit="1" :on-change="onPick" :on-remove="() => (file = null)">
            <el-button :icon="Document">选择 PDF</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submit">
          导入并向量化
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Document } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

const auth = useAuthStore()
const docs = ref([])
const loading = ref(false)
const dialog = ref(false)
const uploading = ref(false)
const file = ref(null)
const form = ref({ title: '', device_type: '', device_model: '' })

const canUpload = computed(() => ['auditor', 'admin'].includes(auth.user?.role))

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/documents')
    docs.value = data
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function onPick(f) {
  file.value = f.raw
}

async function submit() {
  if (!file.value) {
    ElMessage.warning('请选择 PDF 文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file.value)
    if (form.value.title) fd.append('title', form.value.title)
    fd.append('device_type', form.value.device_type)
    fd.append('device_model', form.value.device_model)
    await api.post('/documents/upload', fd)
    ElMessage.success('导入成功，已切块并向量化')
    dialog.value = false
    file.value = null
    form.value = { title: '', device_type: '', device_model: '' }
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    uploading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.card-head { display: flex; align-items: center; justify-content: space-between; }
</style>
