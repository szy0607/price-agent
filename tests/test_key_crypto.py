"""key_crypto 单元测试：不需要数据库，纯内存跑。"""
import base64

import pytest

from app.core import key_crypto
from app.core.config import settings

GOOD_KEK = base64.b64encode(b"1" * 32).decode()


@pytest.fixture(autouse=True)
def _use_good_kek(monkeypatch):
    monkeypatch.setattr(settings, "api_key_kek", GOOD_KEK)


def test_roundtrip():
    token = "sk-test-abcdef123456"
    stored = key_crypto.encrypt(token)
    assert key_crypto.decrypt(stored) == token


def test_same_plaintext_yields_different_ciphertext():
    assert key_crypto.encrypt("same-key") != key_crypto.encrypt("same-key")


def test_tampered_payload_rejected():
    stored = bytearray(key_crypto.encrypt("sk-test"), "ascii")
    stored[-1] ^= 0xFF  # 翻转最后一个字节，模拟密文被篡改
    with pytest.raises(ValueError):
        key_crypto.decrypt(bytes(stored).decode())


def test_short_payload_rejected():
    with pytest.raises(ValueError):
        key_crypto.decrypt(base64.b64encode(b"junk").decode())


def test_kek_missing_rejected(monkeypatch):
    monkeypatch.setattr(settings, "api_key_kek", None)
    with pytest.raises(ValueError):
        key_crypto.encrypt("sk-test")


def test_kek_wrong_length_rejected(monkeypatch):
    monkeypatch.setattr(settings, "api_key_kek", base64.b64encode(b"1" * 16).decode())
    with pytest.raises(ValueError):
        key_crypto.encrypt("sk-test")
