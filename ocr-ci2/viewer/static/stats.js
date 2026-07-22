/* 统计概览页图表渲染（方案 A）
 *
 * 优先使用 Chart.js（CDN）渲染柱状/折线；CDN 不可达（内网离线）时
 * 降级为纯 CSS 柱状图，避免出现空 canvas。数据由模板内 #statsData 提供（SSR 注入）。
 */
(function () {
    "use strict";

    function escapeHtml(text) {
        if (text === null || text === undefined) return "";
        return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function num(v) { var n = Number(v); return isNaN(n) ? 0 : n; }

    function getOverview() {
        var el = document.getElementById("statsData");
        if (!el) return {};
        try {
            return JSON.parse(el.textContent || "{}");
        } catch (e) {
            return {};
        }
    }

    // 纯 CSS 柱状降级：隐藏 canvas，在 .chart-card 内追加柱状容器
    function renderCssBars(canvasId, daily, metric, color) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;
        var card = canvas.closest(".chart-card");
        if (!card) return;
        canvas.style.display = "none";
        var max = 0;
        daily.forEach(function (d) { max = Math.max(max, num(d[metric])); });
        var html = '<div class="css-chart"><div class="css-bars">';
        daily.forEach(function (d) {
            var v = num(d[metric]);
            var pct = max > 0 ? Math.max(2, (v / max) * 100) : 0;
            html += '<div class="css-bar-col" title="' + escapeHtml(d.date) + ': ' + v + '">';
            html += '<div class="css-bar" style="height:' + pct + '%;background:' + color + '"></div>';
            html += '<span class="css-bar-val">' + v + '</span>';
            html += '</div>';
        });
        html += '</div></div>';
        card.insertAdjacentHTML("beforeend", html);
        var fb = card.querySelector(".chart-fallback");
        if (fb) fb.hidden = false;
    }

    function init() {
        var overview = getOverview();
        var daily = overview.daily || [];

        if (typeof Chart === "undefined") {
            // CDN 不可达：纯 CSS 降级
            renderCssBars("chartReviews", daily, "reviews", "rgba(9,105,218,0.7)");
            renderCssBars("chartTokens", daily, "median_tokens", "rgba(9,105,218,0.7)");
            return;
        }

        var labels = daily.map(function (d) { return d.date; });
        var reviews = daily.map(function (d) { return num(d.reviews); });
        var highs = daily.map(function (d) { return num(d.high); });
        var tokens = daily.map(function (d) { return num(d.median_tokens); });

        var reviewsCanvas = document.getElementById("chartReviews");
        if (reviewsCanvas) {
            // 横向日期轴：柱体向上，日期从左到右，宽窗口可左右滑动查看
            var minWidth = Math.max(640, labels.length * 28);
            reviewsCanvas.style.minWidth = minWidth + "px";
            reviewsCanvas.parentElement.style.minWidth = minWidth + "px";
            new Chart(reviewsCanvas, {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: [
                        { label: "评审数", data: reviews, backgroundColor: "rgba(9,105,218,0.6)" },
                        { label: "HIGH", data: highs, backgroundColor: "rgba(192,52,29,0.6)" },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { ticks: { maxRotation: 45, minRotation: 45 } },
                        y: { beginAtZero: true, ticks: { precision: 0 } },
                    },
                    plugins: { legend: { position: "bottom" } },
                },
            });
        }

        var tokensCanvas = document.getElementById("chartTokens");
        if (tokensCanvas) {
            var tokenMinWidth = Math.max(480, labels.length * 20);
            tokensCanvas.style.minWidth = tokenMinWidth + "px";
            tokensCanvas.parentElement.style.minWidth = tokenMinWidth + "px";
            new Chart(tokensCanvas, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [
                        { label: "Token 中位数", data: tokens, borderColor: "#0969da", backgroundColor: "rgba(9,105,218,0.1)", fill: true, tension: 0.2 },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { ticks: { maxRotation: 45, minRotation: 45 } },
                        y: { beginAtZero: true },
                    },
                    plugins: { legend: { position: "bottom" } },
                },
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
