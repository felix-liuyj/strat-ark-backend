# StratArk 后端镜像（FastAPI + SQLAlchemy + PostgreSQL）
FROM python:3.13-slim

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

EXPOSE 8000

# 默认启动：init_db 在 lifespan 内自动建表；如需种子数据另跑 python -m scripts.seed
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
