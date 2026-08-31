# 策舟 StratArk · Backend

<p align="center">
  <strong>AI 加密资产量化交易平台 · 后端</strong>
  <br />
  FastAPI + ViewModel 三层架构 · SQLAlchemy 2.0（异步）+ PostgreSQL · Redis · JWT。
  封装 Freqtrade 执行引擎与 TradingAgents 投研引擎，统一权限、配置、任务、风控、审计与计费中台。
</p>

## 目录

- [快速开始](#快速开始)
- [账号与种子数据](#账号与种子数据)
- [项目结构](#项目结构)
- [业务域与 API 模块](#业务域与-api-模块)
- [核心能力](#核心能力)
- [外部集成](#外部集成)
- [技术栈](#技术栈)
- [环境变量](#环境变量)
- [文档与部署](#文档与部署)

## 快速开始

### 方式一：Docker Compose（推荐，一键全栈）

在后端仓库根目录（`strat-ark-backend/`，含 `docker-compose.yml`）执行：

```sh
docker compose up -d --build
docker compose exec backend python -m scripts.seed   # 幂等补齐系统目录与内置策略
```

- 前端：<http://localhost:3000>
- 后端 API 文档：<http://localhost:8000/docs>

> 生产编排包含 Freqtrade 执行引擎与 TradingAgents API 服务，见[文档与部署](#文档与部署)。

### 方式二：本地开发

环境要求：Python 3.13+、Poetry、PostgreSQL（驱动固定 `postgresql+psycopg://`）、Redis。

```sh
poetry install
cp .env.example .env            # 至少填写 DATABASE_URL / JWT_SECRET_KEY
poetry run alembic upgrade head
poetry run python -m scripts.seed                       # 系统目录 + 内置策略（幂等）
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> Alembic 是现有数据库 schema 演进与目录数据迁移的唯一通道；应用启动的 `init_db()` 仅为空库兜底建表，不替代迁移。

### 质量门禁

```sh
poetry run ruff check .
poetry run python -m unittest discover -s tests -v
```

`tests/test_platform_contract.py` 是无外部依赖的 smoke contract：不触发 lifespan，不要求 PostgreSQL / Redis 在线；用于验证 FastAPI app 可导入、平台核心模块路由已注册、REST 路径无 `/search` / `/list` / `/create` 反模式、OpenAPI 可生成以及 JWT 角色解析可用。

## 账号与种子数据

`scripts/seed` 只幂等补齐套餐目录、引擎注册表和平台内置策略，不创建账号，也不写入演示密码。账号统一走注册流程创建。

管理员由 `ADMIN_EMAIL_SUFFIXES` 判定；仅应配置组织实际控制的邮箱域名。引擎管理与审计日志接口在后端强制管理员鉴权。

## 项目结构

```text
strat-ark-backend/
├── api/            # 路由层（仅参数映射）：auth/common + dashboard/navigation/exchanges/
│                   #   bots/strategies/backtests/signals/ai/risk/trades/market/
│                   #   notification/engine/audit/subscription/settings/user_center
├── forms/          # 请求表单（ApiFormModel + Body(embed)，camelCase）
├── responses/      # 响应模型（ApiResponseModel + Field，camelCase）
├── view_models/    # 业务逻辑（BaseViewModel，async with 生命周期，before()）
├── models/         # SQLAlchemy ORM（29 张表，__init__ 聚合触发建表）
├── libs/
│   ├── auth/       # JWT 签发/校验、PermissionChecker
│   ├── audit/      # 平台审计（上下文 + 链式签名持久化服务）
│   ├── ctrl/       # db（SQLAlchemy / Redis）、cloud（OSS）
│   ├── integrations/  # 外部集成（见下）
│   ├── handler/    # 全局异常处理
│   └── response.py # 统一响应模型与状态码
├── configs/        # pydantic-settings 配置
├── scripts/seed.py # 系统目录 + 内置策略（幂等，不创建账号）
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
| 引擎 engine（管理员） | Engine Management | 服务连接状态 / 依赖 / 日志 / 连接 / 配置 / 运维操作（危险操作写审计） |
| 审计 audit（管理员） | Audit Log | 列表筛选 / 详情 / 链式签名校验 / 导出 |
| 订阅 subscription | Pricing / 套餐与用量 | 套餐目录 / 当前订阅 / Stripe Checkout / 用量 / 账单发票 |
| 设置 settings | Settings | General / LLM 网关 / Prompt 模板 / 外观 / 数据 |
| 用户中心 user_center | User Center | 平台 API Key / 第三方账号绑定 / 活跃会话 / 2FA |
| 仪表盘 dashboard | Dashboard | 首屏聚合：账户概览 / 风险 / 指标 / AI 摘要 / 机器人 / 信号 / 持仓 |
| 导航 navigation | 应用骨架 | 侧栏徽标计数（待处理信号 / 运行中机器人 / 未读通知）|

共 29 张表、141 条路由（19 业务域，另含 `common` 健康检查 / OSS 直传）；完整端点见 `/docs`。

## 核心能力

- **ViewModel 三层**：路由（参数映射）→ ViewModel（`async with` 生命周期，`before()`）→ 统一响应。
- **JWT 鉴权 + OAuth 登录**：access/refresh 双 token；Google / Microsoft 授权码后端 exchange；引擎管理与审计日志仅管理员。
- **平台审计**：append-only + sha256 链式签名（可校验、不可篡改），危险运维操作自动留痕。
- **订阅计费**：套餐 / 用量 / 账单；付费切换走 Stripe Checkout，订阅激活与发票以 Stripe Webhook 为准，集成边界见 [`docs/Stripe订阅计费架构.md`](docs/Stripe订阅计费架构.md)。
- **统一响应契约 + 全局异常处理**：`operating_successfully` / `not_found` / `forbidden` 等；401/403/422/500 收敛为业务响应。
- **OSS 直传**：`/common/oss/presign` + `/common/oss/confirm`，目录和扩展名白名单校验后再签发 PUT URL。
- **前后端契约**：前端 `src/api` + `src/types` 与后端 `forms/` `responses/` 逐字段对齐（19 域 / 141 路由），权威映射见 [`docs/前后端接口契约.md`](docs/前后端接口契约.md)；`tests/test_platform_contract.py` 守护路由注册与 REST 规范。

## 外部集成

`libs/integrations/*` 按外部能力分层封装；缺少真实上游配置时返回空结果或明确失败，不制造演示成功数据。已涵盖：

- `exchange` / `freqtrade`（交易所 REST、Bot 编排与实例 REST）
- `trading_agents` / `backtest_engine`（多智能体投研、真实行情回测）
- `market_data` / `notifier`（行情、多渠道通知发送）
- `billing` / `data_ops`（Stripe 订阅计费、数据导出与 LLM 网关测试）

配置外部服务时，在管理员引擎管理中维护 Freqtrade /
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
| 业务敏感数据加密 | `ENCRYPT_KEY` | 交易所和网关密钥入库加密；必须持久化并在所有实例保持一致，生产缺失时拒绝启动 |
| 阿里云 OSS | `ALI_OSS_*`、`BRAND_LOGO_OSS_PATH` | 文件上传和邮件 logo 公开地址；上传目录规则在 `libs/upload_rules.py` |
| SMTP 邮件 | `SMTP_*` | 邮件验证码发送 |
| 行情数据源 | `MARKET_DATA_*` | 行情 REST / WS 数据源，默认 Binance 公共行情 |
| 静态资源 | `STATIC_*` | 本地静态资源目录和访问前缀 |

引擎连接配置不走后端全局环境变量。Freqtrade、TradingAgents、模型网关等服务地址、
Token、API Key 和模型参数由管理员在引擎管理中维护，敏感字段 Fernet 加密入库并只回显掩码。

通知渠道配置不走全局环境变量。Email、Telegram、Lark、Slack、Webhook、SMS、App Push
等渠道的端点和凭证由用户在通知中心维护，后端按 `user_id + channel_kind` 独立入库；
Bot Token、Webhook 地址等敏感字段 Fernet 加密入库并只回显掩码。

## 文档与部署

- API 文档：`/docs`（Swagger）、`/redoc`
- 容器编排（后端仓库根目录，base / Freqtrade 引擎 / 生产 override 三份）：
  - `docker-compose.yml` — base：PostgreSQL + Redis + 后端 + 前端；外部集成未配置时返回空结果或明确失败；本地 `docker compose up -d --build`
  - `docker-compose.engines.yml` — Freqtrade 执行引擎编排器；编排器持有宿主 Docker 控制权限，必须运行在专用受控主机。可单独启动：`docker compose -f docker-compose.engines.yml up -d`
  - `docker-compose.prod.yml` — 生产 override：Gunicorn 多 worker、真实依赖健康检查、日志轮转，并要求显式设置生产镜像引用；`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- 主机部署：[`deploy/README.md`](deploy/README.md)（systemd + Poetry）

## 联系方式

Felix Liu - felixliuyj@gmail.com
