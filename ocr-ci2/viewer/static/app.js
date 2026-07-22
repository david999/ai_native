/* OCR Gateway Dashboard 工作台交互（方案 A）
 *
 * 能力：
 * - 点击左侧 MR 列表项 → fetch /api/reviews/{job_id} → 右侧按文件渲染评论
 * - 点击本地 Session 项 → fetch /api/repos/{repo}/sessions/{id} → 右侧内联渲染（不跳转）
 * - 运行中/排队中 job 每 10s 局部刷新列表（仅重建 #mrList，保留选中与详情，不清空阅读位置）
 * - 键盘可达：Enter/Space 触发选中
 *
 * 依赖：无外部库，纯原生 JS + fetch；后端端点见 viewer/api.py
 * 时间：后端 finished_at 返回 UTC+8 ISO（如 2026-07-16T17:46:00+08:00），前端直接取字面显示。
 */
(function () {
    "use strict";

    var mrList = document.getElementById("mrList");
    var localList = document.getElementById("localList");
    var detailEmpty = document.getElementById("detailEmpty");
    var detailContent = document.getElementById("detailContent");
    var autoRefreshHint = document.getElementById("autoRefreshHint");
    var refreshTimer = null;
    var selectedJobId = null;
    var selectedLocalKey = null;
    // 记录选中项上一次的状态，用于「running→终态」时刷新详情
    var previousStatus = {};

    var STATUS_LABELS = {
        success: "已完成",
        failed: "失败",
        running: "进行中",
        queued: "排队中",
    };
    var STATUS_HINTS = {
        success: "Gateway 评审任务已执行完毕（ocr review 完成并写入索引）",
        failed: "评审任务失败：拉取代码、ocr review 或回写 GitLab 等环节出错",
        running: "评审任务正在执行",
        queued: "评审任务已入队，等待执行",
    };

    function statusLabel(status) {
        return STATUS_LABELS[status] || status || "—";
    }

    function statusHint(status) {
        return STATUS_HINTS[status] || "";
    }

    function escapeHtml(text) {
        if (text === null || text === undefined) return "";
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    // 安全数字：非数字返回 0，避免 NaN 进入 DOM
    function num(v) {
        var n = Number(v);
        return isNaN(n) ? 0 : n;
    }

    function formatTime(iso) {
        if (!iso) return "—";
        // 后端返回 UTC+8 ISO（含 +08:00），直接取字面日期时间，不依赖浏览器时区
        if (typeof iso === "string" && iso.length >= 19 && iso.charAt(10) === "T") {
            return iso.slice(0, 10) + " " + iso.slice(11, 19);
        }
        var d = new Date(iso);
        if (isNaN(d.getTime())) return escapeHtml(iso);
        var pad = function (n) { return n < 10 ? "0" + n : "" + n; };
        return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
            " " + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }

    // 构造一个 MR 列表项的 HTML（与 Jinja 模板结构一致，样式复用）
    function buildItemHtml(row) {
        var cls = "mr-item";
        if (row.has_high) cls += " mr-item-high";
        else if (row.status === "failed") cls += " mr-item-failed";
        else if (row.status === "running" || row.status === "queued") cls += " mr-item-running";
        if (row.job_id && row.job_id === selectedJobId) cls += " selected";
        var html = '<li class="' + cls + '" data-job-id="' + escapeHtml(row.job_id) + '" data-status="' + escapeHtml(row.status) + '" tabindex="0" role="button" aria-label="查看 ' + escapeHtml(row.project_path) + " " + escapeHtml(row.mr_label) + ' 评审详情">';
        html += '<div class="mr-item-main">';
        html += '<div class="mr-item-title"><span class="mr-iid">' + escapeHtml(row.mr_label) + '</span><span class="mr-project muted">' + escapeHtml(row.project_path) + '</span></div>';
        html += '<div class="mr-item-meta">';
        html += '<span class="status status-' + escapeHtml(row.status) + '" title="' + escapeHtml(statusHint(row.status)) + '">' + escapeHtml(row.status_label || statusLabel(row.status)) + '</span>';
        if (row.target_branch) html += '<span class="muted">' + escapeHtml(row.target_branch) + '</span>';
        html += '<code>' + escapeHtml(row.commit_short) + '</code>';
        html += '<span class="muted">' + formatTime(row.finished_at) + '</span>';
        html += '</div></div>';
        html += '<div class="mr-item-stats">';
        if (num(row.high)) html += '<span class="sev-high" title="HIGH">H' + num(row.high) + '</span>';
        if (num(row.medium)) html += '<span class="sev-medium" title="MEDIUM">M' + num(row.medium) + '</span>';
        if (num(row.low)) html += '<span class="sev-low" title="LOW">L' + num(row.low) + '</span>';
        html += '<span class="muted tokens">' + escapeHtml(row.total_tokens_fmt) + '</span>';
        html += '</div></li>';
        return html;
    }

    function emptyHintHtml() {
        return '<li class="empty-hint muted">暂无 Gateway MR 评审记录。触发 CI 或 POST <code>/v1/review/merge-request</code> 后将出现在此。</li>';
    }

    // 渲染单条评审详情：record 头 + session 评论（按文件）
    function renderDetail(data) {
        var record = data.record;
        var session = data.session;
        if (!record) {
            detailContent.innerHTML = '<p class="muted">未找到评审记录。</p>';
            return;
        }

        var html = "";
        html += '<div class="detail-header">';
        html += '<div class="detail-title">';
        html += '<h2>' + escapeHtml(record.mr_label) + ' <span class="muted">' + escapeHtml(record.project_path) + '</span></h2>';
        html += '<div class="detail-meta">';
        html += '<span class="status status-' + escapeHtml(record.status) + '" title="' + escapeHtml(statusHint(record.status)) + '">' + escapeHtml(record.status_label || statusLabel(record.status)) + '</span>';
        if (record.target_branch) html += '<span class="muted">' + escapeHtml(record.target_branch) + '</span>';
        html += '<code>' + escapeHtml(record.commit_short) + '</code>';
        html += '<span class="muted">' + formatTime(record.finished_at) + '</span>';
        html += '</div></div>';
        html += '<div class="detail-actions">';
        if (record.mr_url) {
            html += '<a class="btn" href="' + escapeHtml(record.mr_url) + '" target="_blank" rel="noopener">GitLab MR</a>';
        }
        if (record.mr_history_url) {
            html += '<a class="btn" href="' + escapeHtml(record.mr_history_url) + '">历史</a>';
        }
        if (record.session_url) {
            html += '<a class="btn" href="' + escapeHtml(record.session_url) + '">Session</a>';
        }
        if (record.official_url) {
            html += '<a class="btn" href="' + escapeHtml(record.official_url) + '" target="_blank" rel="noopener" title="官方 Viewer（Token 按文件）">官方 Viewer</a>';
        }
        html += '</div></div>';

        html += '<div class="detail-summary">';
        html += severityBadge("HIGH", num(record.high));
        html += severityBadge("MEDIUM", num(record.medium));
        html += severityBadge("LOW", num(record.low));
        html += '<span class="detail-tokens muted">评论 ' + num(record.comment_count) + ' · Tokens ' + escapeHtml(record.total_tokens_fmt) + '</span>';
        html += '</div>';

        if (record.message && record.status === "failed") {
            html += '<div class="detail-message">' + escapeHtml(record.message) + '</div>';
        }

        if (session && session.comments_by_file && session.comments_by_file.length) {
            html += '<h3>评论（按文件）</h3>';
            html += '<div class="file-tree">';
            session.comments_by_file.forEach(function (file) {
                var sev = file.severity || {};
                var fileClass = num(sev.HIGH) ? "file-high" : (num(sev.MEDIUM) ? "file-medium" : "file-low");
                html += '<details class="file-node ' + fileClass + '" open>';
                html += '<summary>';
                html += '<code>' + escapeHtml(file.file_path) + '</code>';
                html += '<span class="file-count">' + num(file.comment_count) + ' 条</span>';
                if (num(sev.HIGH)) html += '<span class="sev-high">H' + num(sev.HIGH) + '</span>';
                if (num(sev.MEDIUM)) html += '<span class="sev-medium">M' + num(sev.MEDIUM) + '</span>';
                if (num(sev.LOW)) html += '<span class="sev-low">L' + num(sev.LOW) + '</span>';
                html += '</summary>';
                html += '<ul class="file-comments">';
                file.comments.forEach(function (c) {
                    var level = (c.level || "low").toLowerCase();
                    html += '<li class="comment-item comment-' + level + '">';
                    if (num(c.line)) {
                        html += '<div class="comment-loc">L' + num(c.line) + '</div>';
                    }
                    html += '<pre class="comment-text">' + escapeHtml(c.snippet) + '</pre>';
                    html += '</li>';
                });
                html += '</ul>';
                html += '</details>';
            });
            html += '</div>';

            html += '<details class="session-meta-detail"><summary>Session 元数据</summary>';
            html += '<div class="meta-grid">';
            if (session.git_branch) html += '<p><strong>Branch:</strong> ' + escapeHtml(session.git_branch) + '</p>';
            if (session.files_reviewed !== null && session.files_reviewed !== undefined) {
                html += '<p><strong>Files reviewed:</strong> ' + num(session.files_reviewed) + '</p>';
            }
            if (session.duration_seconds !== null && session.duration_seconds !== undefined) {
                html += '<p><strong>Duration:</strong> ' + Number(session.duration_seconds).toFixed(1) + 's</p>';
            }
            var tok = session.tokens || {};
            html += '<p><strong>Tokens:</strong> prompt ' + num(tok.prompt) + ' / completion ' + num(tok.completion) + ' / total ' + num(tok.total) + ' · ' + num(tok.llm_requests) + ' LLM</p>';
            if (num(session.llm_failures)) html += '<p class="sev-high"><strong>LLM failures:</strong> ' + num(session.llm_failures) + '</p>';
            html += '</div></details>';
        } else if (session && num(session.comment_total) === 0) {
            html += '<p class="muted">该评审无评论。</p>';
        } else if (!session) {
            html += '<div class="detail-placeholder">';
            html += '<p class="muted">该评审未关联本地 Session（可能 session JSONL 已清理或评审仍在进行）。</p>';
            if (record.session_url) {
                html += '<p><a class="btn" href="' + escapeHtml(record.session_url) + '">打开 Session 页</a></p>';
            }
            html += '</div>';
        }

        detailContent.innerHTML = html;
        detailEmpty.hidden = true;
        detailContent.hidden = false;
    }

    function severityBadge(level, count) {
        if (!count) return '<span class="sev-badge sev-badge-' + level.toLowerCase() + ' sev-zero">' + level + ' 0</span>';
        return '<span class="sev-badge sev-badge-' + level.toLowerCase() + '">' + level + ' ' + count + '</span>';
    }

    function setLoading(active) {
        detailContent.classList.toggle("loading", active);
    }

    function findItemByJob(jobId) {
        if (!mrList || !jobId) return null;
        var items = mrList.querySelectorAll(".mr-item[data-job-id]");
        for (var i = 0; i < items.length; i++) {
            if (items[i].getAttribute("data-job-id") === jobId) return items[i];
        }
        return null;
    }

    function clearSelection() {
        var siblings = document.querySelectorAll(".mr-item");
        siblings.forEach(function (el) { el.classList.remove("selected"); });
    }

    function selectMr(item, opts) {
        opts = opts || {};
        var jobId = item.getAttribute("data-job-id");
        if (!jobId) return;
        selectedJobId = jobId;
        selectedLocalKey = null;

        clearSelection();
        item.classList.add("selected");

        detailEmpty.hidden = true;
        detailContent.hidden = false;
        if (!opts.silent) {
            setLoading(true);
            detailContent.innerHTML = '<p class="muted">加载中…</p>';
        }

        fetch("/api/reviews/" + encodeURIComponent(jobId), { headers: { "Accept": "application/json" } })
            .then(function (resp) {
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                return resp.json();
            })
            .then(function (data) {
                setLoading(false);
                renderDetail(data);
                if (data.record) previousStatus[jobId] = data.record.status;
            })
            .catch(function (err) {
                setLoading(false);
                detailContent.innerHTML = '<p class="sev-high">加载失败：' + escapeHtml(err.message) + '</p>' +
                    '<p class="muted">可改用右侧操作链接直接跳转 Session 页。</p>';
            });
    }

    // 本地 Session：内联加载最新 session 的评论，不跳转 /r/ 页面
    function selectLocalSession(item, opts) {
        opts = opts || {};
        var encoded = item.getAttribute("data-encoded-repo");
        var sessionId = item.getAttribute("data-session-id");
        var displayName = item.getAttribute("data-display-name") || encoded;
        if (!encoded || !sessionId) return;

        selectedJobId = null;
        selectedLocalKey = encoded + "/" + sessionId;

        clearSelection();
        item.classList.add("selected");

        detailEmpty.hidden = true;
        detailContent.hidden = false;
        if (!opts.silent) {
            setLoading(true);
            detailContent.innerHTML = '<p class="muted">加载中…</p>';
        }

        var url = "/api/repos/" + encodeURIComponent(encoded) + "/sessions/" + encodeURIComponent(sessionId);
        fetch(url, { headers: { "Accept": "application/json" } })
            .then(function (resp) {
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                return resp.json();
            })
            .then(function (data) {
                setLoading(false);
                var record = data.record || {
                    mr_label: "📁 " + displayName,
                    project_path: "本地 Session",
                    status: "success",
                    high: num((data.session && data.session.severity && data.session.severity.HIGH) || 0),
                    medium: num((data.session && data.session.severity && data.session.severity.MEDIUM) || 0),
                    low: num((data.session && data.session.severity && data.session.severity.LOW) || 0),
                    comment_count: num(data.session && data.session.comment_total),
                    total_tokens_fmt: "—",
                    session_url: "/r/" + encodeURIComponent(encoded) + "/" + encodeURIComponent(sessionId),
                    mr_url: "",
                    mr_history_url: "",
                    encoded_repo: encoded,
                    session_id: sessionId,
                };
                renderDetail({ record: record, session: data.session });
            })
            .catch(function (err) {
                setLoading(false);
                detailContent.innerHTML = '<p class="sev-high">加载失败：' + escapeHtml(err.message) + '</p>';
            });
    }

    // 局部刷新列表：仅重建 #mrList，保留选中态与详情面板（修复整页 reload 清空阅读位置的问题）
    function rebindList(items) {
        if (!mrList) return;
        if (!items || !items.length) {
            mrList.innerHTML = emptyHintHtml();
            return;
        }
        mrList.innerHTML = items.map(buildItemHtml).join("");

        // 选中项状态从 running/queued 变为终态时，刷新详情以展示最终评论
        if (selectedJobId) {
            var row = null;
            for (var i = 0; i < items.length; i++) {
                if (items[i].job_id === selectedJobId) { row = items[i]; break; }
            }
            var prev = previousStatus[selectedJobId];
            if (row && prev && prev !== row.status &&
                (prev === "running" || prev === "queued")) {
                var itemEl = findItemByJob(selectedJobId);
                if (itemEl) selectMr(itemEl, { silent: true });
            }
            if (row) previousStatus[selectedJobId] = row.status;
        }
    }

    function refreshList() {
        // 复用当前页的 q/highlight 等查询参数
        var url = "/api/reviews" + window.location.search;
        return fetch(url, { headers: { "Accept": "application/json" } })
            .then(function (resp) { return resp.json(); })
            .then(function (data) { rebindList(data.items); })
            .catch(function () { /* 静默失败，等待下一次轮询 */ });
    }

    if (mrList) {
        mrList.addEventListener("click", function (e) {
            var item = e.target.closest(".mr-item[data-job-id]");
            if (item) selectMr(item);
        });
        mrList.addEventListener("keydown", function (e) {
            if (e.key !== "Enter" && e.key !== " ") return;
            var item = e.target.closest(".mr-item[data-job-id]");
            if (item) {
                e.preventDefault();
                selectMr(item);
            }
        });

        // 默认选中第一条 MR（跳过本地 Session 项与空提示），避免详情区一直空白
        var first = mrList.querySelector(".mr-item[data-job-id]");
        if (first) selectMr(first);
    }

    if (localList) {
        localList.addEventListener("click", function (e) {
            var item = e.target.closest(".mr-item-local");
            if (item) selectLocalSession(item);
        });
        localList.addEventListener("keydown", function (e) {
            if (e.key !== "Enter" && e.key !== " ") return;
            var item = e.target.closest(".mr-item-local");
            if (item) {
                e.preventDefault();
                selectLocalSession(item);
            }
        });
    }

    // 运行中/排队中 job 自动局部刷新（每 10s，仅当存在此类 job 时启用）
    function hasActiveJobs() {
        return mrList && mrList.querySelector('.mr-item[data-status="running"], .mr-item[data-status="queued"]');
    }

    function startAutoRefresh() {
        if (refreshTimer) return;
        if (autoRefreshHint) autoRefreshHint.hidden = false;
        refreshTimer = setInterval(function () {
            if (!hasActiveJobs()) {
                stopAutoRefresh();
                return;
            }
            refreshList();
        }, 10000);
    }

    function stopAutoRefresh() {
        if (refreshTimer) {
            clearInterval(refreshTimer);
            refreshTimer = null;
        }
        if (autoRefreshHint) autoRefreshHint.hidden = true;
    }

    if (hasActiveJobs()) startAutoRefresh();
})();
