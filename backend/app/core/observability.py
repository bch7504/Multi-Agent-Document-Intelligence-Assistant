"""Structured application logging and request correlation."""

import json
import logging
import sys
from contextvars import ContextVar
from threading import Lock
from time import perf_counter
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class TokenUsageCallbackHandler(BaseCallbackHandler):
    """Aggregate token metadata across providers and structured-output calls."""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self._lock = Lock()

    @staticmethod
    def _normalized_usage(raw: object) -> tuple[int, int, int] | None:
        if not isinstance(raw, dict):
            return None
        input_tokens = int(raw.get("input_tokens", raw.get("prompt_tokens", 0)) or 0)
        output_tokens = int(
            raw.get("output_tokens", raw.get("completion_tokens", 0)) or 0
        )
        total_tokens = int(raw.get("total_tokens", input_tokens + output_tokens) or 0)
        if not any((input_tokens, output_tokens, total_tokens)):
            return None
        return input_tokens, output_tokens, total_tokens

    def _add(self, usage: tuple[int, int, int]) -> None:
        with self._lock:
            self.input_tokens += usage[0]
            self.output_tokens += usage[1]
            self.total_tokens += usage[2]

    def on_llm_end(self, response, **kwargs) -> None:
        counted = False
        for generation_list in getattr(response, "generations", []):
            for generation in generation_list:
                message = getattr(generation, "message", None)
                usage = self._normalized_usage(
                    getattr(message, "usage_metadata", None)
                )
                if usage is None:
                    metadata = getattr(message, "response_metadata", {}) or {}
                    usage = self._normalized_usage(metadata.get("token_usage"))
                if usage is not None:
                    self._add(usage)
                    counted = True

        if not counted:
            llm_output = getattr(response, "llm_output", None) or {}
            usage = self._normalized_usage(llm_output.get("token_usage"))
            if usage is not None:
                self._add(usage)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    logger = logging.getLogger("document_assistant")
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    logger.info(event.replace("_", " "), extra={"event": event, "fields": fields})


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        token = request_id_context.set(request_id)
        started = perf_counter()
        logger = logging.getLogger("document_assistant.http")
        try:
            response = await call_next(request)
            duration_ms = round((perf_counter() - started) * 1_000)
            log_event(
                logger,
                "http_request_complete",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "HTTP request failed",
                extra={
                    "event": "http_request_failed",
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round((perf_counter() - started) * 1_000),
                    },
                },
            )
            raise
        finally:
            request_id_context.reset(token)
