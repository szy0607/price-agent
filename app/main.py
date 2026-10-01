from fastapi import FastAPI
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import TraceMiddleware
from app.router.health import health_router
from app.router.log_in import auth_router
from app.router.settings import settings_router
from app.router.chat import chat_router
from contextlib import asynccontextmanager
import logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 时序要点：uvicorn 的日志配置(dictConfig)在 import 应用之后、startup 之前执行——
    # 在模块顶层改会被覆盖回去，只有 lifespan 里改才站得住
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)   # INFO 级访问行不再输出
    yield

app = FastAPI(lifespan=lifespan)
setup_logging()
register_exception_handlers(app)
app.add_middleware(TraceMiddleware)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(health_router)
