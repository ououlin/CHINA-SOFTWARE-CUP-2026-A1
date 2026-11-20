<template>
  <el-container class="app-layout">
    <el-aside width="244px" class="aside desktop-aside"><SidebarNav :sections="visibleSections" :active-path="activePath" /></el-aside>
    <el-drawer v-model="drawerOpen" direction="ltr" :with-header="false" size="278px" modal-class="mobile-menu-drawer" @close="drawerOpen = false">
      <SidebarNav :sections="visibleSections" :active-path="activePath" @select="onMenuSelect" />
    </el-drawer>
    <el-container class="content-shell">
      <el-header class="header">
        <div class="head-left">
          <el-button class="menu-toggle" :icon="Fold" text aria-label="打开导航" @click="drawerOpen = true" />
          <div class="head-bar"></div>
          <div class="head-meta"><div class="head-crumb">设备检修工作台 <span>/</span> {{ currentTitle }}</div><div v-if="currentDesc" class="head-desc">{{ currentDesc }}</div></div>
        </div>
        <div class="head-right">
          <div class="connection-state"><i></i><span>服务在线</span></div>
          <el-button class="theme-toggle" text :title="isDark ? '切换为亮色' : '切换为暗色'" @click="toggleTheme"><el-icon :size="18"><Sunny v-if="isDark" /><Moon v-else /></el-icon></el-button>
          <el-dropdown @command="onCommand"><button class="user" type="button"><span class="avatar"><el-icon><UserFilled /></el-icon></span><span class="user-copy"><b>{{ auth.user?.display_name || '用户' }}</b><small>{{ roleLabel }}</small></span><el-icon class="user-arrow"><ArrowDown /></el-icon></button><template #dropdown><el-dropdown-menu><el-dropdown-item command="logout">退出登录</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
        </div>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, Fold, Moon, Sunny, UserFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '../store'
import { navigationSections } from '../config/navigation'
import SidebarNav from '../components/SidebarNav.vue'

const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const drawerOpen = ref(false)
const isDark = ref(document.documentElement.classList.contains('dark'))
const activePath = computed(() => route.path); const currentTitle = computed(() => route.meta.title || ''); const currentDesc = computed(() => route.meta.desc || '')
const roleLabel = computed(() => ({ worker: '一线作业员', auditor: '审核员', admin: '管理员' }[auth.user?.role] || ''))
const canManage = computed(() => ['auditor', 'admin'].includes(auth.user?.role))
const visibleSections = computed(() => navigationSections.map((section) => ({ ...section, items: section.items.filter((item) => !item.manageOnly || canManage.value) })).filter((section) => section.items.length))
function applyTheme(dark) { document.documentElement.classList.toggle('dark', dark); localStorage.setItem('theme', dark ? 'dark' : 'light') }
function toggleTheme() { isDark.value = !isDark.value; applyTheme(isDark.value) }
function onMenuSelect() { drawerOpen.value = false }
function onCommand(command) { if (command === 'logout') { auth.logout(); router.push('/login') } }
function onResize() { if (window.innerWidth > 768) drawerOpen.value = false }
onMounted(() => window.addEventListener('resize', onResize)); onBeforeUnmount(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.app-layout{min-height:100%;height:100dvh}.content-shell{min-width:0;min-height:0}.aside{background:var(--aside-grad);height:100%;position:relative;overflow:hidden}.aside:after{content:'';position:absolute;inset:0;pointer-events:none;opacity:.16;background-image:linear-gradient(rgba(137,198,184,.18) 1px,transparent 1px),linear-gradient(90deg,rgba(137,198,184,.18) 1px,transparent 1px);background-size:28px 28px;mask-image:linear-gradient(to bottom,#000,transparent 80%)}
.header{height:72px;padding:0 26px;display:flex;align-items:center;justify-content:space-between;background:var(--bg-surface);border-bottom:1px solid var(--bd)}.head-left,.head-right{display:flex;align-items:center;gap:14px;min-width:0}.head-bar{width:4px;height:28px;background:var(--brand);border-radius:2px}.head-meta{min-width:0}.head-crumb{color:var(--ink);font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.head-crumb span{margin:0 7px;color:var(--bd-strong);font-weight:400}.head-desc{margin-top:3px;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.connection-state{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:11px}.connection-state i{width:7px;height:7px;border-radius:50%;background:#3dbd8b;box-shadow:0 0 0 3px rgba(61,189,139,.14)}.theme-toggle{color:var(--ink)}.user{display:flex;align-items:center;gap:8px;border:0;background:none;color:var(--ink);cursor:pointer;padding:3px 0 3px 5px}.avatar{width:31px;height:31px;display:grid;place-items:center;color:#fff;background:var(--brand-grad);border-radius:50%}.user-copy{display:flex;flex-direction:column;align-items:flex-start;line-height:1.1}.user-copy b{font-size:12px;font-weight:600}.user-copy small{margin-top:3px;color:var(--muted);font-size:10px}.user-arrow{color:var(--muted);font-size:12px}.menu-toggle{display:none;color:var(--ink)}.main{min-width:0;min-height:0;overflow:auto;padding:24px;background:var(--bg-page)}
@media(max-width:768px){.desktop-aside{display:none!important}.menu-toggle{display:inline-flex}.header{height:60px;padding:0 12px}.head-bar{height:24px}.head-crumb{font-size:14px}.head-desc,.connection-state,.user-copy,.user-arrow{display:none}.main{padding:12px!important}}
</style>
<style>.mobile-menu-drawer .el-drawer__body{padding:0;background:var(--aside-grad)}</style>
