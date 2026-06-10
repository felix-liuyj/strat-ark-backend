#!/bin/sh
# 初始化共享 user_data 卷（实例容器以只读方式挂载同一卷）：
# - 基础 config 缺失时种入（敏感值留空，per-bot 差异经 FREQTRADE__* env 注入）
# - 内置策略文件以最新版本覆盖（文件名固定，不影响未来的用户自定义策略）
set -e

if [ -d /userdata ]; then
    mkdir -p /userdata/strategies
    if [ ! -f /userdata/config.json ]; then
        cp /seed/user_data/config.json /userdata/config.json
        echo "[orchestrator] 基础 config.json 已种入共享卷"
    fi
    for f in /seed/user_data/strategies/*.py; do
        [ -e "$f" ] || continue
        cp -f "$f" /userdata/strategies/
    done
    echo "[orchestrator] 内置策略已同步到共享卷"
fi

exec uvicorn app:app --host 0.0.0.0 --port 8090
