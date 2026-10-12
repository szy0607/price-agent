import io
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from app.core.errors import BizError, ErrorCode

# 用户上传图片的落地目录：项目根 uploads/，由 main.py 经 StaticFiles 挂到 /uploads
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_BYTES = 2 * 1024 * 1024
_MAX_EDGE = 1280


def save_upload_image(data: bytes, filename: str) -> str:
    """保存用户上传的展示图，返回相对路径（如 /uploads/ab12cd34.jpg）。

    落盘前统一重编码为 JPEG，两个目的：
    1. 剥 EXIF——拍照原图的 EXIF 带 GPS 位置，属隐私红线，绝不原样留存；
    2. 压到最长边 1280 + quality 85——展示图用不到原图尺寸，顺带缩体积。

    同步函数（Pillow 是 CPU 密集），由调用方用 asyncio.to_thread 包起来，
    避免阻塞事件循环。
    """
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise BizError(ErrorCode.PARAM_INVALID, "仅支持 jpg / png / webp 图片")
    if len(data) > _MAX_BYTES:
        raise BizError(ErrorCode.PARAM_INVALID, "图片不能超过 2MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()  # 触发完整解码：改了扩展名的假文件在这里露馅
            # 先按 EXIF 方向转正，再重存——重存不带 exif，GPS 等元数据随之剥离
            im = ImageOps.exif_transpose(im) or im
            im = im.convert("RGB")
            im.thumbnail((_MAX_EDGE, _MAX_EDGE))
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=85, optimize=True, exif=b"")
    except Exception as exc:
        # Pillow 打不开 = 内容不是真图片（改了扩展名的假文件），按参数错误拒绝
        raise BizError(ErrorCode.PARAM_INVALID, "图片文件无法解析") from exc

    name = f"{uuid4().hex}.jpg"
    (UPLOAD_DIR / name).write_bytes(out.getvalue())
    return f"/uploads/{name}"
