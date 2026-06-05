<template>
  <el-container class="app-layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <el-icon :size="24" color="#fff"><Tools /></el-icon>
        <span>检修智能助手</span>
      </div>
      <el-menu :default-active="activePath" router class="menu"
               background-color="#14418c" text-color="#cdd9f0"
               active-text-color="#fff">
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon><span>智能检修问答</span>
        </el-menu-item>
        <el-menu-item index="/sop">
          <el-icon><Tickets /></el-icon><span>作业指引</span>
        </el-menu-item>
        <el-menu-item index="/documents">
          <el-icon><Collection /></el-icon><span>知识库</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="title">{{ currentTitle }}</div>
        <el-dropdown @command="onCommand">
          <span class="user">
            <el-icon><UserFilled /></el-icon>
            {{ auth.user?.display_name }}
            <el-tag size="small" type="info" effect="plain">{{ roleLabel }}</el-tag>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../store'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activePath = computed(() => route.path)
const currentTitle = computed(() => route.meta.title || '')
const roleLabel = computed(() => ({
  worker: '一线人员', auditor: '审核员', admin: '管理员',
}[auth.user?.role] || ''))

function onCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout { height: 100%; }
.aside { background: #14418c; }
.logo {
  height: 56px; display: flex; align-items: center; gap: 10px;
  color: #fff; font-size: 17px; font-weight: 600; padding-left: 20px;
  background: #0f3270;
}
.menu { border-right: none; }
.header {
  background: #fff; display: flex; align-items: center;
  justify-content: space-between; border-bottom: 1px solid #ebeef5;
}
.title { font-size: 16px; font-weight: 600; }
.user { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.main { background: #f5f7fa; padding: 18px; }
</style>
