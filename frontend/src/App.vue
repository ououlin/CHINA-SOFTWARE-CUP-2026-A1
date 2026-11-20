<template>
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { onMounted } from 'vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

// 启动时从 localStorage 读取主题偏好，提前应用 .dark 类避免闪烁
onMounted(() => {
  const saved = localStorage.getItem('theme') || 'light'
  if (saved === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
})
</script>
