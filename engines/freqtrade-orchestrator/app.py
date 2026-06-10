"""StratArk Freqtrade Orchestrator —— per-bot 实例容器编排服务。

职责单一：受 token 保护的内网 REST，按 backend 下发的规格创建 / 启停 / 销毁
freqtrade 实例容器（一个 bot 一个容器）。设计要点：

- 独占 docker.sock（backend 不直连 Docker，权限隔离）；
- 凭证只经容器环境变量注入（FREQTRADE__* 原生覆盖机制），不落盘、不入日志；
- 实例共享只读 user_data 卷（基础 config + 策略文件），交易 db 走容器内 tmpfs；
- 实例容器带 ``stratark.bot`` label，列表 / 对账按 label 过滤；
- ORCHESTRATOR_TOKEN 未配置直接拒绝启动（无匿名访问）。
"""

import os
import secrets

import docker
from docker.errors import APIError, NotFound
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

ORCHESTRATOR_TOKEN = os.environ.get("ORCHESTRATOR_TOKEN", "")
INSTANCE_IMAGE_DEFAULT = os.environ.get("INSTANCE_IMAGE", "freqtradeorg/freqtrade:stable")
INSTANCE_NETWORK = os.environ.get("INSTANCE_NETWORK", "stratark")
USERDATA_VOLUME = os.environ.get("USERDATA_VOLUME", "freqtrade_userdata")
BOT_LABEL = "stratark.bot"

if not ORCHESTRATOR_TOKEN:
    raise RuntimeError("ORCHESTRATOR_TOKEN 必须配置（受保护的编排控制面，禁止匿名访问）")

app = FastAPI(title="StratArk Freqtrade Orchestrator", docs_url=None, redoc_url=None)
_bearer = HTTPBearer(auto_error=False)


def _client() -> docker.DockerClient:
    return docker.from_env()


def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if credentials is None or not secrets.compare_digest(credentials.credentials, ORCHESTRATOR_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


class CreateInstanceRequest(BaseModel):
    ref: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{2,40}$", description="实例引用名（容器名）")
    strategy: str = Field(..., min_length=1, max_length=120, description="freqtrade IStrategy 类名")
    image: str = Field("", description="实例镜像，空用默认")
    env: dict[str, str] = Field(default_factory=dict, description="FREQTRADE__* 配置覆盖（含凭证）")


class InstanceInfo(BaseModel):
    ref: str
    status: str
    health: str
    startedAt: str | None = None


def _instance_info(container) -> InstanceInfo:
    state = container.attrs.get("State", {})
    health = (state.get("Health") or {}).get("Status", "none")
    return InstanceInfo(
        ref=container.name,
        status=container.status,
        health=health,
        startedAt=state.get("StartedAt"),
    )


def _get_container(ref: str):
    client = _client()
    try:
        container = client.containers.get(ref)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=f"instance {ref} not found") from exc
    if BOT_LABEL not in (container.labels or {}):
        # 只允许操作编排器自己创建的实例容器，避免误伤平台其它服务。
        raise HTTPException(status_code=404, detail=f"instance {ref} not found")
    return container


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/instances", dependencies=[Depends(require_token)])
def list_instances() -> list[InstanceInfo]:
    containers = _client().containers.list(all=True, filters={"label": BOT_LABEL})
    return [_instance_info(c) for c in containers]


@app.get("/instances/{ref}", dependencies=[Depends(require_token)])
def get_instance(ref: str) -> InstanceInfo:
    container = _get_container(ref)
    container.reload()
    return _instance_info(container)


@app.post("/instances", dependencies=[Depends(require_token)])
def create_instance(payload: CreateInstanceRequest) -> InstanceInfo:
    client = _client()
    # 同名容器存在即先销毁重建（start 携带最新配置与凭证）。
    try:
        existing = client.containers.get(payload.ref)
        if BOT_LABEL in (existing.labels or {}):
            existing.remove(force=True)
    except NotFound:
        pass

    env = dict(payload.env)
    # 交易 db 进容器 tmpfs：实例重建即重置（live 成交以交易所为准）。
    env.setdefault("FREQTRADE__DB_URL", "sqlite:////tmp/tradesv3.sqlite")
    try:
        container = client.containers.run(
            image=payload.image or INSTANCE_IMAGE_DEFAULT,
            name=payload.ref,
            command=[
                "trade",
                "--config",
                "/freqtrade/user_data/config.json",
                "--strategy",
                payload.strategy,
            ],
            environment=env,
            labels={BOT_LABEL: payload.ref},
            network=INSTANCE_NETWORK,
            volumes={USERDATA_VOLUME: {"bind": "/freqtrade/user_data", "mode": "ro"}},
            tmpfs={"/tmp": ""},
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            read_only=True,
            user="1000:1000",
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],
            mem_limit="1g",
            pids_limit=200,
        )
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"docker run failed: {exc.explanation or exc}") from exc
    container.reload()
    return _instance_info(container)


@app.post("/instances/{ref}/start", dependencies=[Depends(require_token)])
def start_instance(ref: str) -> InstanceInfo:
    container = _get_container(ref)
    container.start()
    container.reload()
    return _instance_info(container)


@app.post("/instances/{ref}/stop", dependencies=[Depends(require_token)])
def stop_instance(ref: str) -> InstanceInfo:
    container = _get_container(ref)
    container.stop(timeout=30)
    container.reload()
    return _instance_info(container)


@app.post("/instances/{ref}/restart", dependencies=[Depends(require_token)])
def restart_instance(ref: str) -> InstanceInfo:
    container = _get_container(ref)
    container.restart(timeout=30)
    container.reload()
    return _instance_info(container)


@app.delete("/instances/{ref}", dependencies=[Depends(require_token)])
def remove_instance(ref: str) -> dict:
    container = _get_container(ref)
    container.remove(force=True)
    return {"ok": True}
