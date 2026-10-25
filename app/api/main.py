import logging

from fastapi import FastAPI
import uvicorn

from app.api.errors import register_exception_handlers
from app.api.middleware.request_id import RequestIdMiddleware
from app.api.routers.ai import router as ai_router
from app.api.routers.health import router as health_router
from app.config import get_settings
from app.logging_config import configure_logging
from app.preflight import validate_runtime_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="AI Sales Assistant API", version="0.1.0")
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(ai_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    validate_runtime_settings(settings, target="api")
    logger.info(
        "Starting API server",
        extra={"app_env": settings.app_env, "host": settings.app_host, "port": settings.app_port},
    )
    uvicorn.run(
        "app.api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
