"""Authenticated envelope encryption for user-provided API keys."""

import base64
import binascii
import json
import re
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


FORMAT_VERSION = 1
_NONCE_BYTES = 12
_TAG_BYTES = 16
_KEY_BYTES = 32
_VERSION_RE = re.compile(r"[A-Za-z0-9_-]{1,32}\Z", re.ASCII)
_PROVIDER_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z", re.ASCII)


class KeyConfigurationError(Exception):
    """The KEK ring is missing or unusable; details must stay out of logs."""


class KeyDecryptionError(Exception):
    """Stored encrypted material failed authentication or format checks."""


@dataclass(frozen=True)
class EncryptedBlob:
    ciphertext: str
    nonce: str
    tag: str


def normalize_provider(provider: str) -> str:
    if not isinstance(provider, str):
        raise ValueError("Invalid provider")
    normalized = provider.lower()
    if not _PROVIDER_RE.fullmatch(normalized):
        raise ValueError("Invalid provider")
    return normalized


def _aad(*parts: str | int) -> bytes:
    return json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode(data: str) -> bytes:
    return base64.b64decode(data, validate=True)


def _encrypt(key: bytes, plaintext: bytes, aad: bytes) -> EncryptedBlob:
    nonce = secrets.token_bytes(_NONCE_BYTES)
    combined = AESGCM(key).encrypt(nonce, plaintext, aad)
    return EncryptedBlob(_encode(combined[:-_TAG_BYTES]), _encode(nonce), _encode(combined[-_TAG_BYTES:]))


def _decrypt(key: bytes, blob: EncryptedBlob, aad: bytes) -> bytes:
    try:
        nonce, tag, ciphertext = _decode(blob.nonce), _decode(blob.tag), _decode(blob.ciphertext)
        if len(nonce) != _NONCE_BYTES or len(tag) != _TAG_BYTES:
            raise ValueError("Invalid encrypted material")
        return AESGCM(key).decrypt(nonce, ciphertext + tag, aad)
    except (InvalidTag, ValueError, TypeError, binascii.Error):
        raise KeyDecryptionError("Encrypted material unavailable") from None


def new_dek() -> bytes:
    return secrets.token_bytes(_KEY_BYTES)


class KeyRing:
    def __init__(self, encoded_keys: dict[str, str], active_version: str):
        try:
            if not encoded_keys or not isinstance(active_version, str):
                raise ValueError
            if any(not isinstance(version, str) or not _VERSION_RE.fullmatch(version) for version in encoded_keys):
                raise ValueError
            keys = {version: _decode(encoded) for version, encoded in encoded_keys.items()}
            if any(len(key) != _KEY_BYTES for key in keys.values()) or active_version not in keys:
                raise ValueError
        except (ValueError, TypeError, binascii.Error):
            raise KeyConfigurationError("API key encryption is not configured") from None
        self._keys = keys
        self.active_version = active_version

    @classmethod
    def from_settings(cls, settings: object) -> "KeyRing":
        try:
            secret = getattr(settings, "api_key_keks")
            active = getattr(settings, "api_key_active_kek_version")
            if secret is None:
                raise ValueError
            pairs = json.loads(secret.get_secret_value(), object_pairs_hook=_unique_pairs)
            if not isinstance(pairs, dict):
                raise ValueError
            return cls(pairs, active)
        except (AttributeError, ValueError, TypeError, json.JSONDecodeError, KeyConfigurationError):
            raise KeyConfigurationError("API key encryption is not configured") from None

    def key_for(self, version: str) -> bytes:
        try:
            return self._keys[version]
        except (KeyError, TypeError):
            raise KeyConfigurationError("API key encryption is not configured") from None


def _unique_pairs(pairs: list[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def wrap_dek(ring: KeyRing, dek: bytes, user_id: int, dek_version: int, kek_version: str | None = None) -> EncryptedBlob:
    if len(dek) != _KEY_BYTES:
        raise ValueError("Invalid DEK")
    version = kek_version or ring.active_version
    return _encrypt(ring.key_for(version), dek, _aad("dek", FORMAT_VERSION, user_id, dek_version, version))


def unwrap_dek(ring: KeyRing, blob: EncryptedBlob, user_id: int, dek_version: int, kek_version: str, format_version: int) -> bytes:
    if format_version != FORMAT_VERSION:
        raise KeyDecryptionError("Encrypted material unavailable")
    dek = _decrypt(ring.key_for(kek_version), blob, _aad("dek", format_version, user_id, dek_version, kek_version))
    if len(dek) != _KEY_BYTES:
        raise KeyDecryptionError("Encrypted material unavailable")
    return dek


def encrypt_api_key(dek: bytes, api_key: bytes, user_id: int, provider: str, dek_version: int) -> EncryptedBlob:
    return _encrypt(dek, api_key, _aad("api-key", FORMAT_VERSION, user_id, normalize_provider(provider), dek_version))


def decrypt_api_key(dek: bytes, blob: EncryptedBlob, user_id: int, provider: str, dek_version: int, format_version: int) -> bytes:
    if format_version != FORMAT_VERSION:
        raise KeyDecryptionError("Encrypted material unavailable")
    try:
        normalized = normalize_provider(provider)
    except ValueError:
        raise KeyDecryptionError("Encrypted material unavailable") from None
    return _decrypt(dek, blob, _aad("api-key", format_version, user_id, normalized, dek_version))
