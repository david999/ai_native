<template>
  <div class="page">
    <div class="header">
      <h1>本地仓库 Session</h1>
      <button class="btn" :class="{ active: onlyHigh }" @click="onlyHigh = !onlyHigh; load()">仅 HIGH</button>
    </div>
    <div v-if="error" class="error-banner">{{ error }}</div>
    <table class="table">
      <thead>
        <tr><th>仓库</th><th>Session</th><th>HIGH</th><th>MED</th><th>LOW</th><th>Tokens</th><th>最近</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in repos" :key="r.encoded_path">
          <td><router-link :to="`/r/${encodeURIComponent(r.encoded_path)}`">{{ r.display_name }}</router-link></td>
          <td>{{ r.session_count }}</td>
          <td class="high">{{ r.high }}</td>
          <td class="medium">{{ r.medium }}</td>
          <td>{{ r.low }}</td>
          <td>{{ r.latest_tokens_fmt || r.latest_tokens || '—' }}</td>
          <td class="muted">{{ formatTime(r.last_modified) }}</td>
        </tr>
        <tr v-if="!repos.length"><td colspan="7" class="muted">暂无本地 Session</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchRepos, formatTime } from '../api'

const repos = ref([])
const onlyHigh = ref(false)
const error = ref('')

async function load() {
  error.value = ''
  try {
    const data = await fetchRepos({ highlight: onlyHigh.value ? 'high' : '' })
    repos.value = data.items || data.repos || []
  } catch (e) {
    error.value = e.message || String(e)
  }
}
onMounted(load)
</script>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.header h1 { margin: 0; font-size: 22px; color: var(--text-strong); }
.table { width: 100%; border-collapse: collapse; background: var(--bg-elev); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.table th, .table td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
.high { color: var(--high); font-weight: 600; }
.medium { color: var(--medium); }
</style>
