import logging

from sqlalchemy.ext.asyncio import AsyncSession
from app.repository import vector_repo, chat_repo
from app.core.config import settings
from app.services.embedding_key_service import key_for_embedding
from app.services import embedding_client
logger = logging.getLogger(__name__)


_HARD_TOP_K = 20
#查询用户是否配置了嵌入模型密钥
async def has_embedding_key(user_id: int, session: AsyncSession) -> bool:
    """这个用户配没配可用的向量模型。**查得到就 true**。

    公开出来是因为对话页那条提示（GET /conversations/rag-index-status）要用它
    ——「未配置向量模型」和「向量库正在更新中」是两句话，用户得能分辨。

    为什么不校验 key 是否真的可用：真调一次才知道，而那要花钱。
    key 已失效的情况由 embed_texts 抛 KeyRejected，在 retrieve_relevant
    那层被吞掉 + 记日志。
    """
    try:
        await key_for_embedding(user_id, session)
        return True
    except Exception:
        return False
# 检索函数
async def _retrieve(user_id:int,query:str,session:AsyncSession) -> list[dict]:
    if not query.strip():
        return []
    if not await has_embedding_key(user_id, session):
        logger.info("用户 %d 没有嵌入模型密钥，无法检索", user_id)
        return []

    vectors = await embedding_client.embed_texts(user_id,[query],session)
    if not vectors or not vectors[0]:
        return []

    top_k = min(_HARD_TOP_K,settings.rag_top_k)

    hits = await vector_repo.search_similar(
        user_id,
        vectors[0],
        top_k,
        min_score=settings.rag_min_score
    )
    if not hits:
        return []
    # ④ 🔴 PG 只是副本，**MySQL 才是事实源**。
    #    命中的是 id，必须回 MySQL 取原文——PG 的 content 列不能直接用：
    #    它可能比 MySQL 旧（用户改了商品但向量还没重建）。
    #    查不到就静默跳过：PG 里留着已删/已转移商品的向量是**正常状态**
    #    （drop_vector 自吞异常，reaper 只兜得住有任务在跑的行）。
    pairs = [(hit.source_type, hit.source_id) for hit in hits]
    rows = await chat_repo.fetch_items_for_rag(user_id, pairs, session)
    if len(rows) < len(hits):
        # 只记 info 不报错：孤儿向量是已知状态，不用每轮刷屏。
        # 🔴 减数用 len(hits) 不是 len(pairs)——两者长度恒等，但 hits 才是
        #   「本来期望拿到几条」的语义来源，将来若加去重逻辑只有 hits 正确。
        logger.info("RAG 命中 %d 条，取到原文 %d 条（孤儿向量 %d 条）",
                    len(hits), len(rows), len(hits) - len(rows))
    return rows
#异常降级
async def retrieve_relevant(user_id:int,query:str,session:AsyncSession) -> list[dict]:
    """按用户这句话做语义检索，返回最相关物品的原文列表。**永不抛异常**。

       返回 list[dict] 而不是 ORM 实例：调用方会在本函数返回后关闭 session，
       detached 实例再取属性会踩 DetachedInstanceError（与    chat_repo.messages_for_context 同一条纪律）。

       抛异常的三种情况与对应降级（详见模块 docstring）：
         - 没配向量模型 key   → 空列表 + warning
         - PG 引擎没起        → 空列表 + warning
         - PG 连不上/SQL 错   → 空列表 + warning
       """
    try:
        return await _retrieve(user_id,query,session)
    except Exception:
        logger.warning("RAG 检索异常", exc_info=True)
        return []
