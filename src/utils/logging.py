"""Structured operational logging without repository content or credentials."""
import json
import logging
from datetime import datetime, timezone
from typing import Any


OBJECTIVE_DETAILS = {
    "attempt", "delay_seconds", "duration_seconds", "error_code", "error_reason",
    "execution_status", "next_attempt", "retry_kind", "score", "status",
}


def log_info(logger: logging.Logger, event: str, message: str, *,
             execution_id: str | None = None, node: str | None = None,
             stage: str | None = None, **details: Any) -> None:
    """Emit a concise INFO event with only operationally useful fields."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "event": event,
    }
    if stage:
        payload["stage"] = stage
    if node:
        payload["node"] = node
    if execution_id:
        payload["execution_id"] = execution_id
    payload.update({key: value for key, value in details.items()
                    if key in OBJECTIVE_DETAILS and value is not None})
    logger.info(json.dumps(payload, ensure_ascii=False))


def log_stage(logger: logging.Logger, stage: str, message: str, *,
              execution_id: str | None = None, node: str | None = None,
              repository: str | None = None, **details: Any) -> None:
    # ``repository`` remains accepted so callers do not need logging-specific
    # branches, but URLs are intentionally omitted from concise console logs.
    log_info(logger, "assessment_stage", message, execution_id=execution_id,
             node=node, stage=stage, **details)
