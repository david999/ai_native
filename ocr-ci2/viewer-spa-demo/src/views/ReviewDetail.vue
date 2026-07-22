<template>
  <div class="detail-page">
    <div class="detail-header">
      <div>
        <h1>{{ review.title }} <span class="muted">{{ review.projectPath }}</span></h1>
        <div class="meta">
          <span class="status" :class="review.status">{{ review.status }}</span>
          <span class="muted">{{ review.targetBranch }}</span>
          <code>{{ review.commitShort }}</code>
          <span class="muted">{{ review.time }}</span>
        </div>
      </div>
      <router-link class="btn" to="/">← 返回工作台</router-link>
    </div>

    <div class="summary">
      <div class="kpi"><span class="label">问题</span><span class="value">{{ review.issues.length }}</span></div>
      <div class="kpi"><span class="label">HIGH</span><span class="value high">{{ highCount }}</span></div>
      <div class="kpi"><span class="label">MEDIUM</span><span class="value medium">{{ mediumCount }}</span></div>
      <div class="kpi"><span class="label">LOW</span><span class="value low">{{ lowCount }}</span></div>
      <div class="kpi"><span class="label">Tokens</span><span class="value">{{ review.totalTokens }}</span></div>
    </div>

    <div class="toolbar">
      <button class="btn" :class="{ active: activeFilter === 'all' }" @click="activeFilter = 'all'">全部</button>
      <button class="btn" :class="{ active: activeFilter === 'HIGH' }" @click="activeFilter = 'HIGH'">HIGH</button>
      <button class="btn" :class="{ active: activeFilter === 'MEDIUM' }" @click="activeFilter = 'MEDIUM'">MEDIUM</button>
      <button class="btn" :class="{ active: activeFilter === 'LOW' }" @click="activeFilter = 'LOW'">LOW</button>
    </div>

    <div class="issue-list">
      <div
        v-for="(issue, idx) in filteredIssues"
        :key="idx"
        class="issue-card"
        :class="issue.level.toLowerCase()"
      >
        <div class="issue-header">
          <span class="badge" :class="issue.level.toLowerCase()">{{ issue.level }}</span>
          <span class="line" @click="goToLine(issue.filePath, issue.line)">
            {{ issue.filePath }}<span v-if="issue.line">:L{{ issue.line }}</span>
          </span>
        </div>
        <div class="issue-body">{{ issue.description }}</div>
        <div v-if="issue.suggestion" class="suggestion">
          <div class="suggestion-label">建议</div>
          <pre><code>{{ issue.suggestion }}</code></pre>
        </div>
        <div v-if="issue.diff" class="diff">
          <div class="diff-label">修改建议</div>
          <pre><code>{{ issue.diff }}</code></pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const review = ref({
  title: '!100',
  projectPath: 'java_group/metric-service',
  targetBranch: 'main',
  commitShort: 'abc12345',
  status: 'success',
  time: '2026-07-22 10:00:00',
  totalTokens: '156K',
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
    }
  ]
})

const activeFilter = ref('all')
const filteredIssues = computed(() => {
  if (activeFilter.value === 'all') return review.value.issues
  return review.value.issues.filter(i => i.level === activeFilter.value)
})
const highCount = computed(() => review.value.issues.filter(i => i.level === 'HIGH').length)
const mediumCount = computed(() => review.value.issues.filter(i => i.level === 'MEDIUM').length)
const lowCount = computed(() => review.value.issues.filter(i => i.level === 'LOW').length)

function goToLine(path, line) {
  alert('打开 GitLab：' + path + ':' + line)
}
</script>

<style scoped>
.detail-page { max-width: 1200px; margin: 0 auto; color: #c9d1d9; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.detail-header h1 { margin: 0 0 6px; font-size: 22px; color: #f0f6fc; }
.meta { display: flex; gap: 10px; align-items: center; font-size: 13px; }
.status { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
.status.success { background: #238636; color: #fff; }
.btn { display: inline-block; padding: 6px 12px; border: 1px solid #30363d; border-radius: 6px; background: #161b22; color: #c9d1d9; text-decoration: none; cursor: pointer; }
.summary { display: flex; gap: 12px; margin-bottom: 16px; }
.kpi { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; min-width: 90px; }
.kpi .label { display: block; font-size: 12px; color: #8b949e; }
.kpi .value { font-size: 18px; font-weight: 700; color: #f0f6fc; }
.kpi .value.high { color: #f85149; }
.kpi .value.medium { color: #d29922; }
.kpi .value.low { color: #8b949e; }
.toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.toolbar .btn.active { border-color: #58a6ff; color: #58a6ff; background: #121d2f; }
.muted { color: #8b949e; }
.issue-card { border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; background: #161b22; }
.issue-card.high { border-left: 4px solid #f85149; }
.issue-card.medium { border-left: 4px solid #d29922; }
.issue-card.low { border-left: 4px solid #8b949e; }
.issue-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; color: #fff; }
.badge.high { background: #f85149; }
.badge.medium { background: #d29922; }
.badge.low { background: #8b949e; }
.line { font-size: 13px; color: #58a6ff; cursor: pointer; }
.line:hover { text-decoration: underline; }
.issue-body { font-size: 14px; line-height: 1.6; color: #c9d1d9; margin-bottom: 12px; }
.suggestion-label, .diff-label { font-size: 12px; color: #8b949e; margin-bottom: 6px; }
.suggestion pre, .diff pre { margin: 0; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 10px 12px; font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; font-size: 13px; white-space: pre-wrap; color: #c9d1d9; }
.diff { margin-top: 12px; }
</style>
