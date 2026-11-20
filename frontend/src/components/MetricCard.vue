<template>
  <article class="metric-card" :class="[`tone-${tone}`, { 'is-alert': alert }]">
    <div class="metric-card__top"><span>{{ label }}</span><el-icon><component :is="icon" /></el-icon></div>
    <div class="metric-card__value">{{ value }}<small v-if="unit">{{ unit }}</small></div>
    <div v-if="hint" class="metric-card__hint">{{ hint }}</div>
  </article>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '--' },
  unit: { type: String, default: '' },
  hint: { type: String, default: '' },
  icon: { type: [Object, Function], default: null },
  tone: { type: String, default: 'brand' },
  alert: { type: Boolean, default: false },
})
</script>

<style scoped>
.metric-card { min-height:112px; padding:15px 16px 13px; background:var(--bg-surface); border:1px solid var(--bd); border-radius:var(--radius); box-shadow:var(--shadow-sm); border-top:3px solid var(--brand); }
.metric-card.tone-warning { border-top-color:#d97706; } .metric-card.tone-info { border-top-color:#3b82f6; }
.metric-card__top { display:flex; justify-content:space-between; align-items:center; color:var(--muted); font-size:12px; } .metric-card__top .el-icon { color:var(--brand); }
.tone-warning .metric-card__top .el-icon { color:#d97706; }
.metric-card__value { margin-top:9px; color:var(--ink); font-size:28px; font-weight:700; line-height:1; letter-spacing:.01em; } .metric-card__value small { margin-left:4px; color:var(--muted); font-size:12px; font-weight:500; }
.metric-card__hint { margin-top:10px; color:var(--muted); font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.metric-card.is-alert { background:linear-gradient(135deg,var(--bg-surface),rgba(217,119,6,.06)); }
</style>

