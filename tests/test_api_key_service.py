"""MySQL integration tests; run after migrating a disposable local test database."""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
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


def _login_payload(email: str, password: str) -> dict:
    """/auth/login 必带人机验证，这里自己签一个有效 token。

    口径见 `app/core/captcha.py`：`sig = hmac_sha256(CAPTCHA_KEY, f"{salt}.{ts}.{答案}")`，
    答案就是提交的那个串。比 mock 掉 `verify_captcha` 好 —— 走的是真登录链路，
    签名口径一旦改了这里会直接失败，而不是悄悄放过。
    """
    salt = secrets.token_hex(8)
    ts = str(int(time.time()))
    answer = "TEST23"
    sig = hmac.new(settings.captcha_key.encode(), f"{salt}.{ts}.{answer}".encode(), hashlib.sha256).hexdigest()
    return {
        "user_email": email,
        "password": password,
        "captcha_token": f"{salt}.{ts}.{sig}",
        "captcha_code": answer,
    }


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
    assert [item.model_name for item in await service.list_key_metadata(first, actor=ACTOR)] == [None]
    async with service.key_for_call(first, "openai", actor=ACTOR) as borrowed:
        assert bytes(borrowed.value) == b"sk-test-secret-aaaa"
        assert borrowed.model_name is None
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
        response = await first.post("/auth/login", json=_login_payload(emails[user_ids[0]], password))
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

        response = await second.post("/auth/login", json=_login_payload(emails[user_ids[1]], password))
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
            response = await client.post("/auth/login", json=_login_payload(emails[user_id], password))
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
        sent_models = []

        def handler(request):
            sent_models.append(json.loads(request.content)["model"])
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
        # 没有自选模型时回落服务商默认，且请求体和响应报出的是同一个名字
        assert sent_models == ["gpt-4o-mini"]
        assert response.json()["data"]["model"] == "gpt-4o-mini"
        assert "sk-test-first-aaaa" not in response.text
        assert (await second.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})).status_code == 400

        # 用户自选模型：请求体带模型名，响应报出的也是它，不再是写死的默认值
        assert (await first.put("/settings/model", json={"provider": "openai", "model_name": "gpt-4o"}, headers={"X-Requested-With": "price-agent"})).status_code == 200
        response = await first.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})
        assert response.json()["data"]["model"] == "gpt-4o"
        assert sent_models[-1] == "gpt-4o"
        assert (await first.get("/settings/model")).json()["data"]["model_name"] == "gpt-4o"
        own_rows = (await first.get("/settings/api-keys")).json()["data"]
        assert {row["provider"]: row["model_name"] for row in own_rows}["openai"] == "gpt-4o"

        await first.put("/settings/api-keys/anthropic", json={"api_key": "sk-test-first-cccc"}, headers={"X-Requested-With": "price-agent"})
        assert (await first.put("/settings/model", json={"provider": "anthropic", "model_name": "claude-3-5-haiku-latest"}, headers={"X-Requested-With": "price-agent"})).status_code == 200
        expected_provider = "anthropic"
        response = await first.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})
        assert response.status_code == 200
        assert response.json()["data"]["content"] == "Anthropic 的回复"
        assert response.json()["data"]["model"] == "claude-3-5-haiku-latest"
        assert sent_models[-1] == "claude-3-5-haiku-latest"
        # 每个厂商各记一个：切到 anthropic 之后，openai 那份选择还在
        saved = {row["provider"]: row["saved_model"] for row in (await first.get("/settings/model")).json()["data"]["options"]}
        assert saved == {"openai": "gpt-4o", "anthropic": "claude-3-5-haiku-latest", "deepseek": None, "qwen": None}

        # 只传服务商 = 不传模型名 = 清空该厂商的选择，回落默认
        assert (await first.put("/settings/model", json={"provider": "openai"}, headers={"X-Requested-With": "price-agent"})).status_code == 200
        assert (await first.get("/settings/model")).json()["data"]["model_name"] == "gpt-4o-mini"
        expected_provider = "openai"
        assert (await first.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})).status_code == 200
        assert sent_models[-1] == "gpt-4o-mini"
        assert (await first.put("/settings/model", json={"provider": "openai", "model_name": "gpt-4o"}, headers={"X-Requested-With": "price-agent"})).status_code == 200

        upstream_status = 401
        response = await first.post("/chat/message", json=request, headers={"X-Requested-With": "price-agent"})
        assert response.status_code == 500
        api_keys = {row["provider"]: row for row in (await first.get("/settings/api-keys")).json()["data"]}
        assert api_keys["openai"]["status"] == "invalid"
        # Key 被判失效不该顺手清掉用户的模型选择
        assert api_keys["openai"]["model_name"] == "gpt-4o"
        await first.delete("/settings/api-keys/openai", headers={"X-Requested-With": "price-agent"})
        assert (await first.get("/settings/model")).json()["data"]["provider"] is None


async def test_provider_model_listing_and_model_name_rules(user_ids, monkeypatch):
    """用用户自己的 Key 向厂商拉模型列表，以及模型名的存储规则。"""
    monkeypatch.setattr(settings, "api_key_keks", SecretStr('{"v1":"' + base64.b64encode(b"1" * 32).decode() + '"}'))
    monkeypatch.setattr(settings, "api_key_active_kek_version", "v1")
    password = "testPassword123"
    async with async_session_local() as db:
        async with db.begin():
            owner = await db.get(User, user_ids[0])
            owner.password_hash = hash_password(password)
            email = owner.user_email

    write = {"X-Requested-With": "price-agent"}
    listing_status = 200
    listing_body = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}, {"id": "text-embedding-3-small"}, {"id": "whisper-1"}, {"id": "gpt-4o-audio-preview"}]}
    calls = []
    original_client = httpx.AsyncClient
    anthropic_models_url = chat_service.MODEL_PROVIDERS["anthropic"]["models_url"]

    def handler(request):
        calls.append(str(request.url))
        # 用前缀比而不是全等：Anthropic 那趟我们**故意**带 ?limit=100（只取一页），
        # 全等会让它掉进下面的 Bearer 分支，断言鉴权头时炸掉。
        if str(request.url).startswith(anthropic_models_url):
            assert request.headers["x-api-key"] == "sk-listing-aaaa"
            assert request.url.params["limit"] == "100"
            # 带 has_more 也只取一页，不翻第二页
            return httpx.Response(200, json={"data": [{"id": "claude-haiku-4-5", "display_name": "Claude Haiku"}], "has_more": True, "next_page": "cursor-2"})
        assert request.headers["authorization"] == "Bearer sk-listing-aaaa", str(request.url)
        if listing_status == 401:
            return httpx.Response(401, json={"error": "rejected"})
        if listing_status == 302:
            return httpx.Response(302, headers={"location": "https://elsewhere.example/models"}, json=listing_body)
        if listing_status == 404:
            return httpx.Response(404, json={"error": "no models endpoint here"})
        if listing_status == 400:
            return httpx.Response(200, json={"data": "not-a-list"})
        return httpx.Response(200, json=listing_body)

    monkeypatch.setattr(chat_service.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as first:
        assert (await first.post("/auth/login", json=_login_payload(email, password))).status_code == 200
        for provider in chat_service.MODEL_PROVIDERS:
            assert (await first.put(f"/settings/api-keys/{provider}", json={"api_key": "sk-listing-aaaa"}, headers=write)).status_code == 200

        # 这个 GET 会解密用户 Key，所以受同源写保护；不带该头必须被拒
        assert (await first.get("/settings/models/openai")).status_code == 400
        # 不在 MODEL_PROVIDERS 白名单里的服务商标识（前端「其他服务商」）不予列出
        assert (await first.get("/settings/models/custom", headers=write)).status_code == 400

        listing_body = {"data": [{"id": "gpt-4o-mini"}]}
        for provider, config in chat_service.MODEL_PROVIDERS.items():
            calls.clear()
            response = await first.get(f"/settings/models/{provider}", headers=write)
            assert response.status_code == 200, response.text
            # 只有这一条 URL 断言能抓到写死的地址打错字（查询串不参与比较）
            assert [call.split("?")[0] for call in calls] == [config["models_url"]]
            payload = response.json()["data"]
            assert payload["provider"] == provider
            if provider == "anthropic":
                assert payload["models"] == [{"id": "claude-haiku-4-5", "label": "Claude Haiku"}]
                assert payload["default"] == config["model"]
            else:
                assert payload["models"] == [{"id": "gpt-4o-mini", "label": "gpt-4o-mini"}]

        # 明显不能对话的模型不出现在下拉里
        calls.clear()
        listing_body = {"data": [{"id": "gpt-4o"}, {"id": "text-embedding-3-small"}, {"id": "whisper-1"}, {"id": "gpt-4o-audio-preview"}]}
        models = (await first.get("/settings/models/openai", headers=write)).json()["data"]["models"]
        assert [item["id"] for item in models] == ["gpt-4o"]

        # 保存模型名
        assert (await first.put("/settings/model", json={"provider": "openai", "model_name": "gpt-4o"}, headers=write)).status_code == 200
        assert (await first.put("/settings/model", json={"provider": "openai", "model_name": "gpt-4o" + "x" * 128}, headers=write)).status_code == 400
        for junk in ("gpt 4o", "gpt-4o;drop", "../evil", "gpt-4o\nwith tail", "模型"):
            assert (await first.put("/settings/model", json={"provider": "openai", "model_name": junk}, headers=write)).status_code == 400, junk
        # 首尾空白会被修剪后再存
        assert (await first.put("/settings/model", json={"provider": "openai", "model_name": "  gpt-4o  "}, headers=write)).status_code == 200
        assert (await first.get("/settings/model")).json()["data"]["model_name"] == "gpt-4o"
        # 空白等价于「不选」，落库存 NULL
        assert (await first.put("/settings/model", json={"provider": "openai", "model_name": "   "}, headers=write)).status_code == 200
        assert (await first.get("/settings/model")).json()["data"]["model_name"] == "gpt-4o-mini"
        assert (await first.put("/settings/model", json={"provider": "openai", "model_name": "gpt-4o"}, headers=write)).status_code == 200

        # 302 不接受（客户端 follow_redirects=False），且不会跟着打到重定向目标
        listing_status = 302
        calls.clear()
        response = await first.get("/settings/models/openai", headers=write)
        assert response.status_code == 500
        assert calls == [chat_service.MODEL_PROVIDERS["openai"]["models_url"]]
        assert "sk-listing-aaaa" not in response.text

        # 404 / 响应形状不对 → 中文提示而不是 traceback，Key 保持可用
        for listing_status in (404, 400):
            response = await first.get("/settings/models/openai", headers=write)
            assert response.status_code == 500
            assert response.json()["msg"] == "服务商未能返回模型列表"
            assert "sk-listing-aaaa" not in response.text
        assert {row["provider"]: row["status"] for row in (await first.get("/settings/api-keys")).json()["data"]}["openai"] == "active"

        # 被服务商拒绝：Key 标记失效，但用户选的模型名留着
        listing_status = 401
        response = await first.get("/settings/models/openai", headers=write)
        assert response.status_code == 500
        assert response.json()["msg"] == "服务商拒绝了 API Key，请到设置中替换"
        rows = {row["provider"]: row for row in (await first.get("/settings/api-keys")).json()["data"]}
        assert rows["openai"]["status"] == "invalid"
        assert rows["openai"]["model_name"] == "gpt-4o"

        # 没有可用 Key 的服务商：400 而不是解密失败
        assert (await first.delete("/settings/api-keys/qwen", headers=write)).status_code == 200
        response = await first.get("/settings/models/qwen", headers=write)
        # 文案也钉住：这一路靠 KeyRecordError 走 400，而 except 子句里漏 import 会变成
        # NameError -> 500，状态码能分辨、但只有 msg 能证明是「因为没有 Key」才 400 的。
        assert response.status_code == 400, response.text
        assert response.json()["msg"] == "请先保存该服务商的 API Key"

        # 覆盖 Key 之后模型名不变（save_key 只重写信封列）
        assert (await first.put("/settings/api-keys/openai", json={"api_key": "sk-listing-bbbb"}, headers=write)).status_code == 200
        rows = {row["provider"]: row for row in (await first.get("/settings/api-keys")).json()["data"]}
        assert rows["openai"]["model_name"] == "gpt-4o"
        assert rows["openai"]["status"] == "active"
