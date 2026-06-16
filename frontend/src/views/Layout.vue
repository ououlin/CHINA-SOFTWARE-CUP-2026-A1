<template>
  <el-container class="app-layout">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <el-icon :size="24" color="#fff"><Tools /></el-icon>
        <span>检修智能助手</span>
      </div>
      <el-menu :default-active="activePath" router class="menu"
               background-color="transparent" text-color="#cdd9f0"
               active-text-color="#fff">
        <el-menu-item index="/dashboard">
          <el-icon><DataBoard /></el-icon><span>数据看板</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon><span>智能检修问答</span>
        </el-menu-item>
        <el-menu-item index="/devices">
          <el-icon><Monitor /></el-icon><span>设备档案</span>
        </el-menu-item>
        <el-menu-item index="/alert">
          <el-icon><WarningFilled /></el-icon><span>故障预警</span>
        </el-menu-item>
        <el-menu-item index="/scan">
          <el-icon><Postcard /></el-icon><span>扫码报修</span>
        </el-menu-item>
        <el-menu-item index="/sop">
          <el-icon><Tickets /></el-icon><span>作业指引</span>
        </el-menu-item>
        <el-menu-item index="/cases">
          <el-icon><EditPen /></el-icon><span>知识沉淀</span>
        </el-menu-item>
        <el-menu-item index="/graph">
          <el-icon><Share /></el-icon><span>知识图谱</span>
        </el-menu-item>
        <el-menu-item index="/feedback">
          <el-icon><Star /></el-icon><span>标注修正</span>
        </el-menu-item>
        <el-menu-item index="/documents">
          <el-icon><Collection /></el-icon><span>知识库</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="head-left">
          <div class="head-bar"></div>
          <div class="head-meta">
            <div class="head-title">{{ currentTitle }}</div>
            <div v-if="currentDesc" class="head-desc">{{ currentDesc }}</div>
          </div>
        </div>
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
const currentDesc = computed(() => route.meta.desc || '')
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
.aside { background: linear-gradient(180deg, #0f3270 0%, #14418c 55%, #163d80 100%); }
.logo {
  height: 56px; display: flex; align-items: center; gap: 10px;
  color: #fff; font-size: 17px; font-weight: 600; padding-left: 20px;
  background: linear-gradient(120deg, #0b2a63, #14418c);
  border-bottom: 1px solid rgba(255, 255, 255, .08);
}
.menu { border-right: none; }
.menu :deep(.el-menu-item) { margin: 2px 10px; border-radius: 8px; }
.menu :deep(.el-menu-item:hover) { background: rgba(255, 255, 255, .08) !important; }
.menu :deep(.el-menu-item.is-active) {
  background: rgba(79, 155, 255, .22) !important;
  box-shadow: inset 3px 0 0 #4d9bff;
  font-weight: 600;
}
.header {
  background: #fff; display: flex; align-items: center;
  justify-content: space-between; border-bottom: 1px solid #ebeef5;
  box-shadow: 0 1px 6px rgba(0, 0, 0, .03); height: 60px;
}
.head-left { display: flex; align-items: center; gap: 12px; }
.head-bar {
  width: 4px; height: 32px; border-radius: 3px;
  background: linear-gradient(180deg, #1f6feb, #14418c);
}
.head-title { font-size: 17px; font-weight: 700; color: #1f2329; line-height: 1.2; }
.head-desc { font-size: 12.5px; color: #8a8f99; margin-top: 2px; }
.user { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.main { background: #f5f7fa; padding: 18px; }
</style>
