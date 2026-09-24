#请求级trace_id的存放与使用
import contextvars
_trace_id : contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id",default=None)


def set_trace_id(trace_id:str) ->contextvars.Token :
    return _trace_id.set(trace_id)
def get_trace_id() -> str | None:
    return _trace_id.get()
def reset_trace_id(token:contextvars.Token)->None:
    _trace_id.reset(token)
