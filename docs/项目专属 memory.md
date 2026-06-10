# StratArk 项目专属 memory

适用工作区：`/Users/felixliu/Documents/Projects/Personal Projects/Cambria Tech/strat-ark`

## 仓库边界

- 根目录不是 Git 仓库，不在根目录提交。
- 前端仓库：`strat-ark-frontend`，当前分支按实际 `git status -sb` 为准。
- 后端仓库：`strat-ark-backend`，当前分支按实际 `git status -sb` 为准。
- 修改完成后，如对应子项目存在 Git 仓库，必须在当前分支自动 commit 并 push；多仓库分别提交推送。

## 前端实现规则

- i18n 必须是语言隔离目录：`zh` 和 `en` 各自持有同一组共同 key。
- 禁止以中文文案作为源语言再映射英文；业务状态、筛选项、方向、风险、权限等都必须用稳定 token，再在渲染点映射 i18n key。
- 非 `src/i18n/locales/*.ts` 的源码中不应保留用户可见中文字符串；品牌字样和注释可以保留，但路由标题、表单默认值、套餐额度、select value 等必须使用稳定 key / token。
- 导航、订阅套餐、表格行等数据模型只保存结构、token 或 i18n key；不要保存中文 label 再让页面选择性忽略。
- `translate()` 缺失时应回退 key 本身，不跨语言目录兜底，以便暴露缺失翻译。
- 前端用户可见 icon 必须用内嵌 SVG，禁止字符图标、emoji、icon font、外链图标。
- 管理端角色可见性集中在权限层，管理员多出审计日志和引擎管理；普通用户和订阅用户隐藏这两个页面。
- 通知渠道设置按钮需要 hover 显示，点击后按 channel 类型打开匹配配置弹窗；当前前端 / 后端应覆盖 Web、Email、Telegram、Lark、Slack、Discord、Webhook、SMS、App Push。

## 当前清理重点

- 已重点修正 i18n 架构、Dashboard、Bots、Trades、Signals、订阅套餐、404 占位页、侧栏导航数据的 token 化和部分字符图标问题。
- 后端 contract 已补入 Strategy Versions 与 Backtest Result 路由；继续查漏时应从 `docs/平台开发计划.md` 的 API 清单反推 `tests/test_platform_contract.py`。
- 仍需滚动排查 Market、Market Detail、Bot Detail、AI Research、Engine Management 等页面中的硬编码方向文案、字符图标和展示值参与逻辑判断。
- 查漏补缺时优先扫描：`Long|Short|Neutral|●|▲|₿|Ξ|◎|→|←|—|import *`。

## 验证习惯

- 前端变更至少运行 `npm run typecheck`、`npm run build` 和 i18n key 完整性脚本。
- i18n 扫描需同时做两类：locale key parity；非 locale 源码中的中文字符串扫描，排除注释和品牌后处理所有真实 UI 文案。
- 后端平台路由变更至少运行 `poetry run ruff check .`、`poetry run python -m unittest discover -s tests -v`、`git diff --check`。
- UI 变更使用 Browser 插件优先回归目标页面；截图 API 如超时，可用 DOM、console、交互状态作为证据并明确说明。
- 回归重点：无 framework overlay、无相关 console error、无 i18n key 泄漏、目标交互真实改变页面状态。
