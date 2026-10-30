import logging
import os
import sys
from contextvars import ContextVar
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_context.get()
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s"
    )
    if root.handlers:
        for handler in root.handlers:
            if not getattr(handler, "_parchapay_handler", False):
                handler.addFilter(RequestIdFilter())
                handler.setFormatter(formatter)
                handler._parchapay_handler = True
        logging.getLogger("httpx").setLevel(logging.WARNING)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler._parchapay_handler = True
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(formatter)
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = uuid4().hex
        token = request_id_context.set(request_id)
        started = perf_counter()
        logger = logging.getLogger("app.http")
        logger.info("request_started method=%s", request.method)
        try:
            response = await call_next(request)
            route = getattr(request.scope.get("route"), "path", "unmatched")
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed method=%s route=%s status=%s elapsed_ms=%s",
                request.method,
                route,
                response.status_code,
                elapsed_ms,
            )
            return response
        except Exception:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            logger.exception(
                "request_failed method=%s route=%s",
                request.method,
                route,
            )
            raise
        finally:
            request_id_context.reset(token)
