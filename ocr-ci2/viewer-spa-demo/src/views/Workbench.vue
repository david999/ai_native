<template>
  <div class="workbench">
    <div class="header">
      <h1>评审工作台</h1>
      <p class="hint">左侧选 MR → 中间选 issue → 右侧看详情与代码</p>
    </div>

    <section class="kpi-bar">
      <div class="kpi"><span class="label">今日评审</span><span class="value">8</span></div>
      <div class="kpi"><span class="label">HIGH</span><span class="value high">13</span></div>
      <div class="kpi"><span class="label">MEDIUM</span><span class="value medium">5</span></div>
      <div class="kpi"><span class="label">LOW</span><span class="value low">3</span></div>
      <div class="kpi"><span class="label">7日Token</span><span class="value">120K</span></div>
    </section>

    <div class="filters">
      <input v-model="query" placeholder="按项目路径过滤…" class="search" />
      <button class="btn" :class="{ active: onlyHigh }" @click="onlyHigh = !onlyHigh">HIGH</button>
      <button class="btn" :class="{ active: onlyMedium }" @click="onlyMedium = !onlyMedium">MEDIUM</button>
      <button class="btn" :class="{ active: onlyLow }" @click="onlyLow = !onlyLow">LOW</button>
      <button class="btn" :class="{ active: onlyFailed }" @click="onlyFailed = !onlyFailed">失败</button>
    </div>

    <div class="three-pane">
      <!-- 左侧：MR 列表 -->
      <div class="pane mr-list">
        <div class="pane-title">MR 列表</div>
        <div class="scroll">
          <div
            v-for="row in filteredRows"
            :key="row.jobId"
            class="mr-item"
            :class="{
              high: row.high > 0,
              failed: row.status === 'failed',
              selected: selectedMr?.jobId === row.jobId
            }"
            @click="selectMr(row)"
          >
            <div class="title">
              <span class="iid">{{ row.mrLabel }}</span>
            </div>
            <div class="meta">
              <span class="status" :class="row.status">{{ row.status }}</span>
              <span class="muted">{{ row.projectPath }}</span>
            </div>
            <div class="stats">
              <span v-if="row.high" class="high">H{{ row.high }}</span>
              <span v-if="row.medium" class="medium">M{{ row.medium }}</span>
              <span v-if="row.low" class="low">L{{ row.low }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 中间：issue 列表（按问题为维度） -->
      <div class="pane issue-pane">
        <div class="pane-title">{{ selectedMr ? `Issues (${selectedMr.issues.length})` : 'Issues' }}</div>
        <div class="scroll" v-if="selectedMr">
          <div
            v-for="(issue, idx) in selectedMr.issues"
            :key="idx"
            class="issue-item"
            :class="{
              selected: selectedIssue === issue,
              high: issue.level === 'HIGH',
              medium: issue.level === 'MEDIUM',
              low: issue.level === 'LOW'
            }"
            @click="selectIssue(issue)"
          >
            <div class="issue-row">
              <span class="badge" :class="issue.level.toLowerCase()">{{ issue.level }}</span>
              <span class="line">{{ shortPath(issue.filePath) }}:L{{ issue.line }}</span>
            </div>
            <div class="issue-desc">{{ issue.description }}</div>
          </div>
        </div>
        <div class="empty-mini" v-else>
          <p class="muted">选择左侧 MR 后查看问题</p>
        </div>
      </div>

      <!-- 右侧：issue 详情 -->
      <div class="pane detail-pane">
        <div class="pane-title">{{ selectedIssue ? `${shortPath(selectedIssue.filePath)}:L${selectedIssue.line}` : 'Issue 详情' }}</div>
        <div class="scroll" v-if="selectedIssue">
          <div class="detail-meta">
            <span class="badge" :class="selectedIssue.level.toLowerCase()">{{ selectedIssue.level }}</span>
            <a class="link" @click="goToLine(selectedIssue.filePath, selectedIssue.line)">在 GitLab 中打开</a>
            <router-link v-if="selectedMr" class="link" :to="`/review/${selectedMr.jobId}`">查看完整详情 →</router-link>
          </div>
          <div class="issue-body">{{ selectedIssue.description }}</div>
          <div v-if="selectedIssue.suggestion" class="suggestion">
            <div class="suggestion-label">建议</div>
            <pre><code>{{ selectedIssue.suggestion }}</code></pre>
          </div>
          <div v-if="selectedIssue.diff" class="diff">
            <div class="diff-label">修改建议</div>
            <pre><code>{{ selectedIssue.diff }}</code></pre>
          </div>
        </div>
        <div class="scroll" v-else>
          <div class="empty">
            <div class="arrow">←</div>
            <p>选择中间 issue 查看详情</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const rows = ref([
  {
    jobId: 'demo-01', projectId: '1', projectPath: 'java_group/metric-service', mrLabel: '!100', mrUrl: '#',
    targetBranch: 'main', commitShort: 'abc12345', status: 'success', high: 2, medium: 1, low: 1,
    commentCount: 4, totalTokensFmt: '156K',
    issues: [
      {
        level: 'HIGH', filePath: 'src/main/java/io/binghe/metric/config/MetricConfig.java', line: 20,
        description: '使用 System.out.println 记录日志，应替换为 SLF4J 以支持级别控制和统一收集。',
        suggestion: 'private static final Logger log = LoggerFactory.getLogger(MetricConfig.class);\nlog.info("添加测试日志...");',
        diff: '- System.out.println("添加测试日志...");\n+ private static final Logger log = LoggerFactory.getLogger(MetricConfig.class);\n+ log.info("添加测试日志...");'
      },
      {
        level: 'HIGH', filePath: 'src/main/java/io/binghe/metric/config/MetricConfig.java', line: 21,
        description: '存在两条重复的 System.out.println("添加测试日志...") 语句，疑似复制粘贴残留。',
        suggestion: '删除其中一条重复语句，或统一使用日志框架。',
        diff: '- System.out.println("添加测试日志...");\n- System.out.println("添加测试日志...");\n+ log.info("添加测试日志...");'
      },
      {
        level: 'MEDIUM', filePath: 'src/main/java/io/binghe/metric/service/MetricCollector.java', line: 45,
        description: '循环内重复调用 size()，可能造成不必要的性能开销。',
        suggestion: '在循环外缓存 size() 结果，或使用 for-each 遍历。',
        diff: '- for (int i = 0; i < list.size(); i++) { ... }\n+ int size = list.size();\n+ for (int i = 0; i < size; i++) { ... }'
      },
      {
        level: 'LOW', filePath: 'src/main/java/io/binghe/metric/util/DateUtil.java', line: 12,
        description: '魔法值 1000 建议提取为常量。',
        suggestion: 'private static final int MILLISECONDS_PER_SECOND = 1000;',
        diff: '- private static final int MILLISECONDS_PER_SECOND = 1000;\n+ private static final int MILLISECONDS_PER_SECOND = 1000;'
      }
    ]
  },
  {
    jobId: 'demo-02', projectId: '2', projectPath: 'go_group/parser', mrLabel: '!17', mrUrl: '#',
    targetBranch: 'develop', commitShort: 'def67890', status: 'success', high: 1, medium: 0, low: 0,
    commentCount: 1, totalTokensFmt: '89K',
    issues: [
      {
        level: 'HIGH', filePath: 'parser.go', line: 34,
        description: '未处理 error 返回值，可能导致 panic 且丢失错误原因。',
        suggestion: 'if err != nil {\n    return err\n}',
        diff: '- _, err := parse()\n+ result, err := parse()\n+ if err != nil { return err }'
      }
    ]
  },
  {
    jobId: 'demo-03', projectId: '1', projectPath: 'java_group/auth-gateway', mrLabel: '!42', mrUrl: '#',
    targetBranch: 'main', commitShort: 'ghi11122', status: 'failed', high: 0, medium: 0, low: 0,
    commentCount: 0, totalTokensFmt: '—',
    issues: []
  }
])

const query = ref('')
const onlyHigh = ref(false)
const onlyMedium = ref(false)
const onlyLow = ref(false)
const onlyFailed = ref(false)
const selectedMr = ref(rows.value[0])
const selectedIssue = ref(rows.value[0].issues[0])

const filteredRows = computed(() => {
  return rows.value.filter(r => {
    if (query.value && !r.projectPath.toLowerCase().includes(query.value.toLowerCase())) return false
    if (onlyHigh.value && !r.high) return false
    if (onlyMedium.value && !r.medium) return false
    if (onlyLow.value && !r.low) return false
    if (onlyFailed.value && r.status !== 'failed') return false
    return true
  })
})

function selectMr(row) {
  selectedMr.value = row
  selectedIssue.value = row.issues?.[0] || null
}
function selectIssue(issue) {
  selectedIssue.value = issue
}
function shortPath(path) {
  const parts = path.split('/')
  return parts.length > 3 ? '.../' + parts.slice(-3).join('/') : path
}
function goToLine(path, line) {
  alert('打开 GitLab：' + path + ':' + line)
}
</script>

<style scoped>
.workbench { max-width: 1600px; margin: 0 auto; height: calc(100vh - 140px); display: flex; flex-direction: column; color: #c9d1d9; }
.header { margin-bottom: 12px; }
.header h1 { margin: 0 0 4px; font-size: 22px; color: #f0f6fc; }
.hint { color: #8b949e; font-size: 14px; margin: 0; }
.kpi-bar { display: flex; gap: 12px; margin-bottom: 12px; }
.kpi { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 14px; min-width: 80px; }
.kpi .label { display: block; font-size: 12px; color: #8b949e; }
.kpi .value { font-size: 18px; font-weight: 700; color: #f0f6fc; }
.kpi .value.high { color: #f85149; }
.kpi .value.medium { color: #d29922; }
.kpi .value.low { color: #8b949e; }
.filters { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.search { padding: 6px 10px; border: 1px solid #30363d; border-radius: 6px; min-width: 240px; background: #0d1117; color: #c9d1d9; }
.btn { display: inline-block; padding: 5px 10px; border: 1px solid #30363d; border-radius: 6px; background: #161b22; color: #c9d1d9; cursor: pointer; text-decoration: none; font-size: 13px; }
.btn.active { border-color: #58a6ff; color: #58a6ff; background: #121d2f; }
.three-pane { display: grid; grid-template-columns: 240px 320px 1fr; gap: 12px; flex: 1; min-height: 0; }
.pane { background: #161b22; border: 1px solid #30363d; border-radius: 8px; display: flex; flex-direction: column; overflow: hidden; }
.pane-title { padding: 10px 12px; font-weight: 600; font-size: 13px; border-bottom: 1px solid #30363d; background: #0d1117; color: #f0f6fc; }
.scroll { flex: 1; overflow-y: auto; padding: 8px; }
.mr-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; transition: background .12s; }
.mr-item:hover { background: #1f242c; }
.mr-item.selected { background: #1c2f4a; }
.mr-item.high { background: #2d1b1b; }
.mr-item.failed { background: #2d1b1b; }
.mr-item .title { display: flex; gap: 8px; align-items: baseline; }
.iid { font-weight: 700; font-size: 14px; color: #f0f6fc; }
.meta { display: flex; gap: 6px; align-items: center; margin-top: 4px; font-size: 12px; }
.status { display: inline-block; padding: 1px 6px; border-radius: 999px; font-size: 10px; font-weight: 600; text-transform: uppercase; }
.status.success { background: #238636; color: #fff; }
.status.failed { background: #f85149; color: #fff; }
.stats { display: flex; gap: 6px; margin-top: 6px; font-size: 12px; font-weight: 600; }
.high { color: #f85149; }
.medium { color: #d29922; }
.low { color: #8b949e; }
.muted { color: #8b949e; }
.issue-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; transition: background .12s; border-left: 3px solid transparent; }
.issue-item:hover { background: #1f242c; }
.issue-item.selected { background: #1c2f4a; }
.issue-item.high { border-left-color: #f85149; }
.issue-item.medium { border-left-color: #d29922; }
.issue-item.low { border-left-color: #8b949e; }
.issue-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.issue-desc { font-size: 13px; line-height: 1.4; color: #c9d1d9; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; color: #fff; }
.badge.high { background: #f85149; }
.badge.medium { background: #d29922; }
.badge.low { background: #8b949e; }
.line { font-size: 12px; color: #58a6ff; }
.detail-meta { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #30363d; }
.link { color: #58a6ff; cursor: pointer; font-size: 13px; text-decoration: none; }
.link:hover { text-decoration: underline; }
.issue-body { font-size: 15px; line-height: 1.6; color: #f0f6fc; margin-bottom: 16px; }
.suggestion-label, .diff-label { font-size: 12px; color: #8b949e; margin-bottom: 6px; }
.suggestion pre, .diff pre { margin: 0; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 10px 12px; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; font-size: 13px; white-space: pre-wrap; color: #c9d1d9; }
.diff { margin-top: 12px; }
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; color: #8b949e; min-height: 200px; text-align: center; }
.empty-mini { display: flex; align-items: center; justify-content: center; color: #8b949e; min-height: 100px; font-size: 13px; }
.arrow { font-size: 30px; opacity: 0.4; }
</style>
