# StratArk Freqtrade Orchestrator（per-bot 实例编排，独占 docker.sock）
# 构建上下文 = engines/（compose 中指定），以便携带 freqtrade/user_data 种子。
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY freqtrade-orchestrator/requirements.txt ./
RUN pip install -r requirements.txt

COPY freqtrade-orchestrator/app.py freqtrade-orchestrator/entrypoint.sh ./
# user_data 种子（基础 config + 内置策略），entrypoint 启动时写入共享卷
COPY freqtrade/user_data /seed/user_data
RUN chmod +x entrypoint.sh

# 需访问宿主 docker.sock（compose 挂载）；容器自身 read_only + cap_drop 加固
EXPOSE 8090

ENTRYPOINT ["./entrypoint.sh"]
