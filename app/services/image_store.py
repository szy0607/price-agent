import io
import logging
import os
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from app.core.errors import BizError, ErrorCode

logger = logging.getLogger(__name__)

# 用户上传图片的落地目录：项目根 uploads/，由 main.py 经 StaticFiles 挂到 /uploads
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# —— 上传策略常量（代码策略，不是部署差异，故意不进 .env）——
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 2 * 1024 * 1024        # 文件大小上限
MAX_EDGE = 1280                    # 展示图最长边：超过的缩到这个值（行为兼容原 thumbnail）
MAX_PIXELS = 25_000_000            # 解码前像素上限：超过即拒（解压炸弹防线）
CHUNK_SIZE = 64 * 1024             # 分块读取粒度

# Pillow 自带的解压炸弹防护默认只 warning 不拒；显式压低阈值，超限直接抛 DecompressionBombError
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def save_upload_image(data: bytes, filename: str) -> str:
    """保存用户上传的展示图，返回相对路径（如 /uploads/ab12cd34.jpg）。

    落盘前统一重编码为 JPEG，三个目的：
    1. 剥 EXIF——拍照原图的 EXIF 带 GPS 位置，属隐私红线，绝不原样留存；
    2. 压到最长边 MAX_EDGE + quality 85——展示图用不到原图尺寸，顺带缩体积；
    3. 炸弹图在解码前拦掉——见下方 size 检查的顺序注释。

    同步函数（Pillow 是 CPU 密集），由调用方用 asyncio.to_thread 包起来，
    避免阻塞事件循环。
    """
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise BizError(ErrorCode.PARAM_INVALID, "仅支持 jpg / png / webp 图片")
    if len(data) > MAX_BYTES:
        raise BizError(ErrorCode.PARAM_INVALID, "图片不能超过 2MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            # 顺序是关键：im.size 读的是文件头，不解码；必须在 im.load()（完整解码）之前查。
            # 反过来的话，一张 50000×50000 的炸弹图会先把内存撑爆才轮到检查。
            width, height = im.size
            if width * height > MAX_PIXELS:
                logger.warning("上传图片尺寸超限被拒: %sx%s", width, height)
                raise BizError(ErrorCode.PARAM_INVALID, "图片尺寸超出限制")
            im.load()  # 触发完整解码：改了扩展名的假文件在这里露馅
            # 先按 EXIF 方向转正，再重存——重存不带 exif，GPS 等元数据随之剥离
            im = ImageOps.exif_transpose(im) or im
            im = im.convert("RGB")
            im.thumbnail((MAX_EDGE, MAX_EDGE))
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=85, optimize=True, exif=b"")
    except BizError:
        raise
    except Exception as exc:
        # Pillow 打不开 = 内容不是真图片（改了扩展名的假文件），按参数错误拒绝
        raise BizError(ErrorCode.PARAM_INVALID, "图片文件无法解析") from exc

    # 原子写入：先写临时文件再 rename。直接写目标路径的话，进程崩在写的中途会留下
    # 半个文件，而 StaticFiles 会把它当正常图服务出去。
    name = f"{uuid4().hex}.jpg"
    tmp_path = UPLOAD_DIR / f".{name}.tmp"
    final_path = UPLOAD_DIR / name
    tmp_path.write_bytes(out.getvalue())
    os.replace(tmp_path, final_path)  # 同盘 rename，原子替换
    return f"/uploads/{name}"
