"""GET /uploads/{name} —— 用户展示图的唯一出口。

替代原来的 StaticFiles 直挂：同前缀下具体路由优先于 mount，所有图片请求
先过这道鉴权（登录 + 归属），再 FileResponse 读盘。前端 src 不用改。

判定口径与 purchase-records 一致：图不是你的（或未登记/文件不在）
一律「图片不存在」40001，不透出「存在但不属于你」这种可枚举差别。
"""
import re

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.dependence import CurrentUser, get_db_session
from app.services import image_service, image_store

image_file_router = APIRouter(tags=["image-file"])

# 落盘文件名只可能是 uuid4().hex + .jpg；正则同时是路径穿越的防线
_NAME_RE = re.compile(r"^[0-9a-f]{32}\.jpg$")


@image_file_router.get("/uploads/{name}")
async def get_upload_image(name: str, user: CurrentUser,
                           session: AsyncSession = Depends(get_db_session)):
    if not _NAME_RE.match(name):
        raise BizError(ErrorCode.PARAM_INVALID, "图片不存在")
    rel_path = f"/uploads/{name}"
    owner_id = await image_service.path_owner_id(rel_path, session)
    if owner_id != user.id:
        raise BizError(ErrorCode.PARAM_INVALID, "图片不存在")
    path = image_store.UPLOAD_DIR / name
    if not path.is_file():
        raise BizError(ErrorCode.PARAM_INVALID, "图片不存在")
    return FileResponse(path, media_type="image/jpeg")
