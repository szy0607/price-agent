import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Scope, Receive, Send,Message

from app.core.trace import set_trace_id, TRACE_HEADER, reset_trace_id

import logging

logger = logging.getLogger("app.access")
_ROUTE_NAMES = {
    "/auth/login":"登录",
    "/auth/register":"注册",
    "/auth/logout":"退出登录",
    "/auth/me":"获取用户信息",
    "/auth/captcha":"获取验证码",
    "/health":"健康检查",
    "/settings/api-keys":"获取API密钥"
}
def _route_name(scope:Scope) -> str:
    if scope["path"] in _ROUTE_NAMES:
        return _ROUTE_NAMES[scope["path"]]
    route = scope.get("route")
    return getattr(route,"name","")



class TraceMiddleware:
    def __init__(self,app:ASGIApp):
        self.app = app
    async def __call__(self,scope:Scope, receive:Receive, send:Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        trace_id = uuid.uuid4().hex
        token = set_trace_id(trace_id)
        scope.setdefault("state",{})
        scope["state"]["trace_id"] = trace_id
        start = time.perf_counter()
        status_holder = {"code":500}
        async def send_with_trace_id(message:Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                MutableHeaders(scope = message)[TRACE_HEADER] = trace_id
            await send(message)
        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            elapsed = (time.perf_counter() - start)*1000
            logger.info(
                "%s %s -> %s %s(耗时%.0fms)",
                scope["method"],
                scope["path"],
                status_holder["code"],
                _route_name(scope),
                elapsed
            )
            reset_trace_id(token)
