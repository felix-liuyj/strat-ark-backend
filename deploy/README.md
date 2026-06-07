# Linux 本地部署指南

## 前置条件

- Linux 系统（Ubuntu 20.04+ / CentOS 8+ / Debian 11+）
- root 或 sudo 权限
- 已安装 **Python 3.13+**，或可通过 `PYTHON_BIN` 显式指定满足版本要求的解释器
- 已安装 `curl`
- 已安装 `systemd`
- 已安装 `git` 或 `rsync`
- PostgreSQL 已安装并运行
- Redis 已安装并运行
- 部署脚本不再自动安装系统依赖，缺少运行命令时会直接报错退出
- 部署时不要使用位于 `/root` 下的 Python 解释器，例如 root 的 conda / pyenv 环境；默认使用 `/opt/python3.13/bin/python`
  ，也可通过 `PYTHON_BIN` 覆盖

## 快速部署

```bash
# 1. 克隆代码
git clone <YOUR_REPO_URL> strat-ark-backend
cd strat-ark-backend

# 2. 运行部署脚本（首次部署）
sudo bash deploy/deploy.sh

# 3. 编辑配置文件
sudo vim /opt/strat-ark-backend/.env

# 4. 重启服务使配置生效
sudo systemctl restart strat-ark-backend
```

## 环境变量

部署脚本支持以下环境变量自定义：

| 变量                   | 默认值                          | 说明                    |
|----------------------|------------------------------|-----------------------|
| `APP_NAME`           | `strat-ark-backend`          | 服务名（systemd 单元名）       |
| `APP_USER`           | `strat-ark`                  | 运行服务的系统用户             |
| `APP_DIR`            | `/opt/strat-ark-backend`     | 项目部署目录                |
| `REPO_URL`           | 空                            | Git 仓库地址（留空则复制本地代码）   |
| `PYTHON_MIN_VERSION` | `3.13`                       | 最低 Python 版本要求        |
| `PYTHON_BIN`         | `/opt/python3.13/bin/python` | 默认 Python 解释器路径，可显式覆盖 |
| `WORKERS`            | `4`                          | Gunicorn worker 数量    |
| `PORT`               | `8000`                       | 服务监听端口                |
| `POETRY_HOME`        | `/opt/poetry`                | Poetry 安装目录           |

示例：

```bash
sudo WORKERS=2 PORT=9000 bash deploy/deploy.sh
```

如果服务器上需要切换到其他 Python 解释器，可显式指定：

```bash
sudo PYTHON_BIN=/usr/bin/python3.13 bash deploy/deploy.sh
```

## 常用命令

```bash
# 查看服务状态
sudo systemctl status strat-ark-backend

# 查看实时日志
sudo journalctl -u strat-ark-backend -f

# 重启服务
sudo systemctl restart strat-ark-backend

# 停止服务
sudo systemctl stop strat-ark-backend

# 禁用开机自启
sudo systemctl disable strat-ark-backend
```

## 快速更新

代码更新后，使用 `--update` 刷新代码、Poetry 虚拟环境和 systemd 配置：

```bash
sudo bash deploy/deploy.sh --update
```

## 完整卸载

卸载应用本身（systemd 服务、部署目录、运行用户）：

```bash
sudo bash deploy/deploy.sh --uninstall
```

跳过确认直接卸载：

```bash
sudo bash deploy/deploy.sh --uninstall --force
```

如果还要一并删除脚本安装的 Poetry 运行时，并兼容清理旧版 `pyenv` 目录：

```bash
sudo bash deploy/deploy.sh --uninstall --purge-runtime
```

说明：

- `--uninstall` 默认清理应用相关资源，不会动系统依赖包
- `--purge-runtime` 仅在确认这台机器没有其他项目依赖当前 Poetry 运行时再使用
- 卸载不会删除 PostgreSQL、Redis、Nginx 等外部依赖服务

## 部署架构

```text
systemd (strat-ark-backend.service)
  └── gunicorn (master)
        ├── uvicorn worker 1
        ├── uvicorn worker 2
        ├── uvicorn worker 3
        └── uvicorn worker 4
```

- **Gunicorn** 作为进程管理器，负责 worker 的生命周期管理
- **UvicornWorker** 处理异步请求
- **systemd** 提供守护进程、开机自启、自动重启能力
- Python 运行环境由 **Poetry** 管理的项目内 `.venv` 提供，systemd 直接使用 `.venv/bin/gunicorn`

## 反向代理（可选）

建议使用 Nginx 反向代理：

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
    }
}
```
