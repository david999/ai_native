<template>
  <div class="workbench">
    <div class="header">
      <h1>评审工作台</h1>
      <p class="hint">左侧选 MR → 中间选 issue → 右侧看详情；可跳转 GitLab 查看原文</p>
    </div>

    <KpiBar :kpis="kpis" />

    <div class="filters">
      <input v-model="query" class="search" placeholder="按项目路径过滤…" @keyup.enter="reload" />
      <button class="btn" :class="{ active: onlyHigh }" @click="toggleHigh">HIGH</button>
      <button class="btn" :class="{ active: onlyFailed }" @click="toggleFailed">失败</button>
      <button class="btn" @click="reload">刷新</button>
      <span class="muted" v-if="loading">加载中…</span>
      <span class="status-legend muted" title="任务状态说明">已完成=评审跑完 · 失败=任务出错 · 进行中/排队=实时</span>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

  <div v-if="!loading && !items.length && !hasMrIndex" class="info-banner">
    暂无 Gateway MR 评审索引（<code>review-index.jsonl</code>）。触发 CI 或 POST
    <code>/v1/review/merge-request</code> 后，MR 会出现在左侧列表；统计页 KPI 亦来自该索引。
    下方可浏览本地 OCR Session。
  </div>

    <div class="three-pane">
      <!-- 左：MR 列表 -->
      <div class="pane">
        <div class="pane-title">MR 列表 ({{ items.length }})</div>
        <div class="scroll">
          <div
            v-for="row in items"
            :key="row.job_id"
            class="mr-item"
            :class="{
              selected: selectedJobId === row.job_id,
              high: row.high > 0,
              failed: row.status === 'failed',
            }"
            @click="selectMr(row)"
          >
            <div class="title">
              <span class="iid">{{ row.mr_label }}</span>
              <span
                class="status"
                :class="row.status"
                :title="row.status_hint || ''"
              >{{ row.status_label || row.status }}</span>
            </div>
            <div class="meta muted">{{ row.project_path }}</div>
            <div class="stats">
              <span v-if="row.high" class="high">H{{ row.high }}</span>
              <span v-if="row.medium" class="medium">M{{ row.medium }}</span>
              <span v-if="row.low" class="low">L{{ row.low }}</span>
              <span class="muted">{{ row.total_tokens_fmt }}</span>
            </div>
          </div>
          <div v-if="!items.length && !loading" class="empty">暂无 Gateway MR 评审</div>
          <div v-if="localRepos.length" class="local-section">
            <div class="local-title muted">本地 Session（非 Gateway 索引）</div>
            <div
              v-for="repo in localRepos"
              :key="repo.encoded_path"
              class="local-item"
              :class="{ selected: selectedLocalKey === repo.encoded_path }"
              @click="selectLocalRepo(repo)"
            >
              <div class="title">
                <span class="iid">📁</span>
                <span>{{ repo.display_name }}</span>
              </div>
              <div class="meta muted">{{ repo.session_count }} sessions</div>
              <div class="stats">
                <span v-if="repo.high" class="high">H{{ repo.high }}</span>
                <span v-if="repo.medium" class="medium">M{{ repo.medium }}</span>
                <span class="muted">{{ repo.latest_tokens_fmt }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 中：issue 列表 -->
      <div class="pane">
        <div class="pane-title">
          Issues
          <span v-if="issues.length" class="muted">({{ issues.length }})</span>
        </div>
        <div class="scroll" v-if="hasSelection">
          <div v-if="detailLoading" class="empty">加载详情…</div>
          <div v-else-if="!issues.length" class="empty">该 MR 暂无 issue</div>
          <div
            v-for="(issue, idx) in issues"
            :key="idx"
            class="issue-item"
            :class="[issue.level?.toLowerCase(), { selected: selectedIssue === issue }]"
            @click="selectedIssue = issue"
          >
            <div class="issue-row">
              <span class="badge" :class="(issue.level || 'low').toLowerCase()">{{ issue.level || 'LOW' }}</span>
              <span class="line">{{ shortPath(issue.file_path) }}:L{{ issue.line }}</span>
            </div>
            <div class="issue-desc">{{ issue.snippet || issue.description || '（无描述）' }}</div>
          </div>
        </div>
        <div v-else class="empty">选择左侧 MR 或本地 Session</div>
      </div>

      <!-- 右：issue 详情 -->
      <div class="pane">
        <div class="pane-title">
          {{ selectedIssue ? `${shortPath(selectedIssue.file_path)}:L${selectedIssue.line}` : 'Issue 详情' }}
        </div>
        <div class="scroll detail" v-if="selectedIssue">
          <div class="detail-meta">
            <span class="badge" :class="(selectedIssue.level || 'low').toLowerCase()">
              {{ selectedIssue.level || 'LOW' }}
            </span>
            <a
              v-if="gitlabUrl"
              class="link"
              :href="gitlabUrl"
              target="_blank"
              rel="noopener"
            >在 GitLab 中打开</a>
            <router-link
              v-if="record?.session_url && record?.encoded_repo && record?.session_id"
              class="link"
              :to="`/r/${encodeURIComponent(record.encoded_repo)}/${encodeURIComponent(record.session_id)}`"
            >Session</router-link>
            <a
              v-else-if="record?.session_url"
              class="link"
              :href="record.session_url"
            >Session</a>
            <router-link
              v-if="record"
              class="link"
              :to="`/mr/${encodeURIComponent(record.project_id)}/${encodeURIComponent(record.mr_iid)}`"
            >MR 历史</router-link>
          </div>
          <div class="issue-body">{{ selectedIssue.snippet || selectedIssue.description }}</div>
          <div class="meta-block muted">
            <div>文件：<code>{{ selectedIssue.file_path }}</code></div>
            <div>行号：L{{ selectedIssue.line }}</div>
            <div v-if="record">项目：{{ record.project_path }} {{ record.mr_label }}</div>
          </div>
        </div>
        <div v-else class="empty">选择中间 issue 查看详情</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { fetchReview, fetchReviews, fetchSession, formatTime, shortPath } from '../api'
import KpiBar from '../components/KpiBar.vue'

const items = ref([])
const localRepos = ref([])
const hasMrIndex = ref(false)
const kpis = ref({})
const query = ref('')
const onlyHigh = ref(false)
const onlyFailed = ref(false)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const selectedJobId = ref('')
const selectedLocalKey = ref('')
const record = ref(null)
const issues = ref([])
const selectedIssue = ref(null)
let pollTimer = null

const hasSelection = computed(() => Boolean(selectedJobId.value || selectedLocalKey.value))

const highlight = computed(() => {
  if (onlyFailed.value) return 'failed'
  if (onlyHigh.value) return 'high'
  return ''
})

const gitlabUrl = computed(() => {
  // 优先用后端给出的 MR URL；行级锚点依赖 GitLab 版本，能跳 MR 即可
  if (!record.value?.mr_url) return ''
  const base = record.value.mr_url
  if (!selectedIssue.value?.file_path) return base
  // GitLab diffs 页：尽量附带文件名，便于人工定位
  const file = encodeURIComponent(selectedIssue.value.file_path)
  return `${base}/diffs?file=${file}`
})

async function reload() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchReviews({ q: query.value, highlight: highlight.value, limit: 100 })
    items.value = data.items || []
    localRepos.value = data.local_repos || []
    hasMrIndex.value = Boolean(data.has_mr_index)
    kpis.value = data.kpis || {}
    // 保持选中：优先 MR job，其次本地 Session；都不在则回落到首条 MR
    const still = items.value.find((r) => r.job_id === selectedJobId.value)
    const stillLocal = localRepos.value.find((r) => r.encoded_path === selectedLocalKey.value)
    if (still) {
      await loadDetail(still.job_id, { keepIssue: true })
    } else if (stillLocal) {
      await selectLocalRepo(stillLocal, { keepIssue: true })
    } else if (items.value.length) {
      await selectMr(items.value[0])
    } else {
      selectedJobId.value = ''
      selectedLocalKey.value = ''
      record.value = null
      issues.value = []
      selectedIssue.value = null
    }
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

async function selectMr(row) {
  selectedJobId.value = row.job_id
  selectedLocalKey.value = ''
  await loadDetail(row.job_id, { keepIssue: false })
}

function applyIssuesFromSession(session, { keepIssue }) {
  let list = session?.issues || []
  if (!list.length && session?.comments_by_file) {
    list = session.comments_by_file.flatMap((f) => f.comments || [])
  }
  if (!list.length && session?.comments_by_level) {
    list = [
      ...(session.comments_by_level.HIGH || []),
      ...(session.comments_by_level.MEDIUM || []),
      ...(session.comments_by_level.LOW || []),
    ]
  }
  const prevKey = selectedIssue.value
    ? `${selectedIssue.value.file_path}:${selectedIssue.value.line}:${selectedIssue.value.snippet}`
    : ''
  issues.value = list
  if (keepIssue && prevKey) {
    selectedIssue.value =
      list.find((i) => `${i.file_path}:${i.line}:${i.snippet}` === prevKey) || list[0] || null
  } else {
    selectedIssue.value = list[0] || null
  }
}

async function selectLocalRepo(repo, { keepIssue = false } = {}) {
  selectedJobId.value = ''
  selectedLocalKey.value = repo.encoded_path
  if (!repo.latest_session_id) {
    record.value = {
      project_path: '本地 Session',
      mr_label: `📁 ${repo.display_name}`,
    }
    issues.value = []
    selectedIssue.value = null
    return
  }
  detailLoading.value = true
  try {
    const data = await fetchSession(repo.encoded_path, repo.latest_session_id)
    record.value = data.record || {
      encoded_repo: repo.encoded_path,
      session_id: repo.latest_session_id,
      project_path: '本地 Session',
      mr_label: `📁 ${repo.display_name}`,
      session_url: `/r/${encodeURIComponent(repo.encoded_path)}/${encodeURIComponent(repo.latest_session_id)}`,
    }
    applyIssuesFromSession(data.session, { keepIssue })
  } catch (e) {
    error.value = e.message || String(e)
    issues.value = []
    selectedIssue.value = null
  } finally {
    detailLoading.value = false
  }
}

async function loadDetail(jobId, { keepIssue }) {
  detailLoading.value = true
  try {
    const data = await fetchReview(jobId)
    record.value = data.record
    applyIssuesFromSession(data.session, { keepIssue })
  } catch (e) {
    error.value = e.message || String(e)
    issues.value = []
    selectedIssue.value = null
  } finally {
    detailLoading.value = false
  }
}

function toggleHigh() {
  onlyHigh.value = !onlyHigh.value
  if (onlyHigh.value) onlyFailed.value = false
  reload()
}
function toggleFailed() {
  onlyFailed.value = !onlyFailed.value
  if (onlyFailed.value) onlyHigh.value = false
  reload()
}

watch(query, () => {
  // 输入时不自动刷，回车/刷新按钮触发；此处仅占位
})

onMounted(() => {
  reload()
  // 有运行中 job 时 10s 轮询列表（与方案 A 一致）
  pollTimer = setInterval(() => {
    const active = items.value.some((r) => r.status === 'running' || r.status === 'queued')
    if (active) reload()
  }, 10000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// 暴露给模板（formatTime 备用）
void formatTime
</script>

<style scoped>
.workbench { max-width: 1600px; margin: 0 auto; height: calc(100vh - 100px); display: flex; flex-direction: column; gap: 12px; }
.header h1 { margin: 0 0 4px; font-size: 22px; color: var(--text-strong); }
.hint { margin: 0; color: var(--muted); font-size: 13px; }
.filters { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.status-legend { font-size: 12px; margin-left: auto; max-width: 420px; line-height: 1.35; }
.search {
  padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px;
  min-width: 240px; background: var(--bg); color: var(--text);
}
.three-pane { display: grid; grid-template-columns: 260px 340px 1fr; gap: 12px; flex: 1; min-height: 0; }
.pane {
  background: var(--bg-elev); border: 1px solid var(--border); border-radius: 8px;
  display: flex; flex-direction: column; overflow: hidden;
}
.pane-title {
  padding: 10px 12px; font-weight: 600; font-size: 13px;
  border-bottom: 1px solid var(--border); background: var(--bg); color: var(--text-strong);
}
.scroll { flex: 1; overflow-y: auto; padding: 8px; }
.mr-item, .issue-item {
  padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px;
  border-left: 3px solid transparent;
}
.mr-item:hover, .issue-item:hover { background: var(--bg-hover); }
.mr-item.selected, .issue-item.selected { background: var(--bg-sel); }
.mr-item.high { background: #2d1b1b; }
.mr-item.failed { background: #2d1b1b; }
.iid { font-weight: 700; color: var(--text-strong); margin-right: 8px; }
.meta { font-size: 12px; margin-top: 4px; }
.stats { display: flex; gap: 6px; margin-top: 6px; font-size: 12px; font-weight: 600; }
.high { color: var(--high); }
.medium { color: var(--medium); }
.low { color: var(--low); }
.issue-item.high { border-left-color: var(--high); }
.issue-item.medium { border-left-color: var(--medium); }
.issue-item.low { border-left-color: var(--low); }
.issue-row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.line { font-size: 12px; color: var(--link); }
.issue-desc {
  font-size: 13px; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.detail-meta { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.link { color: var(--link); cursor: pointer; font-size: 13px; }
.issue-body { font-size: 15px; line-height: 1.6; color: var(--text-strong); margin-bottom: 16px; white-space: pre-wrap; }
.meta-block { font-size: 13px; line-height: 1.7; }
.detail { padding: 12px; }
.empty { color: var(--muted); text-align: center; padding: 12px; font-size: 13px; }
.info-banner {
  background: #121d2f; border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 14px; font-size: 13px; color: var(--muted); line-height: 1.5;
}
.info-banner code { color: var(--text); }
.local-section { margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border); }
.local-title { font-size: 12px; margin-bottom: 8px; }
.local-item {
  display: block; padding: 10px 12px; border-radius: 6px; margin-bottom: 4px;
  color: inherit; text-decoration: none; transition: background .12s; cursor: pointer;
}
.local-item:hover { background: var(--bg-hover); }
.local-item.selected { background: var(--bg-sel); }
</style>
