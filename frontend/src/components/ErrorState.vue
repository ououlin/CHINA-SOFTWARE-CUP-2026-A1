<template><div class="state-panel is-error"><el-icon :size="28"><WarningFilled /></el-icon><strong>{{ title }}</strong><p>{{ description }}</p><el-button v-if="retry" size="small" type="primary" plain @click="$emit('retry')">重新加载</el-button></div></template>
<script setup>
import { WarningFilled } from '@element-plus/icons-vue'
defineProps({ title: { type: String, default: '数据加载失败' }, description: { type: String, default: '网络或服务暂时不可用，请稍后重试。' }, retry: { type: Boolean, default: true } })
defineEmits(['retry'])
</script>
<style scoped>
.state-panel { min-height:160px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:7px; padding:24px; color:var(--muted); text-align:center; } .is-error .el-icon { color:#d97706; } strong { color:var(--ink-soft); font-size:14px; } p { margin:0 0 5px; font-size:12px; }
</style>

