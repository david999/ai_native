<template>
  <div class="page">
    <div class="header">
      <div>
        <router-link to="/repos">← 仓库列表</router-link>
        <h1>{{ displayName }}</h1>
        <p class="muted">{{ encodedRepo }}</p>
      </div>
      <button class="btn" :class="{ active: onlyHigh }" @click="onlyHigh = !onlyHigh; load()">仅 HIGH</button>
    </div>
    <div v-if="error" class="error-banner">{{ error }}</div>
    <div class="list">
      <router-link
        v-for="s in sessions"
        :key="s.session_id"
        class="card"
        :to="`/r/${encodeURIComponent(encodedRepo)}/${encodeURIComponent(s.session_id)}`"
      >
        <div class="title">
          <code>{{ s.session_id }}</code>
          <span v-if="s.has_high" class="badge high">HIGH</span>
        </div>
        <div class="meta muted">
          {{ s.git_branch || '—' }} · H{{ s.high }} M{{ s.medium }} L{{ s.low }} · {{ s.total_tokens_fmt || s.total_tokens }}
        </div>
      </router-link>
      <div v-if="!sessions.length" class="empty">暂无 Session</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { fetchRepo } from '../api'

const props = defineProps({ encodedRepo: { type: String, required: true } })
const sessions = ref([])
const displayName = ref(props.encodedRepo)
const onlyHigh = ref(false)
const error = ref('')

async function load() {
  error.value = ''
  try {
    const data = await fetchRepo(props.encodedRepo, { highlight: onlyHigh.value ? 'high' : '' })
    sessions.value = data.sessions || []
    displayName.value = data.display_name || props.encodedRepo
  } catch (e) {
    error.value = e.message || String(e)
  }
}
watch(() => props.encodedRepo, load)
onMounted(load)
</script>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px; }
.header h1 { margin: 8px 0 4px; font-size: 22px; color: var(--text-strong); }
.list { display: flex; flex-direction: column; gap: 8px; }
.card {
  display: block; padding: 12px 14px; background: var(--bg-elev);
  border: 1px solid var(--border); border-radius: 8px; color: inherit; text-decoration: none;
}
.card:hover { border-color: var(--link); }
.title { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.meta { font-size: 12px; }
</style>
