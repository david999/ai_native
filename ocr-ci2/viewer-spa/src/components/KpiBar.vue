<template>
  <div class="kpi-bar">
    <!-- 字段名与 review_index.compute_kpis 对齐 -->
    <div class="kpi"><span class="label">今日评审</span><span class="value">{{ num(kpis.today_reviews) }}</span></div>
    <div class="kpi"><span class="label">HIGH</span><span class="value high">{{ num(kpis.open_high) }}</span></div>
    <div class="kpi"><span class="label">队列</span><span class="value">{{ num(kpis.queue_depth) }}</span></div>
    <div class="kpi"><span class="label">7日Token中位</span><span class="value">{{ kpis.median_tokens_7d_fmt || '—' }}</span></div>
  </div>
</template>

<script setup>
defineProps({
  kpis: { type: Object, default: () => ({}) },
})
function num(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
</script>
