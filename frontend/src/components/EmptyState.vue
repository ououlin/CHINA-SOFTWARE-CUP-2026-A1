<template><div class="state-panel"><el-icon :size="28"><component :is="icon" /></el-icon><strong>{{ title }}</strong><p>{{ description }}</p><slot /></div></template>
<script setup>
import { Box } from '@element-plus/icons-vue'
defineProps({ title: { type: String, default: '暂无数据' }, description: { type: String, default: '当前筛选条件下没有可展示内容。' }, icon: { type: [Object, Function], default: Box } })
</script>
<style scoped>
.state-panel { min-height:160px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:7px; padding:24px; color:var(--muted); text-align:center; } .state-panel .el-icon { color:var(--brand); opacity:.75; } strong { color:var(--ink-soft); font-size:14px; } p { margin:0; font-size:12px; }
</style>

