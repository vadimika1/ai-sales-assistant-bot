from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_feedback_store
from app.storage import FeedbackStore

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _database_ready_payload(store: FeedbackStore) -> tuple[int, dict[str, Any]]:
    try:
        with store.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        logger.warning("Readiness database check failed: %s", error)
        return (
            503,
            {
                "status": "fail",
                "checks": {
                    "database": {
                        "status": "fail",
                        "detail": "database unavailable",
                    }
                },
            },
        )
    except Exception:
        logger.exception("Unexpected readiness database check error")
        return (
            503,
            {
                "status": "fail",
                "checks": {
                    "database": {
                        "status": "fail",
                        "detail": "database unavailable",
                    }
                },
            },
        )

    return (
        200,
        {
            "status": "ok",
            "checks": {
                "database": {
                    "status": "ok",
                }
            },
        },
    )


@router.get("/health/ready")
def health_ready(store: FeedbackStore = Depends(get_feedback_store)) -> JSONResponse:
    status_code, payload = _database_ready_payload(store)
    return JSONResponse(status_code=status_code, content=payload)
