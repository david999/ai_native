<template>
  <div class="app">
    <nav class="topnav">
      <div class="brand">
        <strong>OCR Gateway</strong>
        <span class="tag">SPA</span>
      </div>
      <div class="links">
        <router-link to="/">评审工作台</router-link>
        <router-link to="/stats">统计概览</router-link>
        <router-link to="/repos">仓库</router-link>
        <a href="/legacy/" title="方案 A HTMX 兜底">经典版</a>
      </div>
    </nav>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.topnav {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; background: var(--bg-elev); border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 10px; color: var(--text-strong); }
.tag {
  font-size: 11px; padding: 2px 8px; border-radius: 999px;
  background: var(--ok); color: #fff;
}
.links { display: flex; gap: 16px; align-items: center; }
.links a { color: var(--link); font-size: 14px; }
.links a.router-link-active { font-weight: 700; text-decoration: underline; }
.main { padding: 20px 24px; }
</style>
