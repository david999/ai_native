# 国内手机（华为 / 安卓）快速访问 GitHub

> **适用场景**：在 Cursor Cloud 等云端开发流程中，需要用手机随时查看 GitHub 上的 PR、Issue、Checks、Agent 评论与通知；本文只收录**当前仍可持续使用**的方案，并明确排除常见但已失效或高风险的「加速」做法。

## 1. 先搞清楚你要访问什么

| 需求 | 手机端典型操作 | 对网络的要求 |
|------|----------------|--------------|
| 看 PR / Issue / 评论 / Checks | 浏览器或 GitHub App 打开网页 | 需能稳定访问 `github.com` 及静态资源域名 |
| 收 Cursor / GitHub 通知 | 邮件 App、GitHub App 推送 | 推送走 FCM/系统通道；**点开链接**仍要能上 GitHub |
| 在手机上 `git clone` / `push` | Termux + git、或桌面远程 | 需要稳定代理 + 正确 DNS，且**不要**走第三方镜像登录 |

Cursor Cloud 场景下，**90% 只需「可靠打开 GitHub 网页」**，不必在手机上折腾 `git clone` 或公益镜像。

---

## 2. 方案筛选结论（先看这张表）

| 方案 | 结论 | 说明 |
|------|------|------|
| **规则分流代理（Clash Meta / sing-box 等）+ 自建或可信订阅节点** | ✅ **首选** | 2025–2026 国内最稳定；可只代理 GitHub/Google，国内直连 |
| **GitHub 官方 App + 上述代理** | ✅ **推荐** | 与网页同源，适合扫 PR、看通知 |
| **手机浏览器 + 系统/VPN 隧道代理** | ✅ 可用 | 与 App 等价；注意华为后台杀进程 |
| **加密 DNS（DoH/DoT）单独使用** | ⚠️ 仅辅助 | 可缓解 DNS 污染，**无法**解决 IP 层封锁；不要当唯一方案 |
| **公益 URL 镜像（ghproxy、gitclone、ghfast 等）** | ❌ 不推荐 | 随时停服/换域名；**禁止**在镜像站登录（令牌泄露风险） |
| **FastGit / hub.fastgit.\*** | ❌ 已失效 | 项目已长期不可用，教程过时 |
| **仅改 hosts（GitHub520 等）** | ❌ 不可靠 | 多数运营商已 IP 封锁；手机改 hosts 也麻烦 |
| **应用商店「免费翻墙 VPN」** | ❌ 高风险 | 易劫持流量、植入广告；不适合登录 GitHub |
| **码云 / Gitee 导入再浏览** | ⚠️ 仅只读备份 | 看不到 GitHub 原生 PR 讨论，**不适合** Cursor Cloud 工作流 |
| **dev-sidecar、桌面 hosts 工具** | — 不适用手机 | 适合 Windows/macOS 开发机，见下文「与开发机分工」 |

---

## 3. 推荐方案 A：规则分流代理（最稳、最适合开发者）

### 3.1 原理（为何比「改 hosts / 镜像」靠谱）

国内访问 GitHub 常见问题是：

1. **DNS 污染**（解析到错误 IP）
2. **IP 层干扰**（连接超时、TLS 中断）

仅改 hosts 或换 DNS **往往不够**；需要让 GitHub 相关流量走**加密代理隧道**，并由客户端用**规则**决定哪些域名走代理、哪些直连国内。

现代节点协议中，**VLESS + Reality**、**Hysteria2** 等在弱网/高干扰环境下通常比老旧 OpenVPN、裸 WireGuard 更耐干扰（具体取决于你的节点提供商与本地运营商）。

### 3.2 客户端选择（安卓 / 华为）

| 客户端 | 包名 / 来源 | 适用 |
|--------|-------------|------|
| [Clash Meta for Android](https://github.com/MetaCubeX/ClashMetaForAndroid/releases) | `com.github.metacubex.clash.meta` | 国行华为安卓、可侧载 APK 的机型 |
| [sing-box for Android](https://github.com/SagerNet/sing-box/releases) | 官方 sing-box 系 | 与 CMFA 类似，规则灵活 |
| 鸿蒙手机（HarmonyOS） | 通过 **卓易通** 安装上述 Android APK，或使用鸿蒙原生代理类应用 | 需额外注意后台保活（见 3.4） |

**安装建议**：

- 优先从 **GitHub Releases** 或 **F-Droid** 获取 APK，避免来路不明的「破解整合版」。
- 架构选 **arm64-v8a**（近年华为机型）；不确定时用 universal 包。

### 3.3 最小可用配置思路

你需要一份**可信的订阅或自建节点**（本文不列举商业机场；请自行选择合规、口碑稳定的服务）。

配置要点：

1. **模式**：使用「规则 / Rule」而非「全局」，避免国内 App、银行、政务站点误走代理。
2. **规则集**：确保至少包含 `github.com`、`api.github.com`、`raw.githubusercontent.com`、`objects.githubusercontent.com`、`codeload.github.com`、`github.githubassets.com`、`avatars.githubusercontent.com` 等走代理（常用 Loyalsoldier / ACL4SSR 等规则集已覆盖）。
3. **DNS**：在代理内核内做 **fake-ip 或 redir-host**，不要让系统 DNS 先返回污染结果；**不要**只对 GitHub 开系统 DoH 却走直连。
4. **验证**：连接代理后，用手机浏览器打开 <https://github.com> 与任意公开仓库 README；再打开一个 PR 页面确认图片与 Checks 能加载。

### 3.4 华为 / 鸿蒙必做：后台与省电

华为系系统 aggressively 杀后台，会导致「刚还能上 GitHub，切换 App 就断」。

请在 **设置 → 应用 → [你的代理 App]** 中逐项确认：

- 允许**自启动**、**关联启动**
- 耗电管理选 **不允许限制** / **完全允许后台活动**
- 若有「智能省电」「应用启动管理」，对该 App 选手动允许全部后台权限
- 将代理 App 加入**锁定任务**（多任务界面下拉锁定）

鸿蒙通过卓易通安装的 Android 代理 App，同样需要在卓易通与系统两处放开后台。

### 3.5 与 GitHub 登录安全

- 只在 **`https://github.com`** 或 **官方 GitHub App** 内登录。
- 开启 **2FA**；优先 Passkey / TOTP。
- **切勿**在第三方镜像站的登录页输入 GitHub 账号或 PAT。

---

## 4. 推荐方案 B：GitHub App + 通知（Cursor Cloud 增效）

在方案 A 的网络环境下：

1. 安装 **GitHub** 官方 App（华为应用市场可能没有，需 APK 侧载或通过代理访问 Play 获取）。
2. 登录后打开 **Watch / 自定义通知**，关注 Cloud Agent 或 CI 所在的仓库与 PR。
3. 将 Cursor / GitHub 邮件通知设为「仅重要」，减少噪音；需要时点通知深链到 PR。

**快捷路径**：在桌面端复制 PR URL，发到「文件传输助手」或备忘录，手机点链接即可（仍需方案 A 的网络）。

---

## 5. 辅助手段（可叠加，不能替代代理）

| 手段 | 作用 | 局限 |
|------|------|------|
| 浏览器 DoH（Chrome / Edge / Firefox） | 降低 DNS 污染 | 不解决 IP 封锁 |
| 阿里云公共 DNS `223.5.5.5` 等 | 国内解析更稳 | 对 GitHub 帮助有限 |
| 公司 / 家宽已有代理 | 手机 Wi‑Fi 下可能直连公司 PAC | 离开局域网需另配手机代理 |

---

## 6. 明确不推荐的方案（及原因）

### 6.1 公益 GitHub 镜像 / `git config url.insteadOf`

- 适合**匿名只读 clone**，不适合**登录、看私有仓、PR 评审**。
- 镜像运营方可见流量，存在**凭据钓鱼**历史案例与社区共识风险。
- 域名频繁更换、停服（如 ghproxy 主域、FastGit 等），**不能**作为 Cursor Cloud 日常依赖。

### 6.2 仅 hosts（GitHub520 等）

- 维护成本高，IP 变更快；在不少省份/运营商已与 IP 封锁叠加，**实测经常完全无效**。
- Android 改 hosts 通常要 root 或 VPN 类 App，不如直接用规则代理干净。

### 6.3 应用商店「一键科学上网」

- 来源不明、协议过时、易泄露浏览与账号数据；**不要**用于 GitHub 登录。

### 6.4 为 GitHub 单独装 GMS（华为鸿蒙教程）

- 解决的是 Google 服务与 Play，**不是**访问 GitHub 的必要条件；成本高、系统升级风险大，与本文目标无关。

---

## 7. 与开发机 / Cursor Cloud 的分工

| 环境 | 建议 |
|------|------|
| **Cursor Cloud Agent（Linux VM）** | 云端一般可直接访问 GitHub；问题多在**你本地/手机网络** |
| **家里 Windows / macOS** | 可用 [dev-sidecar](https://github.com/docmirror/dev-sidecar) 等本地 HTTPS 代理，浏览器 + git 一体；配置见项目文档 |
| **手机** | 用 **方案 A + GitHub App**，不要复用桌面上的 `git config insteadOf` 镜像 |

在手机上偶尔需要 git 时，应通过 **Termux + 与 Clash 相同的本地 HTTP/SOCKS 端口**（如 `127.0.0.1:7890`），且仅对 `github.com` 设置代理，**不要**把 token 交给第三方镜像。

---

## 8. 推荐的一次性搭建流程（约 15–30 分钟）

```text
1. 准备可信节点订阅（自建或付费服务，支持 Clash/sing-box 配置）
2. 安装 Clash Meta for Android（或 sing-box），导入订阅
3. 模式选「规则」，打开 TUN/系统代理（按客户端说明）
4. 华为/鸿蒙：放开后台与自启动
5. 浏览器验证 github.com → 安装/登录 GitHub App → 打开目标仓库通知
6. （可选）桌面端 Watch 同一 PR，手机只负责审批与看 CI
```

**日常习惯**：需要看 PR 时先确认代理已连接（状态栏图标 / 客户端前台服务），再点开链接，避免「半开网页」导致误判为 GitHub 宕机。

---

## 9. 故障排查

| 现象 | 优先检查 |
|------|----------|
| 网页白屏 / 图片裂图 | 规则是否包含 `github.githubassets.com`、`avatars.githubusercontent.com` |
| 仅浏览器不行，其他 App 正常 | 浏览器是否走了「直连」；关闭「省流/WLAN+ 智能切换」 |
| 一会儿能上一会儿不行 | 华为后台杀代理；节点质量；换 Hysteria2 / Reality 节点测试 |
| `git` / Termux 超时 | Termux 是否配置 `http.proxy`；代理本地端口是否与客户端一致 |
| 私有仓 401 / 403 | 与网络无关，检查 PAT 权限与 SSO 授权 |

---

## 10. 合规与风险说明

- 请遵守当地法律法规与所在单位网络政策；本文仅描述**技术层面**的常见做法。
- 代理订阅来源请自行甄别，避免使用来路不明的「免费节点」处理含公司代码的私有仓库。
- **不要在第三方网页输入 GitHub 密码或 Fine-grained PAT。**

---

## 11. 相关链接

- Clash Meta for Android：<https://github.com/MetaCubeX/ClashMetaForAndroid>
- sing-box：<https://github.com/SagerNet/sing-box>
- GitHub 官方移动 App：<https://github.com/mobile>
- 本仓库 Cursor Cloud 开发说明：[AGENTS.md](../AGENTS.md)
