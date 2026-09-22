import logging

from fastapi import FastAPI,Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
logger = logging.getLogger(__name__)
class ErrorCode:
    PARAM_INVALID = 40001
    CAPTCHA_INVALID = 40002
    SESSION_INVALID = 40101
    CREDENTIALS = 40102
    EMAIL_TAKEN = 40901
    RATE_LIMITED = 42901
    INTERNAL = 50000

CODE_HTTP_STATUS : dict[int,int] = {
    40001:400,
    40002:400,
    40101:401,
    40102:401,
    40901:409,
    42901:429,
    50000:500,
}
class BizError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        if code not in CODE_HTTP_STATUS:
            raise ValueError(f"未定义错误码{code}")
        self.code = code
        self.msg = msg
        self.http_status = CODE_HTTP_STATUS[code]
        super().__init__(msg)

def success(data=None) -> dict:
    return {"code":0,"msg":"success","data":data}

def envelope(code:int,msg:str,http_status:int,data=None) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"code":code,"msg":msg,"data":data},
    )

def register_exception_handlers(app : FastAPI):
    @app.exception_handler(BizError)
    async def _h_biz(request:Request,exc:BizError)->JSONResponse:
        return envelope(exc.code,exc.msg,exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def _h_req_val(request:Request,exc:RequestValidationError)->JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(
            str(p) for p in first.get("loc",()) if p not in ("body","query","path")
        ) or "request"
        detail = str(first.get("msg","参数校验失败")).removeprefix("Value Error,")
        return envelope(ErrorCode.PARAM_INVALID,f"{field}:{detail}",400)

    @app.exception_handler(StarletteHTTPException)
    async def _h_http(request:Request,exc:StarletteHTTPException)->JSONResponse:
        code = ErrorCode.INTERNAL if exc.status_code == 500 else exc.status_code * 100 + 1
        return envelope(code,exc.detail,exc.status_code)
    @app.exception_handler(Exception)
    async def _h_exc(request:Request,exc:Exception)->JSONResponse:
        logger.exception("未处理异常 %s %s",request.method,request.url.path)
        return envelope(ErrorCode.INTERNAL,"内部服务器错误",500)
