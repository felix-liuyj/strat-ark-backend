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

> 含 Freqtrade / TradingAgents 两个引擎的生产编排，见[文档与部署](#文档与部署)。

### 方式二：本地开发

环境要求：Python 3.13+、Poetry、PostgreSQL（驱动固定 `postgresql+psycopg://`）、Redis。

```sh
poetry install
cp .env.example .env            # 至少填写 DATABASE_URL / JWT_SECRET_KEY
poetry run python -m scripts.seed                       # 建表 + 演示种子（幂等）
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> 表结构在应用启动（lifespan `init_db`）时自动创建（多 worker 用 PG advisory lock 串行化），无需手动迁移。

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
├── models/         # SQLAlchemy ORM（28 张表，__init__ 聚合触发建表）
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
| 认证 auth | 登录 / 用户中心 | 注册 / 登录 / 验证码 / 双 token 刷新 / 资料 / 管理员用户列表 |
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

共 28 张表、110 条路由；完整端点见 `/docs`。

## 核心能力

- **ViewModel 三层**：路由（参数映射）→ ViewModel（`async with` 生命周期，`before()`）→ 统一响应。
- **JWT 鉴权 + 角色 gating**：access/refresh 双 token；引擎管理与审计日志仅管理员。
- **平台审计**：append-only + sha256 链式签名（可校验、不可篡改），危险运维操作自动留痕。
- **订阅计费（模拟）**：套餐 / 用量 / 账单；升级降级取消仅更新本地订阅与 `users.plan`，**绝不接入真实支付**。
- **统一响应契约 + 全局异常处理**：`operating_successfully` / `not_found` / `forbidden` 等；401/403/422/500 收敛为业务响应。
- **OSS 直传**：预签名 PUT + confirm 设置 ACL。

## 外部集成（stub）

`libs/integrations/*` 以接口 stub 实现，返回**拟真 mock 数据**，函数签名为真实接入预留；留空相关配置即用 mock，不影响本地运行与演示。已涵盖：

- `exchange` / `freqtrade`（交易所 REST、Bot 编排与容器）
- `trading_agents` / `agent` / `backtest_engine`（多智能体投研、回测引擎）
- `market_data` / `trading` / `risk_engine`（行情、交易记录、风控评估）
- `kubernetes` / `notifier`（引擎集群运维、多渠道通知发送）
- `billing` / `data_ops` / `oauth`（订阅计费、数据导出、第三方绑定）

接入真实服务时，替换对应 stub 实现并填写 `.env` 中的集成配置；其中 **Freqtrade 执行引擎**（`FREQTRADE_ORCHESTRATOR_URL` / `FREQTRADE_API_TOKEN`）与 **TradingAgents 投研引擎**（`TRADINGAGENTS_API_URL` + `LLM_*`）已在生产编排 `docker-compose.prod.yml` 中作为独立服务接入，后端通过编排内网（`http://freqtrade:8080` / `http://tradingagents:8100`）连接。

## 技术栈

FastAPI · Uvicorn · Pydantic v2 · SQLAlchemy 2.0（异步）· PostgreSQL（psycopg）· Redis · PyJWT · bcrypt · aiosmtplib · Jinja2 · 阿里云 OSS。

## 环境变量

见 [`.env.example`](.env.example)。关键项：`DATABASE_URL`、`DATABASE_SCHEMA`、`REDIS_*`、`JWT_SECRET_KEY`、`ADMIN_EMAIL_SUFFIXES`、`CORS_ORIGINS`；外部集成项（`FREQTRADE_*` / `TRADINGAGENTS_*` / `LLM_*` / `MARKET_DATA_*` / `K8S_*` / 渠道令牌）留空即用 stub。

## 文档与部署

- API 文档：`/docs`（Swagger）、`/redoc`
- 容器编排（仓库根目录，base + 生产 override 两份）：
  - `docker-compose.yml` — base：PostgreSQL + Redis + 后端 + 前端，引擎连接留空走 stub；本地 `docker compose up -d --build`
  - `docker-compose.prod.yml` — 生产 override：叠加 **Freqtrade 执行引擎** 与 **TradingAgents 投研引擎** 两个服务，并补齐 restart / healthcheck / 资源限制，敏感值走 `.env`；`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- 主机部署：[`deploy/README.md`](deploy/README.md)（systemd + Poetry）

## 联系方式

Felix Liu - felixliuyj@gmail.com
