<template>
  <div class="page">
    <div class="header">
      <div>
        <router-link :to="`/r/${encodeURIComponent(encodedRepo)}`">← 返回仓库</router-link>
        <h1>{{ displayName }}</h1>
        <p class="muted"><code>{{ sessionId }}</code> · {{ session?.git_branch || '—' }}</p>
      </div>
      <div class="actions">
        <a v-if="session?.official_url" class="btn" :href="session.official_url" target="_blank" rel="noopener">官方 Viewer</a>
        <a v-if="mrUrl" class="btn" :href="mrUrl" target="_blank" rel="noopener">GitLab MR</a>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="summary" v-if="session">
      <div class="kpi"><span class="label">HIGH</span><span class="value high">{{ sev.HIGH || 0 }}</span></div>
      <div class="kpi"><span class="label">MEDIUM</span><span class="value medium">{{ sev.MEDIUM || 0 }}</span></div>
      <div class="kpi"><span class="label">LOW</span><span class="value low">{{ sev.LOW || 0 }}</span></div>
      <div class="kpi"><span class="label">评论</span><span class="value">{{ session.comment_total || 0 }}</span></div>
      <div class="kpi"><span class="label">Tokens</span><span class="value">{{ session.tokens?.total || 0 }}</span></div>
    </div>

    <div class="two-pane" v-if="session">
      <div class="pane">
        <div class="pane-title">Issues ({{ issues.length }})</div>
        <div class="scroll">
          <div
            v-for="(issue, idx) in issues"
            :key="idx"
            class="issue-item"
            :class="[issue.level?.toLowerCase(), { selected: selected === issue }]"
            @click="selected = issue"
          >
            <div class="issue-row">
              <span class="badge" :class="(issue.level || 'low').toLowerCase()">{{ issue.level }}</span>
              <span class="line">{{ shortPath(issue.file_path) }}:L{{ issue.line }}</span>
            </div>
            <div class="issue-desc">{{ issue.snippet }}</div>
          </div>
        </div>
      </div>
      <div class="pane">
        <div class="pane-title">详情</div>
        <div class="scroll detail" v-if="selected">
          <div class="detail-meta">
            <span class="badge" :class="(selected.level || 'low').toLowerCase()">{{ selected.level }}</span>
            <span class="muted">{{ selected.file_path }}:L{{ selected.line }}</span>
          </div>
          <div class="body">{{ selected.snippet }}</div>
        </div>
        <div v-else class="empty">选择左侧 issue</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchSession, shortPath } from '../api'

const props = defineProps({
  encodedRepo: { type: String, required: true },
  sessionId: { type: String, required: true },
})

const session = ref(null)
const displayName = ref('')
const mrUrl = ref('')
const selected = ref(null)
const error = ref('')

const sev = computed(() => session.value?.severity || {})
const issues = computed(() => {
  const s = session.value
  if (!s) return []
  if (s.issues?.length) return s.issues
  if (s.comments_by_file?.length) return s.comments_by_file.flatMap((f) => f.comments || [])
  const by = s.comments_by_level || {}
  return [...(by.HIGH || []), ...(by.MEDIUM || []), ...(by.LOW || [])]
})

async function load() {
  error.value = ''
  try {
    const data = await fetchSession(props.encodedRepo, props.sessionId)
    session.value = data.session || data
    displayName.value = data.display_name || props.encodedRepo
    mrUrl.value = data.mr_url || data.record?.mr_url || ''
  } catch (e) {
    error.value = e.message || String(e)
  }
}
watch(issues, (list) => {
  if (!selected.value && list.length) selected.value = list[0]
})
watch(() => [props.encodedRepo, props.sessionId], load)
onMounted(load)
</script>

<style scoped>
.page { max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
.header { display: flex; justify-content: space-between; gap: 12px; }
.header h1 { margin: 8px 0 4px; font-size: 22px; color: var(--text-strong); }
.actions { display: flex; gap: 8px; }
.summary { display: flex; gap: 12px; flex-wrap: wrap; }
.two-pane { display: grid; grid-template-columns: 360px 1fr; gap: 12px; min-height: 420px; }
.pane {
  background: var(--bg-elev); border: 1px solid var(--border); border-radius: 8px;
  display: flex; flex-direction: column; overflow: hidden;
}
.pane-title { padding: 10px 12px; font-weight: 600; border-bottom: 1px solid var(--border); background: var(--bg); }
.scroll { flex: 1; overflow: auto; padding: 8px; }
.issue-item { padding: 10px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; border-left: 3px solid transparent; }
.issue-item:hover { background: var(--bg-hover); }
.issue-item.selected { background: var(--bg-sel); }
.issue-item.high { border-left-color: var(--high); }
.issue-item.medium { border-left-color: var(--medium); }
.issue-item.low { border-left-color: var(--low); }
.issue-row { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }
.line { font-size: 12px; color: var(--link); }
.issue-desc { font-size: 13px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.detail-meta { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.body { white-space: pre-wrap; line-height: 1.6; color: var(--text-strong); }
</style>
