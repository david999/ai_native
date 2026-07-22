/**
 * Dashboard JSON API 封装（对接方案 A 已落地的 /api/*）。
 * 开发态由 Vite 代理到 :8010；生产态同源由 Gateway 托管。
 */

async function request(path, params = {}) {
  const url = new URL(path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return
    url.searchParams.set(k, String(v))
  })
  const resp = await fetch(url.toString(), {
    headers: { Accept: 'application/json' },
  })
  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    throw new Error(`API ${resp.status}: ${text || resp.statusText}`)
  }
  return resp.json()
}

export function fetchReviews({ q = '', highlight = '', limit = 50, offset = 0 } = {}) {
  return request('/api/reviews', { q, highlight, limit, offset })
}

export function fetchReview(jobId) {
  return request(`/api/reviews/${encodeURIComponent(jobId)}`)
}

export function fetchStats(days = 30) {
  return request('/api/stats', { days })
}

export function fetchRepos({ highlight = '' } = {}) {
  return request('/api/repos', { highlight })
}

export function fetchRepo(encodedRepo, { highlight = '' } = {}) {
  return request(`/api/repos/${encodeURIComponent(encodedRepo)}`, { highlight })
}

export function fetchSession(encodedRepo, sessionId) {
  return request(
    `/api/repos/${encodeURIComponent(encodedRepo)}/sessions/${encodeURIComponent(sessionId)}`,
  )
}

export function fetchMrHistory(projectId, mrIid) {
  return request(
    `/api/mr/${encodeURIComponent(projectId)}/${encodeURIComponent(mrIid)}`,
  )
}

export function fetchApiHealth() {
  return request('/api/health')
}

/** 把 finished_at ISO 裁成 UTC+8 可读时间（后端已按 Asia/Shanghai 切日）。 */
export function formatTime(iso) {
  if (!iso) return '—'
  // 后端返回带偏移或 Z；直接截取前 19 位作兜底展示
  const s = String(iso).replace('T', ' ')
  return s.length >= 19 ? s.slice(0, 19) : s
}

export function shortPath(path) {
  if (!path) return '(unknown)'
  const parts = String(path).split('/')
  return parts.length > 3 ? `.../${parts.slice(-3).join('/')}` : path
}
