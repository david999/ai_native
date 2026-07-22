<template>
  <div class="app">
    <nav class="topnav">
      <div class="brand">
        <strong>OCR Gateway</strong>
        <span class="tag">Code Review Dashboard</span>
      </div>
      <div class="links">
        <router-link to="/">MR 列表</router-link>
      </div>
    </nav>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<style>
* { box-sizing: border-box; }
.app { min-height: 100vh; background: #0d1117; color: #c9d1d9; }
.topnav {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; background: #161b22; border-bottom: 1px solid #30363d;
}
.brand { display: flex; align-items: center; gap: 10px; }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: #238636; color: #fff; }
.links { display: flex; gap: 16px; }
.links a { color: #58a6ff; text-decoration: none; font-size: 14px; }
.links a:hover { text-decoration: underline; }
.main { padding: 24px; }
.muted { color: #8b949e; }
</style>
