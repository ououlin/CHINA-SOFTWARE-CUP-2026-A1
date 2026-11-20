<template>
  <header class="page-header">
    <div v-if="icon" class="page-header__icon" :class="`is-${tone}`">
      <el-icon :size="20"><component :is="icon" /></el-icon>
    </div>
    <div class="page-header__copy">
      <div class="page-header__eyebrow">{{ eyebrow }}</div>
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions"><slot name="actions" /></div>
  </header>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  eyebrow: { type: String, default: '设备检修工作台' },
  icon: { type: [Object, Function], default: null },
  tone: { type: String, default: 'brand' },
})
</script>

<style scoped>
.page-header { display:flex; align-items:center; gap:14px; padding:16px 18px; margin-bottom:14px; background:var(--bg-surface); border:1px solid var(--bd); border-radius:var(--radius); box-shadow:var(--shadow-sm); }
.page-header__icon { width:42px; height:42px; flex:none; display:grid; place-items:center; color:#fff; background:var(--brand-grad); border-radius:8px; }
.page-header__icon.is-warning { background:linear-gradient(135deg,#d97706,#b45309); }
.page-header__icon.is-accent { background:linear-gradient(135deg,#0f8f83,#0b6f67); }
.page-header__copy { min-width:0; flex:1; }
.page-header__eyebrow { font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin-bottom:3px; }
h1 { margin:0; color:var(--ink); font-size:19px; line-height:1.25; }
p { margin:4px 0 0; color:var(--muted); font-size:13px; }
.page-header__actions { display:flex; align-items:center; gap:8px; flex:none; }
@media (max-width:640px) { .page-header { padding:13px 14px; gap:10px; } .page-header__icon { width:36px; height:36px; } h1 { font-size:17px; } p { font-size:12px; } .page-header__actions :deep(.el-button span) { display:none; } }
</style>

