"""Internal storage and short-lived access to user-provided API keys.

Callers must authenticate the owner before passing a user ID to this service.
"""

import datetime
import logging
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.api_key_crypto import (
    FORMAT_VERSION,
    EncryptedBlob,
    KeyDecryptionError,
    KeyRing,
    decrypt_api_key,
    encrypt_api_key,
    new_dek,
    normalize_provider,
    unwrap_dek,
    wrap_dek,
)
from app.models import User, UserApiKey, UserKeyEnvelope


logger = logging.getLogger(__name__)
_ACTOR_RE = re.compile(r"(?:user:[1-9][0-9]*|service:[a-z][a-z0-9_-]{0,31})\Z", re.ASCII)


class KeyRecordError(Exception):
    """The requested user or API key record is unavailable."""


@dataclass(frozen=True)
class KeyMetadata:
    provider: str
    masked_key: str
    status: str
    create_time: datetime.datetime
    update_time: datetime.datetime


@dataclass
class KeyForCall:
    value: bytearray = field(repr=False)
    revision: str


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _validate_subject(user_id: int, actor: str) -> None:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
        raise ValueError("Invalid user ID")
    if not isinstance(actor, str) or not _ACTOR_RE.fullmatch(actor):
        raise ValueError("Invalid actor")


def _validate_key(api_key: str) -> bytes:
    if not isinstance(api_key, str) or len(api_key) < 8 or api_key.isspace():
        raise ValueError("Invalid API key")
    encoded = api_key.encode("utf-8")
    if len(encoded) > 4096:
        raise ValueError("Invalid API key")
    return encoded


def _envelope_blob(envelope: UserKeyEnvelope) -> EncryptedBlob:
    return EncryptedBlob(envelope.encrypted_dek, envelope.dek_nonce, envelope.dek_tag)


def _key_blob(key: UserApiKey) -> EncryptedBlob:
    return EncryptedBlob(key.encrypted_api_key, key.api_key_nonce, key.api_key_tag)


def _store_envelope(envelope: UserKeyEnvelope, blob: EncryptedBlob, kek_version: str, dek_version: int) -> None:
    envelope.encrypted_dek = blob.ciphertext
    envelope.dek_nonce = blob.nonce
    envelope.dek_tag = blob.tag
    envelope.kek_version = kek_version
    envelope.dek_version = dek_version
    envelope.format_version = FORMAT_VERSION
    envelope.update_time = _utc_now()


def _store_key(key: UserApiKey, blob: EncryptedBlob, dek_version: int) -> None:
    key.encrypted_api_key = blob.ciphertext
    key.api_key_nonce = blob.nonce
    key.api_key_tag = blob.tag
    key.dek_version = dek_version
    key.format_version = FORMAT_VERSION
    key.update_time = _utc_now()


class ApiKeyService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], ring: KeyRing):
        self._sessions = session_factory
        self._ring = ring

    def _audit(self, action: str, actor: str, user_id: int, provider: str | None, outcome: str, detail: str = "-") -> None:
        logger.info(
            "api_key.audit action=%s actor=%s user_id=%s provider=%s outcome=%s detail=%s",
            action, actor, user_id, provider or "-", outcome, detail,
        )

    async def _lock_user(self, db: AsyncSession, user_id: int) -> None:
        found = await db.scalar(select(User.id).where(User.id == user_id).with_for_update())
        if found is None:
            raise KeyRecordError("User unavailable")

    async def _envelope(self, db: AsyncSession, user_id: int) -> UserKeyEnvelope | None:
        return await db.scalar(select(UserKeyEnvelope).where(UserKeyEnvelope.user_id == user_id))

    async def save_key(self, user_id: int, provider: str, api_key: str, *, actor: str) -> None:
        _validate_subject(user_id, actor)
        provider = normalize_provider(provider)
        plaintext = bytearray(_validate_key(api_key))
        try:
            async with self._sessions() as db:
                async with db.begin():
                    await self._lock_user(db, user_id)
                    envelope = await self._envelope(db, user_id)
                    if envelope is None:
                        dek = new_dek()
                        envelope = UserKeyEnvelope(user_id=user_id, dek_version=1, format_version=FORMAT_VERSION)
                        _store_envelope(envelope, wrap_dek(self._ring, dek, user_id, 1), self._ring.active_version, 1)
                        db.add(envelope)
                        await db.flush()
                    else:
                        dek = unwrap_dek(self._ring, _envelope_blob(envelope), user_id, envelope.dek_version, envelope.kek_version, envelope.format_version)
                        if envelope.kek_version != self._ring.active_version:
                            _store_envelope(
                                envelope,
                                wrap_dek(self._ring, dek, user_id, envelope.dek_version),
                                self._ring.active_version,
                                envelope.dek_version,
                            )
                    key = await db.scalar(select(UserApiKey).where(UserApiKey.user_id == user_id, UserApiKey.provider == provider))
                    if key is None:
                        key = UserApiKey(user_id=user_id, provider=provider)
                        db.add(key)
                    _store_key(key, encrypt_api_key(dek, bytes(plaintext), user_id, provider, envelope.dek_version), envelope.dek_version)
                    key.key_suffix = api_key[-4:]
                    key.status = "active"
                    key.revision = uuid.uuid4().hex
            self._audit("save", actor, user_id, provider, "success", self._ring.active_version)
        except Exception as exc:
            self._audit("save", actor, user_id, provider, "failed", type(exc).__name__)
            raise
        finally:
            plaintext[:] = b"\x00" * len(plaintext)

    async def list_key_metadata(self, user_id: int, *, actor: str) -> list[KeyMetadata]:
        _validate_subject(user_id, actor)
        async with self._sessions() as db:
            rows = (await db.scalars(select(UserApiKey).where(UserApiKey.user_id == user_id).order_by(UserApiKey.provider))).all()
        self._audit("list", actor, user_id, None, "success")
        return [KeyMetadata(row.provider, "****" + row.key_suffix, row.status, row.create_time, row.update_time) for row in rows]

    async def delete_key(self, user_id: int, provider: str, *, actor: str) -> bool:
        _validate_subject(user_id, actor)
        provider = normalize_provider(provider)
        try:
            async with self._sessions() as db:
                async with db.begin():
                    await self._lock_user(db, user_id)
                    key = await db.scalar(select(UserApiKey).where(UserApiKey.user_id == user_id, UserApiKey.provider == provider))
                    deleted = key is not None
                    if key is not None:
                        await db.delete(key)
            self._audit("delete", actor, user_id, provider, "success" if deleted else "noop")
            return deleted
        except Exception as exc:
            self._audit("delete", actor, user_id, provider, "failed", type(exc).__name__)
            raise

    async def mark_invalid(self, user_id: int, provider: str, expected_revision: str, *, actor: str) -> bool:
        _validate_subject(user_id, actor)
        provider = normalize_provider(provider)
        if not isinstance(expected_revision, str) or not re.fullmatch(r"[0-9a-f]{32}", expected_revision):
            raise ValueError("Invalid revision")
        try:
            async with self._sessions() as db:
                async with db.begin():
                    await self._lock_user(db, user_id)
                    key = await db.scalar(select(UserApiKey).where(UserApiKey.user_id == user_id, UserApiKey.provider == provider))
                    changed = key is not None and key.revision == expected_revision and key.status == "active"
                    if changed:
                        key.status = "invalid"
                        key.update_time = _utc_now()
            self._audit("mark_invalid", actor, user_id, provider, "success" if changed else "noop")
            return changed
        except Exception as exc:
            self._audit("mark_invalid", actor, user_id, provider, "failed", type(exc).__name__)
            raise

    @asynccontextmanager
    async def key_for_call(self, user_id: int, provider: str, *, actor: str) -> AsyncIterator[KeyForCall]:
        _validate_subject(user_id, actor)
        provider = normalize_provider(provider)
        plaintext: bytearray | None = None
        try:
            try:
                async with self._sessions() as db:
                    row = (await db.execute(
                        select(UserKeyEnvelope, UserApiKey)
                        .join(UserApiKey, UserApiKey.user_id == UserKeyEnvelope.user_id)
                        .where(UserKeyEnvelope.user_id == user_id, UserApiKey.provider == provider)
                    )).first()
                    if row is None or row[1].status != "active":
                        raise KeyRecordError("API key unavailable")
                    envelope, key = row
                    if key.dek_version != envelope.dek_version:
                        raise KeyDecryptionError("Encrypted material unavailable")
                    dek = unwrap_dek(self._ring, _envelope_blob(envelope), user_id, envelope.dek_version, envelope.kek_version, envelope.format_version)
                    plaintext = bytearray(decrypt_api_key(dek, _key_blob(key), user_id, provider, key.dek_version, key.format_version))
                    revision = key.revision
                self._audit("use", actor, user_id, provider, "success", "model_call")
            except Exception as exc:
                self._audit("use", actor, user_id, provider, "failed", type(exc).__name__)
                raise
            yield KeyForCall(plaintext, revision)
        finally:
            if plaintext is not None:
                plaintext[:] = b"\x00" * len(plaintext)

    async def rewrap_user_dek(self, user_id: int, *, actor: str, target_kek_version: str | None = None) -> bool:
        _validate_subject(user_id, actor)
        version = target_kek_version or self._ring.active_version
        self._ring.key_for(version)
        try:
            async with self._sessions() as db:
                async with db.begin():
                    await self._lock_user(db, user_id)
                    envelope = await self._envelope(db, user_id)
                    changed = envelope is not None and envelope.kek_version != version
                    if changed:
                        dek = unwrap_dek(self._ring, _envelope_blob(envelope), user_id, envelope.dek_version, envelope.kek_version, envelope.format_version)
                        _store_envelope(envelope, wrap_dek(self._ring, dek, user_id, envelope.dek_version, version), version, envelope.dek_version)
            self._audit("rewrap_dek", actor, user_id, None, "success" if changed else "noop", version)
            return changed
        except Exception as exc:
            self._audit("rewrap_dek", actor, user_id, None, "failed", type(exc).__name__)
            raise

    async def rotate_user_dek(self, user_id: int, *, actor: str) -> bool:
        _validate_subject(user_id, actor)
        try:
            async with self._sessions() as db:
                async with db.begin():
                    await self._lock_user(db, user_id)
                    envelope = await self._envelope(db, user_id)
                    if envelope is None:
                        changed = False
                    else:
                        if envelope.dek_version >= 2_147_483_647:
                            raise KeyRecordError("DEK version unavailable")
                        old_dek = unwrap_dek(self._ring, _envelope_blob(envelope), user_id, envelope.dek_version, envelope.kek_version, envelope.format_version)
                        next_version = envelope.dek_version + 1
                        replacement = new_dek()
                        rows = (await db.scalars(select(UserApiKey).where(UserApiKey.user_id == user_id))).all()
                        for key in rows:
                            if key.dek_version != envelope.dek_version:
                                raise KeyDecryptionError("Encrypted material unavailable")
                            plaintext = bytearray(decrypt_api_key(old_dek, _key_blob(key), user_id, key.provider, key.dek_version, key.format_version))
                            try:
                                _store_key(key, encrypt_api_key(replacement, bytes(plaintext), user_id, key.provider, next_version), next_version)
                            finally:
                                plaintext[:] = b"\x00" * len(plaintext)
                        _store_envelope(envelope, wrap_dek(self._ring, replacement, user_id, next_version), self._ring.active_version, next_version)
                        changed = True
            self._audit("rotate_dek", actor, user_id, None, "success" if changed else "noop", self._ring.active_version)
            return changed
        except Exception as exc:
            self._audit("rotate_dek", actor, user_id, None, "failed", type(exc).__name__)
            raise
