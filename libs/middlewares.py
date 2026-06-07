"""Application middlewares."""

from time import perf_counter

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from libs.logger import api_request_logger
from libs.request_timing import (
    attach_server_timing_header,
    get_request_timings,
    record_request_timing,
    should_trace_request,
)

__all__ = ("ApiRequestLogRecordMiddleware",)


class ApiRequestLogRecordMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = perf_counter()
        request_body = await request.body()
        response = await call_next(request)
        process_time_ms = (perf_counter() - start_time) * 1000
        record_request_timing(request, "middlewareTotal", process_time_ms)
        attach_server_timing_header(request, response)

        if request.url.path != "/health":
            log_payload = {
                "path": request.url.path,
                "method": request.method,
                "query_params": dict(request.query_params),
                "request_body": request_body.decode("utf-8", errors="ignore"),
                "request_headers": dict(request.headers),
                "status_code": response.status_code,
                "process_time_ms": process_time_ms,
            }
            if should_trace_request(request):
                log_payload["timings"] = list(get_request_timings(request))
            api_request_logger.info(log_payload)
        return response
