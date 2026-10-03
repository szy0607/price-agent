from fastapi import FastAPI
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import TraceMiddleware
from app.router.cartitem_router import cart_router
from app.router.health import health_router
from app.router.log_in import auth_router
from app.router.settings import settings_router
from app.router.chat import chat_router
from app.router.purchase_record import purchase_router
from contextlib import asynccontextmanager
import logging
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 时序要点：uvicorn 的日志配置(dictConfig)在 import 应用之后、startup 之前执行——
    # 在模块顶层改会被覆盖回去，只有 lifespan 里改才站得住
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)   # INFO 级访问行不再输出
    yield

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
setup_logging()
register_exception_handlers(app)
app.add_middleware(TraceMiddleware)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(chat_router)
app.include_router(purchase_router)
app.include_router(health_router)
app.include_router(cart_router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=app.title + " - Swagger UI",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url="/openapi.json",
        title=app.title + " - ReDoc",
        redoc_js_url="/static/redoc.standalone.js",
    )