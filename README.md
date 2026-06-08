# 策舟 StratArk · Backend

<p align="center">
  <strong>AI 加密资产量化交易平台 · 后端</strong>
  <br />
  FastAPI + ViewModel 三层架构 · SQLAlchemy 2.0（异步）+ PostgreSQL · Redis · JWT。
  封装 Freqtrade 执行引擎与 TradingAgents 投研引擎，统一权限、配置、任务、风控、审计与计费中台。
</p>

## 目录

- [快速开始](#快速开始)
- [演示账号](#演示账号)
- [项目结构](#项目结构)
- [业务域与 API 模块](#业务域与-api-模块)
- [核心能力](#核心能力)
- [外部集成（stub）](#外部集成stub)
- [技术栈](#技术栈)
- [环境变量](#环境变量)
- [文档与部署](#文档与部署)

## 快速开始

### 方式一：Docker Compose（推荐，一键全栈）

在仓库根目录（`strat-ark/`，含 `docker-compose.yml`）执行：

```sh
docker compose up -d --build
docker compose exec backend python -m scripts.seed   # 写入演示账号 + 内置策略
```

- 前端：<http://localhost:3000>
- 后端 API 文档：<http://localhost:8000/docs>

> 生产编排包含 Freqtrade 执行引擎与 TradingAgents API 服务，见[文档与部署](#文档与部署)。

### 方式二：本地开发

环境要求：Python 3.13+、Poetry、PostgreSQL（驱动固定 `postgresql+psycopg://`）、Redis。

```sh
poetry install
cp .env.example .env            # 至少填写 DATABASE_URL / JWT_SECRET_KEY
poetry run python -m scripts.seed                       # 建表 + 演示种子（幂等）
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> 表结构在应用启动（lifespan `init_db`）时自动创建（多 worker 用 PG advisory lock 串行化），无需手动迁移。

### 质量门禁

```sh
poetry run ruff check .
poetry run python -m unittest discover -s tests -v
```

`tests/test_platform_contract.py` 是无外部依赖的 smoke contract：不触发 lifespan，不要求 PostgreSQL / Redis 在线；用于验证 FastAPI app 可导入、平台核心模块路由已注册、REST 路径无 `/search` / `/list` / `/create` 反模式、OpenAPI 可生成以及 JWT 角色解析可用。

## 演示账号

`scripts/seed` 写入三个与前端 mock 对齐的角色账号（统一密码 `strategy123`）：

| 邮箱 | 角色 | 套餐 | 可见范围 |
|---|---|---|---|
| `alex@stratark.io` | 管理员 admin | Pro | 全部，含引擎管理 / 审计日志 |
| `wei@stratark.io` | 普通用户 | Free | 普通页面（无引擎 / 审计） |
| `lin@stratark.io` | 订阅用户 | Pro | 普通页面 + 订阅权益 |

> 管理员由 `ADMIN_EMAIL_SUFFIXES`（如 `stratark.io`）判定；引擎管理与审计日志接口在 ViewModel 内强制管理员鉴权。

## 项目结构

```text
strat-ark-backend/
├── api/            # 路由层（仅参数映射）：auth/common + exchanges/bots/strategies/
│                   #   backtests/signals/ai/risk/trades/market/notification/engine/
│                   #   audit/subscription/settings/user_center
├── forms/          # 请求表单（ApiFormModel + Body(embed)，camelCase）
├── responses/      # 响应模型（ApiResponseModel + Field，camelCase）
├── view_models/    # 业务逻辑（BaseViewModel，async with 生命周期，before()）
├── models/         # SQLAlchemy ORM（29 张表，__init__ 聚合触发建表）
├── libs/
│   ├── auth/       # JWT 签发/校验、PermissionChecker
│   ├── audit/      # 平台审计（上下文 + 链式签名持久化服务）
│   ├── ctrl/       # db（SQLAlchemy / Redis）、cloud（OSS）
│   ├── integrations/  # 外部集成 stub（见下）
│   ├── handler/    # 全局异常处理
│   └── response.py # 统一响应模型与状态码
├── configs/        # pydantic-settings 配置
├── scripts/seed.py # 建表 + 演示种子（幂等）
├── deploy/         # systemd + Poetry 部署
├── Dockerfile      # 后端镜像
└── main.py         # 应用入口
```

## 业务域与 API 模块

| 域 | 前端页面 | 关键能力 |
|---|---|---|
| 认证 auth | 登录 / 用户中心 | 注册 / 登录 / OAuth exchange / 验证码 / 双 token 刷新 / 资料 / 管理员用户列表 |
| 交易所 exchanges | Exchange Accounts | CRUD / 连接测试 / 同步余额 / 权限检查 / 设默认 |
| 机器人 bots | Bots / Bot Detail / Wizard | 列表 / 详情 / 创建向导 / 启停重启 / Live 强确认 / 交易 / 持仓 / 日志 / AI 摘要 |
| 策略 strategies | Strategy Lab | 列表（内置+私有）/ 详情 / 参数 / 版本 / 源码 / 风险标签 |
| 回测 backtests | Backtest Center | 创建任务 / 结果指标与曲线 / AI 复盘 |
| 信号 signals | Signal Center | 列表 / 状态机（批准/拒绝/执行）/ 手动创建 |
| AI 投研 ai | AI Research Room | 市场分析 / 信号复核 / 回测复盘 / 报告（八智能体结构化输出） |
| 风控 risk | Risk Center | 多层规则 / 触发记录 / 风险总览与评估 |
| 交易记录 trades | Trades | 交易 / 持仓 / 未完成订单 / 统计 / CSV 导出 |
| 行情 market | Market / Detail | 行情列表 / 涨跌榜 / 热力图 / 自选 / 单币种深度（K线/订单簿/成交/AI 快照） |
| 通知 notification | Notifications | 信息流 / 标记已读 / 事件×渠道矩阵 / 渠道配置（各类型）/ 发送测试 |
| 引擎 engine（管理员） | Engine Management | 监控 Pods/资源/依赖/日志 / 连接 / 配置 / 运维操作（危险操作写审计） |
| 审计 audit（管理员） | Audit Log | 列表筛选 / 详情 / 链式签名校验 / 导出 |
| 订阅 subscription | Pricing / 套餐与用量 | 套餐目录 / 当前订阅 / 切换（模拟）/ 用量 / 账单发票 |
| 设置 settings | Settings | General / LLM 网关 / Prompt 模板 / 外观 / 数据 |
| 用户中心 user_center | User Center | 平台 API Key / 第三方账号绑定 / 活跃会话 / 2FA |

共 29 张表、120+ 条路由；完整端点见 `/docs`。

## 核心能力

- **ViewModel 三层**：路由（参数映射）→ ViewModel（`async with` 生命周期，`before()`）→ 统一响应。
- **JWT 鉴权 + OAuth 登录**：access/refresh 双 token；Google / Microsoft 授权码后端 exchange；引擎管理与审计日志仅管理员。
- **平台审计**：append-only + sha256 链式签名（可校验、不可篡改），危险运维操作自动留痕。
- **订阅计费（模拟）**：套餐 / 用量 / 账单；升级降级取消仅更新本地订阅与 `users.plan`，**绝不接入真实支付**。
- **统一响应契约 + 全局异常处理**：`operating_successfully` / `not_found` / `forbidden` 等；401/403/422/500 收敛为业务响应。
- **OSS 直传**：`/common/oss/presign` + `/common/oss/confirm`，目录和扩展名白名单校验后再签发 PUT URL。

## 外部集成（stub）

`libs/integrations/*` 以接口 stub 实现，返回**拟真 mock 数据**，函数签名为真实接入预留；留空相关配置即用 mock，不影响本地运行与演示。已涵盖：

- `exchange` / `freqtrade`（交易所 REST、Bot 编排与容器）
- `trading_agents` / `agent` / `backtest_engine`（多智能体投研、回测引擎）
- `market_data` / `trading` / `risk_engine`（行情、交易记录、风控评估）
- `kubernetes` / `notifier`（引擎集群运维、多渠道通知发送）
- `billing` / `data_ops` / `oauth`（订阅计费、数据导出、用户中心第三方绑定）

接入真实服务时，替换对应 stub 实现，并在管理员引擎管理中维护 Freqtrade /
TradingAgents 的连接配置、凭证、服务地址与部署参数。后端 `.env` 不再作为引擎连接
参数的事实源；`docker-compose.engines.yml` 只负责 Freqtrade 服务编排，
`docker-compose.prod.yml` 只负责 TradingAgents API 服务启动。

## 技术栈

FastAPI · Uvicorn · Pydantic v2 · SQLAlchemy 2.0（异步）· PostgreSQL（psycopg）· Redis · PyJWT · bcrypt · aiosmtplib · Jinja2 · 阿里云 OSS。

## 环境变量

见 [`.env.example`](.env.example)。配置按用途分组维护，避免把不同类型的敏感值和服务地址堆在同一段：

| 分组 | 关键变量 | 说明 |
|---|---|---|
| 应用运行 | `APP_*` | 服务名、环境、监听地址和调试开关 |
| Web 跨域 | `CORS_ORIGINS` | 前端来源白名单 |
| 数据库 | `DATABASE_URL`、`DATABASE_SCHEMA` | PostgreSQL 连接与 schema |
| Redis | `REDIS_*` | 缓存与会话相关 Redis 连接 |
| JWT 与管理员 | `JWT_*`、`ADMIN_EMAIL_SUFFIXES` | 自家 session 与管理员邮箱后缀 |
| OAuth 登录 | `OAUTH_GOOGLE_CLIENT_ID`、`OAUTH_MICROSOFT_CLIENT_ID`、`OAUTH_MICROSOFT_TENANT` | Google / Microsoft Public PKCE 后端 exchange 与 id_token 校验 |
| 业务敏感数据加密 | `ENCRYPT_KEY` | 交易所和网关密钥入库加密，生产必须注入强随机值 |
| 阿里云 OSS | `ALI_OSS_*`、`BRAND_LOGO_OSS_PATH` | 文件上传和邮件 logo 公开地址；上传目录规则在 `libs/upload_rules.py` |
| SMTP 邮件 | `SMTP_*` | 邮件验证码发送 |
| 行情数据源 | `MARKET_DATA_*` | 行情 REST / WS 数据源，留空走 stub |
| Kubernetes 运维 | `K8S_*` | 引擎集群状态与运维配置 |
| 静态资源 | `STATIC_*` | 本地静态资源目录和访问前缀 |

引擎连接配置不走后端全局环境变量。Freqtrade、TradingAgents、模型网关等服务地址、
Token、API Key 和模型参数由管理员在引擎管理中维护，按引擎类型入库并回显掩码。

通知渠道配置不走全局环境变量。Email、Telegram、Lark、Slack、Webhook、SMS、App Push
等渠道的端点和凭证由用户在通知中心维护，后端按 `user_id + channel_kind` 独立入库并在
回显时掩码敏感字段。

## 文档与部署

- API 文档：`/docs`（Swagger）、`/redoc`
- 容器编排（仓库根目录，base / Freqtrade 引擎 / 生产 override 三份）：
  - `docker-compose.yml` — base：PostgreSQL + Redis + 后端 + 前端，引擎连接留空走 stub；本地 `docker compose up -d --build`
  - `docker-compose.engines.yml` — **Freqtrade 执行引擎独立编排**，已按生产全面加固（非 root / read_only / cap_drop / 日志轮转 / 资源 limits+reservations）；可单独启动：`docker compose -f docker-compose.engines.yml up -d`
  - `docker-compose.prod.yml` — 生产 override：主栈生产化，并经 `include` 自动引入 Freqtrade；TradingAgents 直接部署为 `tradingagents-api` API 服务；`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- 主机部署：[`deploy/README.md`](deploy/README.md)（systemd + Poetry）

## 联系方式

Felix Liu - felixliuyj@gmail.com
