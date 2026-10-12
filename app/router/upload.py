import asyncio
import logging

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.errors import BizError, ErrorCode, success
from app.core.rate_limit import check_rate_limit
from app.dependence import CurrentUser, require_same_origin_write, get_db_session
from app.services import image_service, image_store
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

upload_router = APIRouter(tags=["upload"], prefix="/upload")

# 上传限流口径：每用户 60 秒 10 次（传商品图是正常操作，放得比 ai-draft 宽）
_UPLOAD_LIMIT = 10
_UPLOAD_WINDOW = 60


@upload_router.post("/image", dependencies=[Depends(require_same_origin_write)])
async def upload_image(user: CurrentUser, image: UploadFile = File(...),
                       session: AsyncSession = Depends(get_db_session)):
    check_rate_limit(f"upload:{user.id}", limit=_UPLOAD_LIMIT, window=_UPLOAD_WINDOW)

    # 分块读 + 累加计数：不信 image.size（chunked 传输下客户端不发 Content-Length，
    # 预检直接绕过），读超了就断，绝不给「声明很小实际巨大」留空间
    chunks: list[bytes] = []
    total = 0
    while chunk := await image.read(image_store.CHUNK_SIZE):
        total += len(chunk)
        if total > image_store.MAX_BYTES:
            logger.info("上传超限被拒: user_id=%s bytes=%s", user.id, total)
            raise BizError(ErrorCode.PARAM_INVALID, "图片不能超过 2MB")
        chunks.append(chunk)
    if total == 0:
        raise BizError(ErrorCode.PARAM_INVALID, "图片内容为空")

    # image_store 是同步 CPU 活，丢线程池跑，别占着事件循环
    rel_path = await asyncio.to_thread(image_store.save_upload_image, b"".join(chunks), image.filename)
    # 落盘即登记：pending 行让这张图从第一秒起就有主，24h 无人认领由定时任务清
    row = await image_service.register_upload(user.id, rel_path, session)
    logger.info("上传成功: user_id=%s bytes=%s path=%s", user.id, total, rel_path)
    return success({"id": row.id, "image": rel_path})
