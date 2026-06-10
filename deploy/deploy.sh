#!/usr/bin/env bash
# ============================================================
# 后端脚手架 - Linux 本地部署脚本
# 用法:
#   sudo bash deploy.sh
#   sudo bash deploy.sh --update
#   sudo bash deploy.sh --uninstall [--purge-runtime] [--force]
# ============================================================

set -euo pipefail

# -------------------- 配置 --------------------
APP_NAME="${APP_NAME:-strat-ark-backend}"
APP_USER="${APP_USER:-strat-ark}"                   # 运行服务的系统用户
APP_DIR="${APP_DIR:-/opt/strat-ark-backend}"    # 项目部署目录
REPO_URL="${REPO_URL:-}"                      # Git 仓库地址（留空则跳过 clone）
PYTHON_MIN_VERSION="${PYTHON_MIN_VERSION:-3.13}"
PYTHON_BIN="${PYTHON_BIN:-/opt/python3.13/bin/python}"
WORKERS="${WORKERS:-4}"
PORT="${PORT:-8000}"
VENV_DIR="${APP_DIR}/.venv"
POETRY_HOME="${POETRY_HOME:-/opt/poetry}"
POETRY_BIN="${POETRY_BIN:-${POETRY_HOME}/bin/poetry}"
POETRY_CONFIG_DIR="${POETRY_CONFIG_DIR:-/root/.config/pypoetry}"
LEGACY_PYENV_ROOT="${LEGACY_PYENV_ROOT:-/opt/pyenv}"
LEGACY_POETRY_HOME="${LEGACY_POETRY_HOME:-/root/.local/share/pypoetry}"
LEGACY_POETRY_BIN="${LEGACY_POETRY_BIN:-/root/.local/bin/poetry}"

SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# -------------------- 颜色 --------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# -------------------- 检查 root --------------------
[[ $EUID -ne 0 ]] && error "请使用 sudo 运行此脚本"

UPDATE_ONLY=false
UNINSTALL=false
PURGE_RUNTIME=false
FORCE=false

print_usage() {
    cat <<EOF
用法:
  sudo bash deploy/deploy.sh
  sudo bash deploy/deploy.sh --update
  sudo bash deploy/deploy.sh --uninstall [--purge-runtime] [--force]

选项:
  --update         刷新代码、Poetry 虚拟环境与 systemd 配置
  --uninstall      完整卸载应用，移除 systemd 服务、部署目录、运行用户
  --purge-runtime  卸载时额外移除 Poetry 运行时，并兼容清理旧版 pyenv
  --force          卸载时跳过二次确认
  -h, --help       显示帮助
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --update)
                UPDATE_ONLY=true
                ;;
            --uninstall)
                UNINSTALL=true
                ;;
            --purge-runtime)
                PURGE_RUNTIME=true
                ;;
            --force)
                FORCE=true
                ;;
            -h|--help)
                print_usage
                exit 0
                ;;
            *)
                error "未知参数: $1"
                ;;
        esac
        shift
    done

    if [[ "$UPDATE_ONLY" == true && "$UNINSTALL" == true ]]; then
        error "--update 与 --uninstall 不能同时使用"
    fi

    if [[ "$PURGE_RUNTIME" == true && "$UNINSTALL" != true ]]; then
        error "--purge-runtime 只能与 --uninstall 一起使用"
    fi
}

parse_args "$@"

service_exists() {
    [[ -f "$SERVICE_FILE" ]]
}

version_ge() {
    [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" == "$2" ]]
}

is_disallowed_python_path() {
    local path="$1"
    [[ "$path" == /root/* ]]
}

confirm_uninstall() {
    if [[ "$FORCE" == true ]]; then
        return
    fi

    echo ""
    warn "即将卸载 ${APP_NAME}，将执行以下操作："
    warn "  1. 停止并禁用 systemd 服务"
    warn "  2. 删除服务文件 ${SERVICE_FILE}"
    warn "  3. 删除部署目录 ${APP_DIR}"
    warn "  4. 删除运行用户 ${APP_USER}"
    if [[ "$PURGE_RUNTIME" == true ]]; then
        warn "  5. 额外删除 Poetry 运行时，并兼容清理旧版 pyenv 目录"
    fi
    echo ""
    read -r -p "输入 UNINSTALL 确认继续: " confirm
    [[ "$confirm" == "UNINSTALL" ]] || error "已取消卸载"
}

require_command() {
    local cmd="$1"
    local hint="${2:-请先安装 ${cmd} 后重试}"

    command -v "$cmd" &>/dev/null || error "缺少命令 ${cmd}。${hint}"
}

# ============================================================
# 1. 检查 Python 解释器
# ============================================================
ensure_python() {
    info "检查 Python ${PYTHON_MIN_VERSION}+ ..."

    local candidates=()
    local candidate=""
    local resolved=""
    local target=""
    local ver=""

    if [[ -n "$PYTHON_BIN" ]]; then
        candidates+=("$PYTHON_BIN")
    fi
    candidates+=(
        "/usr/bin/python3.13"
        "/usr/local/bin/python3.13"
        "/usr/bin/python3"
        "/usr/local/bin/python3"
        "python3.13"
        "python3"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -x "$candidate" ]]; then
            resolved="$candidate"
        elif command -v "$candidate" &>/dev/null; then
            resolved="$(command -v "$candidate")"
        else
            continue
        fi

        ver="$("$resolved" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        if version_ge "$ver" "$PYTHON_MIN_VERSION"; then
            PYTHON_BIN="$resolved"
            info "使用 Python: ${PYTHON_BIN} (${ver})"
            return
        fi
    done

    error "未找到满足 >= ${PYTHON_MIN_VERSION} 的可用 Python 解释器。部署解释器不能位于 /root 下（例如 root 的 conda/pyenv 环境）。请先安装系统 Python ${PYTHON_MIN_VERSION}+，或通过 PYTHON_BIN=/usr/bin/python3.13 显式指定。"
}

# ============================================================
# 2. 安装 Poetry
# ============================================================
ensure_poetry() {
    info "检查 Poetry..."
    if [[ ! -x "$POETRY_BIN" ]]; then
        require_command "curl" "未检测到 Poetry，且安装 Poetry 需要 curl"
        info "安装 Poetry..."
        curl -sSL https://install.python-poetry.org | POETRY_HOME="$POETRY_HOME" "$PYTHON_BIN" -
    fi
    "$POETRY_BIN" --version
}

# ============================================================
# 3. 创建运行用户
# ============================================================
ensure_user() {
    if ! id "$APP_USER" &>/dev/null; then
        info "创建系统用户 ${APP_USER}..."
        useradd --system --shell /usr/sbin/nologin --home-dir "$APP_DIR" "$APP_USER"
    fi
}

# ============================================================
# 4. 部署代码
# ============================================================
deploy_code() {
    if [[ ! -d "$APP_DIR" ]]; then
        if [[ -n "$REPO_URL" ]]; then
            require_command "git" "设置 REPO_URL 时需要 git clone 仓库"
            info "克隆仓库到 ${APP_DIR}..."
            git clone "$REPO_URL" "$APP_DIR"
        else
            require_command "rsync" "未设置 REPO_URL 时需要 rsync 同步当前项目目录"
            info "复制当前项目到 ${APP_DIR}..."
            # 假设脚本在 deploy/ 子目录，项目根为上一级
            local project_root
            project_root="$(dirname "$SCRIPT_DIR")"
            mkdir -p "$APP_DIR"
            rsync -a --exclude='.venv' --exclude='__pycache__' \
                  --exclude='.git' --exclude='*.pyc' \
                  "${project_root}/" "${APP_DIR}/"
        fi
    else
        if [[ -d "${APP_DIR}/.git" ]]; then
            require_command "git" "部署目录为 Git 仓库时需要 git pull 更新代码"
            info "拉取最新代码..."
            cd "$APP_DIR" && git pull --ff-only
        else
            require_command "rsync" "部署目录不是 Git 仓库时需要 rsync 同步代码"
            info "同步代码..."
            local project_root
            project_root="$(dirname "$SCRIPT_DIR")"
            rsync -a --delete \
                  --exclude='.venv' --exclude='__pycache__' \
                  --exclude='.git' --exclude='*.pyc' \
                  --exclude='.env' --exclude='statics/' \
                  "${project_root}/" "${APP_DIR}/"
        fi
    fi

    # 确保 .env 存在
    if [[ ! -f "${APP_DIR}/.env" ]]; then
        warn ".env 文件不存在，已从 .env.example 复制模板，请编辑填写实际配置！"
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    fi

    chown -R "${APP_USER}:${APP_USER}" "$APP_DIR"
}

# ============================================================
# 5. 安装 Python 依赖
# ============================================================
install_deps() {
    info "使用 Poetry 安装依赖并管理项目虚拟环境..."
    cd "$APP_DIR"
    POETRY_VIRTUALENVS_IN_PROJECT=true "$POETRY_BIN" env use "$PYTHON_BIN"
    POETRY_VIRTUALENVS_IN_PROJECT=true "$POETRY_BIN" install --no-interaction --no-root

    if [[ ! -x "${VENV_DIR}/bin/gunicorn" ]]; then
        error "Poetry 虚拟环境创建失败，请检查 ${VENV_DIR}"
    fi

    chown -R "${APP_USER}:${APP_USER}" "$APP_DIR"
}

# ============================================================
# 5.5 数据库迁移（部署期执行，应用启动不跑 ALTER）
# ============================================================
run_migrations() {
    info "执行数据库迁移 alembic upgrade head..."
    local alembic_bin="${VENV_DIR}/bin/alembic"
    if [[ ! -x "$alembic_bin" ]]; then
        error "未找到 alembic 可执行文件: ${alembic_bin}（请确认依赖安装成功）"
    fi
    # 迁移读取 configs（pydantic-settings 自动加载 ${APP_DIR}/.env），以部署用户身份执行
    (cd "$APP_DIR" && sudo -u "$APP_USER" "$alembic_bin" upgrade head) \
        || error "数据库迁移失败，请检查 DATABASE_URL 与迁移脚本"
}

# ============================================================
# 6. 配置 systemd 服务
# ============================================================
setup_systemd() {
    info "配置 systemd 服务..."

    local gunicorn_bin
    gunicorn_bin="${VENV_DIR}/bin/gunicorn"

    if [[ ! -x "$gunicorn_bin" ]]; then
        error "未找到 gunicorn 可执行文件: ${gunicorn_bin}"
    fi

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=${APP_NAME} API
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service
StartLimitIntervalSec=60

[Service]
Type=exec
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin
EnvironmentFile=-${APP_DIR}/.env

ExecStart=${gunicorn_bin} main:app \\
    --workers ${WORKERS} \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 0.0.0.0:${PORT} \\
    --access-logfile - \\
    --error-logfile - \\
    --timeout 300

Restart=on-failure
RestartSec=5
StartLimitBurst=5

# 安全加固
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${APP_DIR}/statics ${APP_DIR}/.venv
ProtectHome=true
PrivateTmp=true

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    info "systemd 服务已配置: ${SERVICE_FILE}"
}

# ============================================================
# 7. 完整卸载
# ============================================================
stop_and_disable_service() {
    if service_exists; then
        if systemctl is-active --quiet "$APP_NAME"; then
            info "停止服务 ${APP_NAME}..."
            systemctl stop "$APP_NAME"
        else
            info "服务 ${APP_NAME} 当前未运行"
        fi

        if systemctl is-enabled --quiet "$APP_NAME" 2>/dev/null; then
            info "禁用开机自启..."
            systemctl disable "$APP_NAME"
        fi
    else
        info "未发现 systemd 服务文件，跳过服务停止"
    fi
}

remove_service_file() {
    if [[ -f "$SERVICE_FILE" ]]; then
        info "删除服务文件 ${SERVICE_FILE}..."
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        systemctl reset-failed "$APP_NAME" >/dev/null 2>&1 || true
    else
        info "服务文件不存在，跳过删除"
    fi
}

remove_app_dir() {
    if [[ -d "$APP_DIR" ]]; then
        info "删除部署目录 ${APP_DIR}..."
        rm -rf "$APP_DIR"
    else
        info "部署目录不存在，跳过删除"
    fi
}

remove_app_user() {
    if id "$APP_USER" &>/dev/null; then
        info "删除运行用户 ${APP_USER}..."
        userdel -r "$APP_USER" || warn "删除用户失败，请手动检查该用户是否仍被其他进程占用"
    else
        info "运行用户不存在，跳过删除"
    fi
}

purge_runtime() {
    if [[ "$PURGE_RUNTIME" != true ]]; then
        info "保留 Poetry 运行时；如需一并清理，请使用 --purge-runtime"
        return
    fi

    if [[ -d "$POETRY_HOME" ]]; then
        info "删除 Poetry 目录 ${POETRY_HOME}..."
        rm -rf "$POETRY_HOME"
    else
        info "未发现 Poetry 主目录，跳过"
    fi

    if [[ -L "/usr/local/bin/poetry" ]] && [[ "$(readlink /usr/local/bin/poetry)" == "${POETRY_BIN}" ]]; then
        info "删除 Poetry 软链接 /usr/local/bin/poetry..."
        rm -f /usr/local/bin/poetry
    fi

    if [[ -f "$LEGACY_POETRY_BIN" ]]; then
        info "删除旧版 Poetry 可执行文件 ${LEGACY_POETRY_BIN}..."
        rm -f "$LEGACY_POETRY_BIN"
    else
        info "未发现旧版 Poetry 可执行文件，跳过"
    fi

    if [[ -d "$POETRY_CONFIG_DIR" ]]; then
        info "删除 Poetry 配置目录 ${POETRY_CONFIG_DIR}..."
        rm -rf "$POETRY_CONFIG_DIR"
    else
        info "未发现 Poetry 配置目录，跳过"
    fi

    if [[ -d "$LEGACY_POETRY_HOME" ]]; then
        info "删除旧版 Poetry 目录 ${LEGACY_POETRY_HOME}..."
        rm -rf "$LEGACY_POETRY_HOME"
    else
        info "未发现旧版 Poetry 主目录，跳过"
    fi

    if [[ -d "$LEGACY_PYENV_ROOT" ]]; then
        info "删除旧版 pyenv 目录 ${LEGACY_PYENV_ROOT}..."
        rm -rf "$LEGACY_PYENV_ROOT"
    else
        info "未发现旧版 pyenv 目录，跳过"
    fi
}

uninstall_app() {
    echo ""
    echo "=========================================="
    echo "  ${APP_NAME} 卸载脚本"
    echo "=========================================="
    echo ""

    confirm_uninstall
    stop_and_disable_service
    remove_service_file
    remove_app_user
    remove_app_dir
    purge_runtime

    echo ""
    info "=========================================="
    info "  卸载完成！"
    info "=========================================="
    info ""
    info "  已清理: service / deploy dir / app user"
    if [[ "$PURGE_RUNTIME" == true ]]; then
        info "  已额外清理: Poetry（并兼容清理旧版 pyenv）"
    fi
    info ""
}

# ============================================================
# 8. 启动并设置开机自启
# ============================================================
enable_and_start() {
    info "启用开机自启..."
    systemctl enable "$APP_NAME"

    info "重启服务..."
    systemctl restart "$APP_NAME"

    sleep 2
    if systemctl is-active --quiet "$APP_NAME"; then
        info "服务已启动"
        systemctl status "$APP_NAME" --no-pager -l
    else
        error "服务启动失败，请查看日志: journalctl -u ${APP_NAME} -f"
    fi
}

# ============================================================
# 主流程
# ============================================================
main() {
    if [[ "$UNINSTALL" == true ]]; then
        uninstall_app
        return
    fi

    echo ""
    echo "=========================================="
    echo "  ${APP_NAME} 部署脚本"
    echo "=========================================="
    echo ""

    if [[ "$UPDATE_ONLY" == true ]]; then
        info "更新模式：刷新代码、Poetry 虚拟环境与 systemd 配置"
    fi

    ensure_python
    ensure_poetry
    ensure_user
    deploy_code
    install_deps
    run_migrations
    setup_systemd
    enable_and_start

    echo ""
    info "=========================================="
    info "  部署完成！"
    info "=========================================="
    info ""
    info "  服务状态:  systemctl status ${APP_NAME}"
    info "  查看日志:  journalctl -u ${APP_NAME} -f"
    info "  重启服务:  systemctl restart ${APP_NAME}"
    info "  停止服务:  systemctl stop ${APP_NAME}"
    info "  快速更新:  sudo bash deploy/deploy.sh --update"
    info "  完整卸载:  sudo bash deploy/deploy.sh --uninstall"
    info ""
    info "  API 地址:  http://localhost:${PORT}"
    info "  API 文档:  http://localhost:${PORT}/docs"
    info ""

    if [[ ! -f "${APP_DIR}/.env" ]] || grep -q "your-" "${APP_DIR}/.env" 2>/dev/null; then
        warn "请编辑 ${APP_DIR}/.env 填写实际配置后重启服务"
    fi
}

main "$@"
