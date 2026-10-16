import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import get_http_client
from app.services import embedding_key_service

_EMBEDDING_DIM = 1024
_BATCH_SIZE = 10
_TIMEOUT = httpx.Timeout(20.0, connect=8.0)

class EmbeddingError(Exception):
    """embedding 错误"""

async def embed_texts(user_id:int,texts:list[str],session:AsyncSession)->list[list[float]]:
    if not texts:
        return []
    record = await embedding_key_service.key_for_embedding(user_id, session)
    url = record.base_url.rstrip("/") +"/embeddings"
    headers = {"Authorization": f"Bearer {record.api_key}",
               "Content-Type": "application/json"}
    vector: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start:start+_BATCH_SIZE]
        payload = {
            "model": record.model_name,
            "input": batch,
            "dimension": _EMBEDDING_DIM
        }
        client = get_http_client()
        if client is None:
            async with httpx.AsyncClient(timeout=_TIMEOUT,
                                         follow_redirects=False) as one_off:
                resp = await one_off.post(url, json=payload, headers=headers)
        else:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code in (401, 403):
            await embedding_key_service.mark_invalid(record.key_id,user_id,session)
            raise EmbeddingError("向量模型的 key 已被厂商拒绝，已标记为失效，请重新配置")
        if resp.status_code != 200:
            raise EmbeddingError("向量模型调用失败")
        data = resp.json()
        batch_vector = [row["embedding"] for row in data["data"]]
        for vec in batch_vector:
            if len(vec) != _EMBEDDING_DIM:
                raise EmbeddingError("向量模型返回的向量维度与配置不一致")
        vector.extend(batch_vector)
    return vector
