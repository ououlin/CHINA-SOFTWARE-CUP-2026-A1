<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand">
        <el-icon :size="34" color="#1f6feb"><Tools /></el-icon>
        <h1>设备检修知识检索与作业系统</h1>
        <p class="text-muted">基于多模态大模型技术 · 智能检修助手</p>
      </div>
      <el-form @submit.prevent="onLogin">
        <el-form-item>
          <el-input v-model="username" size="large" placeholder="用户名"
                    :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" size="large" type="password" show-password
                    placeholder="密码" :prefix-icon="Lock"
                    @keyup.enter="onLogin" />
        </el-form-item>
        <el-button type="primary" size="large" style="width:100%"
                   :loading="loading" @click="onLogin">登 录</el-button>
      </el-form>
      <div class="hint text-muted">
        演示账号：worker / worker123 ，auditor / auditor123 ，admin / admin123
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Tools } from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

const username = ref('worker')
const password = ref('worker123')
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function onLogin() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const form = new URLSearchParams()
    form.append('username', username.value)
    form.append('password', password.value)
    const { data } = await api.post('/auth/login', form)
    auth.setAuth(data)
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f6feb 0%, #14418c 100%);
}
.login-card {
  width: 380px;
  background: #fff;
  border-radius: 14px;
  padding: 40px 36px 28px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.25);
}
.brand { text-align: center; margin-bottom: 26px; }
.brand h1 { font-size: 19px; margin: 12px 0 6px; }
.brand p { margin: 0; font-size: 13px; }
.hint { margin-top: 16px; font-size: 12px; text-align: center; }
</style>
