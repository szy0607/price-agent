import asyncio

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.errors import BizError, ErrorCode, success
from app.dependence import CurrentUser, require_same_origin_write
from app.services import image_store

upload_router = APIRouter(tags=["upload"], prefix="/upload")


@upload_router.post("/image", dependencies=[Depends(require_same_origin_write)])
async def upload_image(user: CurrentUser, image: UploadFile = File(...)):
    # 先按 Content-Length 挡超大文件，再整体读入——2MB 上限下两者开销都可接受
    if image.size and image.size > image_store._MAX_BYTES:
        raise BizError(ErrorCode.PARAM_INVALID, "图片不能超过 2MB")
    data = await image.read()
    # image_store 是同步 CPU 活，丢线程池跑，别占着事件循环
    rel_path = await asyncio.to_thread(image_store.save_upload_image, data, image.filename)
    return success({"image": rel_path})
