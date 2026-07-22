<template>
  <div class="page">
    <div class="header">
      <div>
        <router-link to="/">← 工作台</router-link>
        <h1>MR {{ mrLabel }} <span class="muted">{{ projectPath }}</span></h1>
      </div>
      <a v-if="mrUrl" class="btn" :href="mrUrl" target="_blank" rel="noopener">打开 GitLab MR</a>
    </div>
    <div v-if="error" class="error-banner">{{ error }}</div>
    <table class="table">
      <thead>
        <tr><th></th><th>Job</th><th>状态</th><th>HIGH</th><th>评论</th><th>Tokens</th><th>完成时间</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="r in reviews" :key="r.job_id">
          <td><span v-if="r.is_latest" class="badge medium">最新</span></td>
          <td><code>{{ r.job_id }}</code></td>
                <td><span class="status" :class="r.status" :title="r.status_hint">{{ r.status_label || r.status }}</span></td>
          <td class="high">{{ r.high }}</td>
          <td>{{ r.comment_count }}</td>
          <td>{{ r.total_tokens_fmt }}</td>
          <td class="muted">{{ formatTime(r.finished_at) }}</td>
          <td>
            <router-link v-if="r.session_url" :to="sessionRoute(r)">Session</router-link>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchMrHistory, formatTime } from '../api'

const props = defineProps({
  projectId: { type: String, required: true },
  mrIid: { type: String, required: true },
})

const reviews = ref([])
const projectPath = ref('')
const mrUrl = ref('')
const error = ref('')
const mrLabel = computed(() => `!${props.mrIid}`)

function sessionRoute(r) {
  // session_url 形如 /r/{encoded}/{sessionId}，Vue Router 可直接用 path
  if (r.encoded_repo && r.session_id) {
    return `/r/${encodeURIComponent(r.encoded_repo)}/${encodeURIComponent(r.session_id)}`
  }
  return r.session_url || '/'
}

async function load() {
  error.value = ''
  try {
    const data = await fetchMrHistory(props.projectId, props.mrIid)
    reviews.value = data.reviews || []
    projectPath.value = data.project_path || ''
    mrUrl.value = data.mr_url || ''
  } catch (e) {
    error.value = e.message || String(e)
  }
}
watch(() => [props.projectId, props.mrIid], load)
onMounted(load)
</script>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px; }
.header h1 { margin: 8px 0 0; font-size: 22px; color: var(--text-strong); }
.table { width: 100%; border-collapse: collapse; background: var(--bg-elev); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.table th, .table td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
.high { color: var(--high); font-weight: 600; }
</style>
