import httpx

_TIMEOUT = httpx.Timeout(35.0,connect=8.0)

_shared : httpx.AsyncClient | None = None

def start_http_client()->None:
    """启动http客户端,lifespan启动时调,全应用共享"""
    global _shared
    _shared = httpx.AsyncClient(timeout=_TIMEOUT,
                                follow_redirects=False,
                                limits=httpx.Limits(max_connections=100,max_keepalive_connections=20,keepalive_expiry=60.0))


async def close_http_client()->None:
    """关闭http客户端,lifespan关闭时调用"""
    global _shared
    if _shared is not None:
        await _shared.aclose()
        _shared = None

def get_http_client()->httpx.AsyncClient | None:
    """获取http客户端"""
    return _shared
