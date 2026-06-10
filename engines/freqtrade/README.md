# Freqtrade 执行引擎配置

本目录是 Freqtrade 引擎 `user_data` 的版本化模板。StratArk 后端不直接部署
Freqtrade，而是通过其 REST API 操控（启停、重载、拉取交易与持仓、读日志）；
引擎的连接地址与凭证由「引擎管理」页经后端 API 写入数据库，部署细节由运维负责。

## 目录结构

```
engines/freqtrade/
├── README.md
└── user_data/
    ├── config.json                 # 生产最佳实现配置（本仓库维护）
    └── strategies/
        └── SampleStrategy.py       # 占位策略，真实策略由平台策略库下发
```

## 放置方式（二选一）

`docker-compose.engines.yml` 将命名卷 `freqtrade_userdata` 挂载到容器
`/freqtrade/user_data`，命令为 `--config /freqtrade/user_data/config.json
--strategy ${FREQTRADE_STRATEGY:-SampleStrategy}`。

1. 复制进命名卷（保持现有 compose 不变）：

   ```bash
   docker compose -f docker-compose.engines.yml up -d --no-start freqtrade
   docker cp engines/freqtrade/user_data/. \
     "$(docker compose -f docker-compose.engines.yml ps -q freqtrade)":/freqtrade/user_data/
   docker compose -f docker-compose.engines.yml up -d freqtrade
   ```

2. 或改为绑定挂载（可复现，便于版本管理）：在 `freqtrade` 服务下加

   ```yaml
   volumes:
     - ./engines/freqtrade/user_data:/freqtrade/user_data
   ```

   官方镜像内 `ftuser` uid 为 1000，首次创建的卷若属 root 需
   `chown -R 1000:1000`。

## 敏感值用环境变量注入（不写入 config.json）

Freqtrade 原生支持 `FREQTRADE__` 前缀、双下划线表示嵌套的环境变量覆盖。
`config.json` 中交易所与 `api_server` 凭证一律留空，由运行环境注入：

```bash
# 交易所密钥
FREQTRADE__EXCHANGE__KEY=...
FREQTRADE__EXCHANGE__SECRET=...

# REST API 凭证（StratArk 后端用它取 JWT）
FREQTRADE__API_SERVER__USERNAME=stratark
FREQTRADE__API_SERVER__PASSWORD=...
FREQTRADE__API_SERVER__JWT_SECRET_KEY=...
FREQTRADE__API_SERVER__WS_TOKEN=...
```

## 与后端控制面的联动

| config.json 段 | StratArk 引擎连接配置（`connection_config`） |
| --- | --- |
| `api_server.listen_port: 8080` | `serviceUrl: http://<host>:8080` |
| Freqtrade `/api/v1/ping` | `healthPath: /api/v1/ping` |
| `api_server.username` + `password` → `/api/v1/token/login` 取 JWT | `restApiToken`（掩码存储） |

后端流程：用 `username/password` 调 `POST /api/v1/token/login` 换取 JWT →
作为 `Authorization: Bearer <token>` 调用 `/api/v1/start`、`/api/v1/stop`、
`/api/v1/reload_config`、`/api/v1/trades`、`/api/v1/status`、`/api/v1/logs` 等。

## 安全默认

- `dry_run: true`：默认模拟盘，不下真实订单；实盘由后端 live-enable 流程切换。
- `initial_state: "stopped"`：容器起来后不自动交易，等后端 REST `/start` 显式拉起。
- `telegram.enabled: false`：通知统一走 StratArk 通知中心。
- `pair_blacklist`：屏蔽杠杆代币与稳定币对。
