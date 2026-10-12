from fastapi import FastAPI
from app.core.errors import register_exception_handlers
from app.core.http_client import start_http_client, close_http_client
from app.core.logging import setup_logging
from app.core.middleware import TraceMiddleware
from app.router.cartitem_router import cart_router
from app.router.health import health_router
from app.router.log_in import auth_router
from app.router.purchase_record import purchase_router
from app.router.owned_router import owned_router
from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

from app.database.session import async_session_local
from app.router.image_file import image_file_router
from app.router.setting import settings_router
from app.router.upload import upload_router
from app.services import image_service, image_store, model_call

# 图片清理间隔：pending 超 24h / released 的文件与行。幂等，多 worker 重复跑无害
_IMAGE_CLEANUP_INTERVAL = 3600


async def _image_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(_IMAGE_CLEANUP_INTERVAL)
        try:
            async with async_session_local() as session:
                await image_service.cleanup_once(session)
        except Exception:
            logging.getLogger(__name__).exception("图片清理任务失败")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 时序要点：uvicorn 的日志配置(dictConfig)在 import 应用之后、startup 之前执行——
    # 在模块顶层改会被覆盖回去，只有 lifespan 里改才站得住
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)   # INFO 级访问行不再输出

    start_http_client()
    cleanup_task = asyncio.create_task(_image_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        await close_http_client()

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
setup_logging()
register_exception_handlers(app)
app.add_middleware(TraceMiddleware)
app.include_router(auth_router)
app.include_router(purchase_router)
app.include_router(health_router)
app.include_router(cart_router)
app.include_router(owned_router)
app.include_router(settings_router)
app.include_router(upload_router)
# /uploads/{name} 路由必须在任何 mount 之前注册——同前缀下具体路由优先匹配，
# 访问收口（登录 + 归属校验）全在这个路由里，uploads/ 不再有裸奔的静态出口
app.include_router(image_file_router)


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