<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'

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
