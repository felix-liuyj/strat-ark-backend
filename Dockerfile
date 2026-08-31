# StratArk 后端镜像（FastAPI + SQLAlchemy + PostgreSQL）
ARG PYTHON_BASE_IMAGE=python:3.13-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 系统依赖（psycopg / cryptography 等构建期可能需要；slim 下 psycopg[binary] 自带 wheel）
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 依赖（先装依赖以利用 Docker 层缓存）
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 应用代码
COPY . .

# 非 root 运行
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 启动顺序：先执行 Alembic 迁移（schema 演进唯一通道；空库由 init_db 的 create_all 兜底），
# 再起服务。如需种子数据另跑 python -m scripts.seed
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
