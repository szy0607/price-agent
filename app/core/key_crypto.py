"""User model API key 的加密存取（AES-256-GCM，单层 KEK）。

存储格式：base64(nonce[12字节] || ciphertext+tag)，落 user_api_key.encrypted_key。
KEK 从 .env 的 API_KEY_KEK 读取：base64 编码的 32 字节随机数（AES-256）。
所有失败（KEK 未配/格式错、payload 坏、tag 校验不过）统一抛 ValueError。
"""
import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_NONCE_LEN = 12  # AES-GCM 标准 96-bit nonce，同一 KEK 下绝不能复用
_KEY_LEN = 32    # AES-256 要求 32 字节


def _load_kek() -> bytes:
    value = settings.api_key_kek
    if not value:
        raise ValueError("API_KEY_KEK is not configured")
    try:
        key = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ValueError("API_KEY_KEK is not valid base64") from exc
    if len(key) != _KEY_LEN:
        raise ValueError("API_KEY_KEK must decode to 32 bytes")
    return key


def encrypt(plain: str) -> str:
    """明文 key -> 可落库的密文串。每次调用 nonce 不同，同明文产生不同密文。"""
    nonce = os.urandom(_NONCE_LEN)
    sealed = AESGCM(_load_kek()).encrypt(nonce, plain.encode("utf-8"), None)
    return base64.b64encode(nonce + sealed).decode("ascii")


def decrypt(stored: str) -> str:
    """库里的密文串 -> 明文 key。密文或 tag 被改动过则抛 ValueError。"""
    try:
        raw = base64.b64decode(stored, validate=True)
    except ValueError as exc:
        raise ValueError("Invalid encrypted payload") from exc
    if len(raw) <= _NONCE_LEN:
        raise ValueError("Invalid encrypted payload")
    nonce, sealed = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    try:
        plain = AESGCM(_load_kek()).decrypt(nonce, sealed, None)
    except InvalidTag as exc:
        raise ValueError("Invalid encrypted payload") from exc
    return plain.decode("utf-8")
