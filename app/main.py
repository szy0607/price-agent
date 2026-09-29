from fastapi import FastAPI
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import TraceMiddleware
from app.router.health import health_router
from app.router.log_in import auth_router
from app.router.settings import settings_router
from app.router.chat import chat_router
setup_logging()
app = FastAPI()
register_exception_handlers(app)
app.add_middleware(TraceMiddleware)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(health_router)
