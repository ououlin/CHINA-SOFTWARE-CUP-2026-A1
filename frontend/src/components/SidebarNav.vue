<template>
  <div class="nav-panel">
    <div class="logo"><span class="logo-mark"><el-icon :size="20"><Tools /></el-icon></span><div><strong>检修智能助手</strong><small>FIELD OPS / A1</small></div></div>
    <nav v-for="section in sections" :key="section.label" class="nav-section">
      <div class="nav-section__label">{{ section.label }}</div>
      <el-menu :default-active="activePath" router class="menu" background-color="transparent" text-color="var(--aside-text)" active-text-color="#fff" @select="$emit('select')">
        <el-menu-item v-for="item in section.items" :key="item.path" :index="item.path" :class="'tone-' + (item.tone || 'default')">
          <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </nav>
    <div class="nav-footer"><span class="footer-dot"></span><div><b>赛事专项环境</b><small>数据仅用于试点验证</small></div></div>
  </div>
</template>
<script setup>
import { Tools } from '@element-plus/icons-vue'
defineProps({ sections: { type: Array, default: () => [] }, activePath: { type: String, default: '' } })
defineEmits(['select'])
</script>
<style scoped>
.nav-panel{height:100%;display:flex;flex-direction:column;position:relative;z-index:1}.logo{height:72px;padding:0 20px;display:flex;align-items:center;gap:10px;color:#fff;border-bottom:1px solid var(--aside-border);background:var(--aside-logo-grad)}.logo-mark{width:34px;height:34px;display:grid;place-items:center;color:#a6eee3;background:rgba(57,209,190,.14);border:1px solid rgba(166,238,227,.24);border-radius:8px}.logo strong{display:block;font-size:15px}.logo small{display:block;margin-top:3px;color:#83a59d;font-size:9px;letter-spacing:.14em}.nav-section{padding:16px 10px 0}.nav-section__label{padding:0 10px 7px;color:#71948c;font-size:10px;letter-spacing:.12em;text-transform:uppercase}.menu{border-right:none}.menu :deep(.el-menu-item){height:40px;line-height:40px;margin:3px 0;border-radius:6px;color:var(--aside-text)}.menu :deep(.el-menu-item:hover){background:var(--aside-hover-bg)!important}.menu :deep(.el-menu-item.is-active){background:var(--aside-active-bg)!important;box-shadow:inset 3px 0 0 var(--aside-active-bar);font-weight:600}.menu :deep(.tone-warning .el-icon){color:#f0a54a}.menu :deep(.tone-accent .el-icon){color:#75ddd0}.nav-footer{margin:auto 16px 18px;padding:11px 12px;display:flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.1);border-radius:6px;color:#b7cec8;background:rgba(255,255,255,.04)}.nav-footer b,.nav-footer small{display:block}.nav-footer b{font-size:11px}.nav-footer small{margin-top:3px;color:#70928a;font-size:10px}.footer-dot{width:7px;height:7px;flex:none;border-radius:50%;background:#58d2a3;box-shadow:0 0 0 4px rgba(88,210,163,.12)}
</style>
