import json
import logging
import re
from datetime import datetime, timezone

from .request_context import correlation_id_ctx, request_id_ctx

_SECRET_QUERY_RE = re.compile(r"(?i)(access_token|api_key|key|token|secret)=([^&\s\"']+)")
_MAPBOX_TOKEN_RE = re.compile(r"pk\.[A-Za-z0-9._-]+")


def _redact_log_message(message: str) -> str:
    message = _SECRET_QUERY_RE.sub(r"\1=REDACTED", message)
    return _MAPBOX_TOKEN_RE.sub("MAPBOX_TOKEN_REDACTED", message)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_ctx.get() or "-",
            "correlation_id": correlation_id_ctx.get() or "-",
            "message": _redact_log_message(record.getMessage()),
        }
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
