<template>
  <div class="stats-page">
    <div class="header">
      <h1>统计概览</h1>
      <div class="days">
        <button
          v-for="d in [7, 14, 30, 90]"
          :key="d"
          class="btn"
          :class="{ active: days === d }"
          @click="load(d)"
        >{{ d }}天</button>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="!loading && !hasMrIndex" class="info-banner">
      统计与 MR 列表来自 Gateway 评审索引（<code>review-index.jsonl</code>）。当前索引为空时 KPI 与趋势均为 0；
      本地 OCR Session 请在工作台或「仓库」页查看。
    </div>
    <KpiBar :kpis="overview.kpis || {}" />

    <div class="grid">
      <section class="card chart-wide">
        <div class="chart-head">
          <h3>每日评审量 / HIGH（横向日期轴，可左右滑动）</h3>
          <div class="legend">
            <span class="legend-item reviews">评审数</span>
            <span class="legend-item high">HIGH</span>
          </div>
        </div>
        <div class="timeline-scroll">
          <div class="timeline-chart" :style="{ minWidth: chartMinWidth }">
            <div class="timeline-cols">
              <div
                v-for="row in daily"
                :key="row.date"
                class="timeline-col"
                :title="`${row.date}：评审 ${row.reviews}，HIGH ${row.high}`"
              >
                <div class="timeline-bars">
                  <div
                    class="timeline-bar reviews"
                    :style="{ height: barHeight(row.reviews, maxReviews) }"
                  ></div>
                  <div
                    class="timeline-bar high"
                    :style="{ height: barHeight(row.high, maxHigh) }"
                  ></div>
                </div>
                <span class="timeline-label">{{ formatDay(row.date) }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <h3>项目 HIGH Top5</h3>
        <table class="table">
          <thead><tr><th>项目</th><th>HIGH</th><th>评审数</th></tr></thead>
          <tbody>
            <tr v-for="p in topProjects" :key="p.project_path">
              <td>{{ p.project_path }}</td>
              <td class="high">{{ p.high }}</td>
              <td>{{ p.reviews }}</td>
            </tr>
            <tr v-if="!topProjects.length"><td colspan="3" class="muted">暂无数据</td></tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <h3>每日明细</h3>
        <div class="table-scroll">
          <table class="table compact">
            <thead>
              <tr><th>日期</th><th>评审</th><th class="high">HIGH</th><th>Token 中位</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in dailyReversed" :key="'t'+row.date">
                <td>{{ row.date }}</td>
                <td>{{ row.reviews }}</td>
                <td class="high">{{ row.high }}</td>
                <td>{{ row.median_tokens }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchStats } from '../api'
import KpiBar from '../components/KpiBar.vue'

const days = ref(30)
const overview = ref({})
const error = ref('')
const loading = ref(false)
const hasMrIndex = computed(() => overview.value.has_mr_index === true)

const daily = computed(() => overview.value.daily || [])
const dailyReversed = computed(() => [...daily.value].reverse())
const topProjects = computed(() => overview.value.project_high_top || [])
const maxReviews = computed(() => Math.max(1, ...daily.value.map((r) => Number(r.reviews) || 0)))
const maxHigh = computed(() => Math.max(1, ...daily.value.map((r) => Number(r.high) || 0)))
const chartMinWidth = computed(() => `${Math.max(480, daily.value.length * 28)}px`)

function barHeight(value, max) {
  const n = Number(value) || 0
  const pct = Math.round((n / max) * 100)
  return `${Math.max(n > 0 ? 6 : 0, pct)}%`
}

function formatDay(iso) {
  if (!iso) return '—'
  return String(iso).slice(5)
}

async function load(d = days.value) {
  days.value = d
  error.value = ''
  loading.value = true
  try {
    overview.value = await fetchStats(d)
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => load())
</script>

<style scoped>
.stats-page { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.info-banner {
  background: #121d2f; border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 14px; font-size: 13px; color: var(--muted); line-height: 1.5;
}
.info-banner code { color: var(--text); }
.header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.header h1 { margin: 0; font-size: 22px; color: var(--text-strong); }
.days { display: flex; gap: 8px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card {
  background: var(--bg-elev); border: 1px solid var(--border); border-radius: 8px; padding: 14px;
}
.chart-wide { grid-column: 1 / -1; }
.card h3 { margin: 0 0 12px; font-size: 14px; color: var(--text-strong); }
.chart-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.chart-head h3 { margin: 0; }
.legend { display: flex; gap: 12px; font-size: 12px; color: var(--muted); }
.legend-item::before {
  content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px;
}
.legend-item.reviews::before { background: var(--link); }
.legend-item.high::before { background: var(--high); }
.timeline-scroll { overflow-x: auto; padding-bottom: 4px; }
.timeline-chart { padding: 4px 8px 0; }
.timeline-cols {
  display: flex; align-items: flex-end; gap: 6px; height: 200px; border-bottom: 1px solid var(--border);
}
.timeline-col {
  flex: 1 0 22px; min-width: 22px; display: flex; flex-direction: column; align-items: center; height: 100%;
}
.timeline-bars {
  flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; gap: 2px;
}
.timeline-bar { width: 42%; border-radius: 3px 3px 0 0; min-height: 0; transition: height .15s; }
.timeline-bar.reviews { background: var(--link); }
.timeline-bar.high { background: var(--high); }
.timeline-label {
  font-size: 10px; color: var(--muted); margin-top: 6px; white-space: nowrap;
  transform: rotate(-45deg); transform-origin: top center; height: 28px;
}
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
.table.compact { font-size: 12px; }
.table-scroll { max-height: 280px; overflow: auto; }
.high { color: var(--high); font-weight: 600; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
</style>
