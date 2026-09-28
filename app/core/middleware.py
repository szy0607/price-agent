import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Scope, Receive, Send,Message

from app.core.trace import set_trace_id, TRACE_HEADER, reset_trace_id


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
        async def send_with_trace_id(message:Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope = message)[TRACE_HEADER] = trace_id
            await send(message)
        try:
            await self.app(scope, receive, send_with_trace_id)
        finally:
            reset_trace_id(token)
