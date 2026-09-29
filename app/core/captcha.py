"""自研无状态图形验证码 —— 全项目唯一出处。

设计口径见 `docs/用户注册与登录-接口契约.md` §2.5：

    token = f"{salt}.{ts}.{sig}"
    sig   = hmac_sha256(CAPTCHA_KEY, f"{salt}.{ts}.{正确答案}")

**答案不出后端**：token 里只有签名，前端解开也拿不到答案。
校验时后端拿用户输入重算一遍 sig 比对即可 —— 所以**全程不需要任何存储**（不依赖 Redis、不写库）。

一次性靠 **120 秒时间窗**，不是靠"服务端用过即删"。
"""

import base64
import hashlib
import hmac
import io
import secrets
import time

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.core.errors import BizError, ErrorCode

# token 有效期（秒）。无状态方案无法"作废"已签发的 token，只能靠它兜住重放。
CAPTCHA_TTL = 120

# 字符集：去掉易混的 I / O（像 1、0），数字只用 2-9 → 24 + 8 = 32 个字符
# 答案空间 = 32^4 ≈ 105 万，盲猜通过率约百万分之一
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 4

_IMG_W, _IMG_H = 160, 56
_FONT_SIZE = 28

# 对外统一文案：格式错 / 过期 / 答案错 **一律这一句**，不区分原因。
# 区分只对攻击者有用（帮他把"猜答案"和"猜时限"分开调参）。
_FAIL_MSG = "人机验证失败，请重试"

# 内置字体：零外部字体依赖。
# ⚠️ 别改成 ImageFont.truetype("C:/Windows/Fonts/...") —— 本地能跑，
#    Linux 部署时那个路径不存在会直接崩。
_FONT = ImageFont.load_default(size=_FONT_SIZE)


def _make_code() -> str:
    """生成 4 位字符码（大写）。"""
    return "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))


def _render(code: str) -> str:
    """把验证码画成 PNG，返回可直接塞进 <img src> 的 data URI。"""
    img = Image.new("RGB", (_IMG_W, _IMG_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 干扰线：4 条浅灰，压住底纹但不盖字
    for _ in range(4):
        draw.line(
            (
                secrets.randbelow(_IMG_W),
                secrets.randbelow(_IMG_H),
                secrets.randbelow(_IMG_W),
                secrets.randbelow(_IMG_H),
            ),
            fill=(190, 200, 210),
            width=1,
        )

    # 逐字符画：每个字符随机上下浮动，比整串画难 OCR 一点。
    # anchor="lm" = 以字符左侧中线为锚点，省得手算偏移。
    x = 16
    for ch in code:
        y = _IMG_H // 2 + secrets.randbelow(9) - 4
        draw.text((x, y), ch, font=_FONT, fill=(28, 32, 38), anchor="lm")
        x += 32

    # 噪点
    for _ in range(40):
        draw.point(
            (secrets.randbelow(_IMG_W), secrets.randbelow(_IMG_H)),
            fill=(150, 160, 170),
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def create_captcha() -> tuple[str, str]:
    """生成一次验证码，返回 `(captcha_token, image_data_uri)`。

    `salt` 每次随机是硬要求：少了它，sig 就直接等于「答案查表」→ 彩虹表秒破。
    """
    answer = _make_code()

    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    sig = hmac.new(
        settings.captcha_key.encode(),
        f"{salt}.{ts}.{answer}".encode(),
        hashlib.sha256,
    ).hexdigest()

    return f"{salt}.{ts}.{sig}", _render(answer)


def verify_captcha(captcha_token: str, user_input: str) -> None:
    """校验验证码；不通过一律 `raise BizError(40002)`。

    三种失败（token 格式错 / 已过期 / 答案不对）**对外是同一句文案**。

    ⚠️ 必须在登录流程里**任何数据库操作之前**调用 —— 见契约 §2.2 的「顺序即安全边界」。
    """
    try:
        salt, ts, sig = captcha_token.split(".")
        issued_at = int(ts)
    except ValueError:
        raise BizError(ErrorCode.CAPTCHA_INVALID, _FAIL_MSG)

    if int(time.time()) - issued_at > CAPTCHA_TTL:
        raise BizError(ErrorCode.CAPTCHA_INVALID, _FAIL_MSG)

    # 统一转大写再比：用户输小写不该被判错（字符集本身只有大写）
    answer = user_input.strip().upper()

    expect = hmac.new(
        settings.captcha_key.encode(),
        f"{salt}.{ts}.{answer}".encode(),
        hashlib.sha256,
    ).hexdigest()

    # 常量时间比对：普通 `==` 是短路比较、逐字节提前返回，会泄露时序侧信道
    if not hmac.compare_digest(expect, sig):
        raise BizError(ErrorCode.CAPTCHA_INVALID, _FAIL_MSG)
