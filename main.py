"""
FastAPI application entry point.
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN, HTTP_500_INTERNAL_SERVER_ERROR

from api import api_router
from configs import get_settings
from libs import lifespan
from libs.handler.exceptions import (
    AppServiceException,
    ForbiddenException,
    custom_app_service_exception_handler,
    custom_auth_forbidden_exception_handler,
    custom_internal_server_exception_handler,
    custom_un_auth_exception_handler,
    custom_validation_exception_handler,
)
from libs.middlewares import ApiRequestLogRecordMiddleware

app = FastAPI(
    title=get_settings().APP_NAME,
    description="Backend scaffold API service.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

static_path = get_settings().STATIC_DIR
if not os.path.exists(static_path):
    os.makedirs(static_path, exist_ok=True)
app.mount(get_settings().STATIC_URL, StaticFiles(directory=static_path), name="statics")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiRequestLogRecordMiddleware)

app.add_exception_handler(HTTP_401_UNAUTHORIZED, custom_un_auth_exception_handler)
app.add_exception_handler(HTTP_403_FORBIDDEN, custom_auth_forbidden_exception_handler)
app.add_exception_handler(ForbiddenException, custom_app_service_exception_handler)
app.add_exception_handler(AppServiceException, custom_app_service_exception_handler)
app.add_exception_handler(RequestValidationError, custom_validation_exception_handler)
app.add_exception_handler(HTTP_500_INTERNAL_SERVER_ERROR, custom_internal_server_exception_handler)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=get_settings().APP_HOST,
        port=get_settings().APP_PORT,
        reload=get_settings().APP_DEBUG,
    )
