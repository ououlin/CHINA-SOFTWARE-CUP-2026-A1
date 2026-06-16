<template>
  <div class="login-page">
    <!-- 左：品牌展示区 -->
    <div class="brand-side">
      <div class="grid-bg"></div>
      <div class="glow glow-1"></div>
      <div class="glow glow-2"></div>

      <!-- 装饰：设备知识网络 -->
      <svg class="deco-net" viewBox="0 0 400 400" fill="none" xmlns="http://www.w3.org/2000/svg">
        <g stroke="rgba(120,180,255,.35)" stroke-width="1">
          <line x1="80" y1="90" x2="200" y2="150" />
          <line x1="200" y1="150" x2="320" y2="100" />
          <line x1="200" y1="150" x2="160" y2="280" />
          <line x1="200" y1="150" x2="300" y2="250" />
          <line x1="160" y1="280" x2="300" y2="250" />
          <line x1="80" y1="90" x2="160" y2="280" />
        </g>
        <g fill="rgba(150,200,255,.9)">
          <circle cx="80" cy="90" r="5" />
          <circle cx="320" cy="100" r="4" />
          <circle cx="160" cy="280" r="5" />
          <circle cx="300" cy="250" r="4" />
        </g>
        <circle cx="200" cy="150" r="9" fill="#7fb4ff" />
        <circle cx="200" cy="150" r="16" fill="none" stroke="#7fb4ff" stroke-width="1.5" opacity=".5" />
      </svg>

      <div class="brand-content">
        <div class="logo">
          <el-icon :size="30"><Tools /></el-icon>
          <span>检修智能助手</span>
        </div>
        <h1 class="headline">基于多模态大模型技术的<br />设备检修知识检索与作业系统</h1>
        <p class="subhead">融合多模态检索 · 标准化作业 · 知识沉淀 · 智能修正<br />让分散的检修经验沉淀为可检索、可执行、可演进的知识体系</p>

        <ul class="feature-list">
          <li><el-icon><Search /></el-icon><span>多模态知识检索</span></li>
          <li><el-icon><Tickets /></el-icon><span>标准化作业指引</span></li>
          <li><el-icon><Share /></el-icon><span>知识沉淀与图谱</span></li>
          <li><el-icon><Monitor /></el-icon><span>设备健康档案</span></li>
        </ul>

        <div class="brand-footer">第十五届中国软件杯 · A 组赛题 · 龙芯中科出题</div>
      </div>
    </div>

    <!-- 右：登录区 -->
    <div class="form-side">
      <div class="login-box">
        <div class="welcome">
          <h2>欢迎登录</h2>
          <p class="text-muted">请使用账号登录智能检修工作台</p>
        </div>

        <el-form @submit.prevent="onLogin" class="login-form">
          <el-form-item>
            <el-input v-model="username" size="large" placeholder="用户名" :prefix-icon="User" />
          </el-form-item>
          <el-form-item>
            <el-input v-model="password" size="large" type="password" show-password
                      placeholder="密码" :prefix-icon="Lock" @keyup.enter="onLogin" />
          </el-form-item>
          <el-button type="primary" size="large" class="submit-btn"
                     :loading="loading" @click="onLogin">登 录</el-button>
        </el-form>

        <el-divider class="quick-divider"><span class="qd-text">演示账号 · 一键登录</span></el-divider>
        <div class="role-cards">
          <div v-for="r in roles" :key="r.user" class="role-card" :style="{ '--rc': r.color }"
               @click="quickLogin(r)">
            <el-icon :size="20"><component :is="r.icon" /></el-icon>
            <div class="rc-name">{{ r.label }}</div>
            <div class="rc-user">{{ r.user }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  User, Lock, Tools, Search, Tickets, Share, Monitor, Avatar, Checked, UserFilled,
} from '@element-plus/icons-vue'
import api from '../api'
import { useAuthStore } from '../store'

const username = ref('worker')
const password = ref('worker123')
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

const roles = [
  { label: '一线人员', user: 'worker', pass: 'worker123', icon: Avatar, color: '#1f6feb' },
  { label: '审核员', user: 'auditor', pass: 'auditor123', icon: Checked, color: '#67c23a' },
  { label: '管理员', user: 'admin', pass: 'admin123', icon: UserFilled, color: '#e6a23c' },
]

async function doLogin() {
  loading.value = true
  try {
    const form = new URLSearchParams()
    form.append('username', username.value)
    form.append('password', password.value)
    const { data } = await api.post('/auth/login', form)
    auth.setAuth(data)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function onLogin() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  await doLogin()
}

function quickLogin(r) {
  username.value = r.user
  password.value = r.pass
  doLogin()
}
</script>

<style scoped>
.login-page { height: 100%; display: flex; }

/* ---- 左：品牌区 ---- */
.brand-side {
  position: relative; flex: 1.15; overflow: hidden;
  background: linear-gradient(135deg, #0a2a6b 0%, #14418c 55%, #1f6feb 120%);
  color: #fff; display: flex; align-items: center;
}
.grid-bg {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, .05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, .05) 1px, transparent 1px);
  background-size: 38px 38px;
  mask-image: radial-gradient(ellipse 80% 80% at 40% 40%, #000 40%, transparent 100%);
}
.glow { position: absolute; border-radius: 50%; filter: blur(70px); opacity: .55; }
.glow-1 { width: 320px; height: 320px; background: #2f7bff; top: -80px; right: -60px; }
.glow-2 { width: 280px; height: 280px; background: #0c1f55; bottom: -90px; left: -40px; opacity: .7; }
.deco-net { position: absolute; right: 40px; top: 60px; width: 300px; height: 300px; opacity: .85; }
.brand-content { position: relative; z-index: 2; padding: 0 64px; max-width: 560px; }
.logo {
  display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 700;
  letter-spacing: .5px; margin-bottom: 34px;
}
.headline { font-size: 30px; line-height: 1.45; font-weight: 700; margin: 0 0 18px; }
.subhead { font-size: 14px; line-height: 1.8; color: rgba(255, 255, 255, .78); margin: 0 0 34px; }
.feature-list { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }
.feature-list li {
  display: flex; align-items: center; gap: 10px; font-size: 14px;
  background: rgba(255, 255, 255, .08); border: 1px solid rgba(255, 255, 255, .12);
  border-radius: 10px; padding: 11px 14px; backdrop-filter: blur(4px);
}
.feature-list li .el-icon { color: #8fc0ff; }
.brand-footer { margin-top: 42px; font-size: 13px; color: rgba(255, 255, 255, .6); letter-spacing: .5px; }

/* ---- 右：表单区 ---- */
.form-side {
  flex: .85; display: flex; align-items: center; justify-content: center;
  background: #fff; padding: 40px;
}
.login-box { width: 340px; }
.welcome { margin-bottom: 28px; }
.welcome h2 { font-size: 26px; font-weight: 700; margin: 0 0 6px; color: #1f2329; }
.welcome p { margin: 0; font-size: 14px; }
.login-form :deep(.el-input__wrapper) { padding: 4px 14px; border-radius: 10px; }
.submit-btn {
  width: 100%; height: 46px; font-size: 16px; letter-spacing: 4px; border-radius: 10px;
  background: linear-gradient(135deg, #1f6feb, #14418c); border: none;
}
.submit-btn:hover { opacity: .92; }
.quick-divider { margin: 26px 0 18px; }
.qd-text { font-size: 12px; color: #a0a4ab; }
.role-cards { display: flex; gap: 12px; }
.role-card {
  flex: 1; cursor: pointer; text-align: center; padding: 14px 6px;
  border: 1px solid #ebeef5; border-radius: 12px; transition: all .18s;
  color: var(--rc);
}
.role-card:hover {
  border-color: var(--rc); transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, .08);
}
.rc-name { font-size: 13px; font-weight: 600; color: #303133; margin-top: 6px; }
.rc-user { font-size: 11px; color: #a0a4ab; margin-top: 2px; }

@media (max-width: 860px) {
  .brand-side { display: none; }
  .form-side { flex: 1; }
}
</style>
