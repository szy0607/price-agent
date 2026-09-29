"""MySQL integration tests; run after migrating a disposable local test database."""

import asyncio
import base64
import os
import secrets
import uuid

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.core.api_key_crypto import KeyDecryptionError, KeyRing, decrypt_api_key, unwrap_dek
from app.core.config import settings
from app.core.security import hash_password
from app.database.session import async_engine, async_session_local
from app.main import app
from app.models import User, UserApiKey, UserKeyEnvelope, UserSession
from app.services.api_key_service import ApiKeyService, KeyRecordError
from app.services import chat_service


pytestmark = pytest.mark.asyncio(loop_scope="module")
ACTOR = "service:test"


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def dispose_test_engine():
    yield
    await async_engine.dispose()


def _ring(active: str = "v1") -> KeyRing:
    return KeyRing({
        "v1": base64.b64encode(b"1" * 32).decode(),
        "v2": base64.b64encode(b"2" * 32).decode(),
    }, active)


@pytest_asyncio.fixture(loop_scope="module")
async def user_ids():
    if os.getenv("RUN_MYSQL_KEY_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_KEY_TESTS=1 on a migrated disposable MySQL database")
    ids = []
    try:
        async with async_session_local() as db:
            async with db.begin():
                for _ in range(2):
                    user = User(user_email=f"api-key-test-{uuid.uuid4().hex}@example.invalid", username="api-key-test", password_hash="unused")
                    db.add(user)
                    await db.flush()
                    ids.append(user.id)
        yield ids
    finally:
        async with async_session_local() as db:
            async with db.begin():
                await db.execute(delete(UserSession).where(UserSession.user_id.in_(ids)))
                await db.execute(delete(User).where(User.id.in_(ids)))


async def _rows(user_id: int):
    async with async_session_local() as db:
        envelope = await db.scalar(select(UserKeyEnvelope).where(UserKeyEnvelope.user_id == user_id))
        keys = (await db.scalars(select(UserApiKey).where(UserApiKey.user_id == user_id).order_by(UserApiKey.provider))).all()
        return envelope, keys


async def test_storage_metadata_and_ownership(user_ids):
    first, second = user_ids
    service = ApiKeyService(async_session_local, _ring())
    await service.save_key(first, "OpenAI", "sk-test-secret-aaaa", actor=ACTOR)
    await service.save_key(second, "openai", "sk-test-secret-bbbb", actor=ACTOR)
    first_envelope, first_keys = await _rows(first)
    second_envelope, _ = await _rows(second)
    assert first_envelope.encrypted_dek != second_envelope.encrypted_dek
    assert first_keys[0].encrypted_api_key != "sk-test-secret-aaaa"
    assert "sk-test-secret-aaaa" not in repr(first_keys[0].__dict__)
    assert [item.masked_key for item in await service.list_key_metadata(first, actor=ACTOR)] == ["****aaaa"]
    async with service.key_for_call(first, "openai", actor=ACTOR) as borrowed:
        assert bytes(borrowed.value) == b"sk-test-secret-aaaa"
        revision = borrowed.revision
    assert not any(borrowed.value)
    await service.save_key(first, "openai", "sk-test-secret-cccc", actor=ACTOR)
    assert not await service.mark_invalid(first, "openai", revision, actor=ACTOR)
    async with service.key_for_call(first, "openai", actor=ACTOR) as borrowed:
        assert bytes(borrowed.value) == b"sk-test-secret-cccc"


async def test_rewrap_and_dek_rotation_include_invalid_keys(user_ids):
    user_id = user_ids[0]
    service = ApiKeyService(async_session_local, _ring())
    await service.save_key(user_id, "openai", "sk-test-secret-aaaa", actor=ACTOR)
    await service.save_key(user_id, "anthropic", "sk-test-secret-bbbb", actor=ACTOR)
    async with service.key_for_call(user_id, "anthropic", actor=ACTOR) as borrowed:
        revision = borrowed.revision
    assert await service.mark_invalid(user_id, "anthropic", revision, actor=ACTOR)
    original_envelope, original_keys = await _rows(user_id)
    old_ciphertext = {key.provider: key.encrypted_api_key for key in original_keys}
    rotated_ring = _ring("v2")
    rotated = ApiKeyService(async_session_local, rotated_ring)
    assert await rotated.rewrap_user_dek(user_id, actor=ACTOR)
    assert not await rotated.rewrap_user_dek(user_id, actor=ACTOR)
    rewrapped_envelope, rewrapped_keys = await _rows(user_id)
    assert rewrapped_envelope.kek_version == "v2"
    assert rewrapped_envelope.encrypted_dek != original_envelope.encrypted_dek
    assert {key.provider: key.encrypted_api_key for key in rewrapped_keys} == old_ciphertext
    new_only = ApiKeyService(async_session_local, KeyRing({"v2": base64.b64encode(b"2" * 32).decode()}, "v2"))
    async with new_only.key_for_call(user_id, "openai", actor=ACTOR) as borrowed:
        assert bytes(borrowed.value) == b"sk-test-secret-aaaa"
    assert await rotated.rotate_user_dek(user_id, actor=ACTOR)
    envelope, keys = await _rows(user_id)
    assert envelope.dek_version == 2
    assert {key.dek_version for key in keys} == {2}
    assert {key.status for key in keys} == {"active", "invalid"}
    assert {key.provider: key.encrypted_api_key for key in keys} != old_ciphertext
    dek = unwrap_dek(rotated_ring, _blob(envelope.encrypted_dek, envelope.dek_nonce, envelope.dek_tag), user_id, 2, "v2", 1)
    assert {key.provider: decrypt_api_key(dek, _blob(key.encrypted_api_key, key.api_key_nonce, key.api_key_tag), user_id, key.provider, 2, 1) for key in keys} == {
        "anthropic": b"sk-test-secret-bbbb", "openai": b"sk-test-secret-aaaa",
    }
    with pytest.raises(KeyRecordError):
        async with rotated.key_for_call(user_id, "anthropic", actor=ACTOR):
            pass


def _blob(ciphertext, nonce, tag):
    from app.core.api_key_crypto import EncryptedBlob
    return EncryptedBlob(ciphertext, nonce, tag)


async def test_rotation_failure_rolls_back_and_concurrent_first_writes(user_ids):
    user_id = user_ids[0]
    service = ApiKeyService(async_session_local, _ring())
    await asyncio.gather(
        service.save_key(user_id, "openai", "sk-test-secret-aaaa", actor=ACTOR),
        service.save_key(user_id, "anthropic", "sk-test-secret-bbbb", actor=ACTOR),
    )
    envelope, keys = await _rows(user_id)
    assert len(keys) == 2
    assert {key.dek_version for key in keys} == {envelope.dek_version}
    async with async_session_local() as db:
        async with db.begin():
            key = await db.scalar(select(UserApiKey).where(UserApiKey.user_id == user_id, UserApiKey.provider == "openai"))
            key.api_key_tag = base64.b64encode(secrets.token_bytes(16)).decode()
    before_envelope, before_keys = await _rows(user_id)
    with pytest.raises(KeyDecryptionError):
        await service.rotate_user_dek(user_id, actor=ACTOR)
    after_envelope, after_keys = await _rows(user_id)
    assert after_envelope.dek_version == before_envelope.dek_version
    assert [(key.provider, key.encrypted_api_key, key.dek_version) for key in after_keys] == [
        (key.provider, key.encrypted_api_key, key.dek_version) for key in before_keys
    ]


async def test_save_rotate_and_invalid_mark_do_not_lose_updates(user_ids):
    user_id = user_ids[0]
    service = ApiKeyService(async_session_local, _ring())
    await service.save_key(user_id, "openai", "sk-test-secret-aaaa", actor=ACTOR)
    async with service.key_for_call(user_id, "openai", actor=ACTOR) as borrowed:
        revision = borrowed.revision
    await asyncio.gather(
        service.rotate_user_dek(user_id, actor=ACTOR),
        service.mark_invalid(user_id, "openai", revision, actor=ACTOR),
        service.save_key(user_id, "anthropic", "sk-test-secret-bbbb", actor=ACTOR),
    )
    envelope, keys = await _rows(user_id)
    assert {key.dek_version for key in keys} == {envelope.dek_version}
    assert {key.provider: key.status for key in keys} == {"anthropic": "active", "openai": "invalid"}
    async with service.key_for_call(user_id, "anthropic", actor=ACTOR) as borrowed:
        assert bytes(borrowed.value) == b"sk-test-secret-bbbb"


async def test_delete_and_save_are_serialized(user_ids):
    user_id = user_ids[0]
    service = ApiKeyService(async_session_local, _ring())
    await service.save_key(user_id, "openai", "sk-test-secret-aaaa", actor=ACTOR)
    await asyncio.gather(
        service.delete_key(user_id, "openai", actor=ACTOR),
        service.save_key(user_id, "openai", "sk-test-secret-bbbb", actor=ACTOR),
    )
    envelope, keys = await _rows(user_id)
    assert len(keys) <= 1
    if keys:
        assert keys[0].dek_version == envelope.dek_version
        async with service.key_for_call(user_id, "openai", actor=ACTOR) as borrowed:
            assert bytes(borrowed.value) == b"sk-test-secret-bbbb"


async def test_settings_http_requires_session_and_keeps_users_separate(user_ids, monkeypatch):
    monkeypatch.setattr(settings, "api_key_keks", SecretStr('{"v1":"' + base64.b64encode(b"1" * 32).decode() + '"}'))
    monkeypatch.setattr(settings, "api_key_active_kek_version", "v1")
    password = "testPassword123"
    async with async_session_local() as db:
        async with db.begin():
            users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
            emails = {user.id: user.user_email for user in users}
            for user in users:
                user.password_hash = hash_password(password)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as first, AsyncClient(transport=transport, base_url="http://testserver") as second:
        response = await first.get("/settings/api-keys")
        assert response.status_code == 401
        response = await first.post("/auth/login", json={"user_email": emails[user_ids[0]], "password": password})
        assert response.status_code == 200
        assert "httponly" in response.headers["set-cookie"].lower()
        profile = (await first.get("/auth/me")).json()["data"]
        assert profile["id"] == user_ids[0]
        assert "password_hash" not in profile
        response = await first.put("/settings/api-keys/openai", json={"api_key": "sk-test-secret-aaaa"})
        assert response.status_code == 400
        response = await first.put(
            "/settings/api-keys/openai",
            json={"api_key": "sk-test-secret-aaaa"},
            headers={"X-Requested-With": "price-agent"},
        )
        assert response.status_code == 200
        assert "sk-test-secret-aaaa" not in response.text
        own_rows = (await first.get("/settings/api-keys")).json()["data"]
        assert own_rows[0]["masked_key"] == "****aaaa"
        assert "sk-test-secret-aaaa" not in repr(own_rows)

        response = await second.post("/auth/login", json={"user_email": emails[user_ids[1]], "password": password})
        assert response.status_code == 200
        assert (await second.get("/settings/api-keys")).json()["data"] == []
        response = await first.post("/auth/logout", headers={"X-Requested-With": "price-agent"})
        assert response.status_code == 200
        assert (await first.get("/settings/api-keys")).status_code == 401


async def test_chat_uses_only_selected_users_key(user_ids, monkeypatch):
    monkeypatch.setattr(settings, "api_key_keks", SecretStr('{"v1":"' + base64.b64encode(b"1" * 32).decode() + '"}'))
    monkeypatch.setattr(settings, "api_key_active_kek_version", "v1")
    password = "testPassword123"
    async with async_session_local() as db:
        async with db.begin():
            users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()
            emails = {user.id: user.user_email for user in users}
            for user in users:
                user.password_hash = hash_password(password)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as first, AsyncClient(transport=transport, base_url="http://testserver") as second:
        assert (await first.post("/chat/message", json={"messages": [{"role": "user", "content": "hello"}]}, headers={"X-Requested-With": "price-agent"})).status_code == 401
        for client, user_id in ((first, user_ids[0]), (second, user_ids[1])):
            response = await client.post("/auth/login", json={"user_email": emails[user_id], "password": password})
            assert response.status_code == 200
        for client, key in ((first, "sk-test-first-aaaa"), (second, "sk-test-second-bbbb")):
            response = await client.put("/settings/api-keys/openai", json={"api_key": key}, headers={"X-Requested-With": "price-agent"})
            assert response.status_code == 200

        assert (await first.post("/chat/message", json={"messages": [{"role": "user", "content": "hello"}]}, headers={"X-Requested-With": "price-agent"})).status_code == 400
        assert (await first.put("/settings/model", json={"provider": "openai"}, headers={"X-Requested-With": "price-agent"})).status_code == 200
        assert (await first.get("/settings/model")).json()["data"]["provider"] == "openai"

        original_client = httpx.AsyncClient
        upstream_status = 200
        expected_provider = "openai"

        def handler(request):
            if expected_provider == "anthropic":
                assert str(request.url) == "https://api.anthropic.com/v1/messages"
                assert request.headers["x-api-key"] == "sk-test-first-cccc"
            else:
                assert str(request.url) == "https://api.openai.com/v1/chat/completions"
                assert request.headers["authorization"] == "Bearer sk-test-first-aaaa"
            assert b"sk-test-first-aaaa" not in request.content
            if upstream_status == 401:
                return httpx.Response(401, json={"error": "rejected"})
            if expected_provider == "anthropic":
                return httpx.Response(200, json={"content": [{"type": "text", "text": "Anthropic 的回复"}]})
            return httpx.Response(200, json={"choices": [{"message": {"content": "来自用户模型的回复"}}]})

        monkeypatch.setattr(chat_service.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
        request = {"messages": [{"role": "user", "content": "推荐耳机"}]}
        response = await first.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})
        assert response.status_code == 200
        assert response.json()["data"]["content"] == "来自用户模型的回复"
        assert "sk-test-first-aaaa" not in response.text
        assert (await second.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})).status_code == 400

        await first.put("/settings/api-keys/anthropic", json={"api_key": "sk-test-first-cccc"}, headers={"X-Requested-With": "price-agent"})
        assert (await first.put("/settings/model", json={"provider": "anthropic"}, headers={"X-Requested-With": "price-agent"})).status_code == 200
        expected_provider = "anthropic"
        response = await first.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})
        assert response.status_code == 200
        assert response.json()["data"]["content"] == "Anthropic 的回复"

        await first.put("/settings/model", json={"provider": "openai"}, headers={"X-Requested-With": "price-agent"})
        expected_provider = "openai"

        upstream_status = 401
        response = await first.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})
        assert response.status_code == 500
        assert {row["provider"]: row["status"] for row in (await first.get("/settings/api-keys")).json()["data"]}["openai"] == "invalid"
        await first.delete("/settings/api-keys/openai", headers={"X-Requested-With": "price-agent"})
        assert (await first.get("/settings/model")).json()["data"]["provider"] is None
