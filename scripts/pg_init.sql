-- pg_init.sql —— price-agent 向量库（PostgreSQL 16 + pgvector）初始化脚本
--
-- 跑法（在项目根目录 F:\price-agent 下，Git Bash / CMD 都行）：
--   docker exec -i price-agent-pg psql -U postgres -d price_agent_pg -f - < scripts/pg_init.sql
--   -i  : 保持标准输入（不加这 flag，管道内容被静默丢弃，脚本一行都不跑）
--   -f -: 从标准输入读 SQL（文件在宿主机，不在容器里，所以不能写容器内路径）
--
-- 幂等：所有语句都是 IF NOT EXISTS，可重复执行。第二遍起不报错、也不改已有数据。
-- 何时跑：新环境初始化 / 改了本文件后 / 部署初始化步骤。
--
-- 定位：MySQL 是事实源，本库只放 embedding 副本（可随时幂等重建）。
--       因此表里刻意【不建外键、不冗余 MySQL 字段】，只有指向 MySQL 那一行的
--       (source_type, source_id)。读取时命中 id 必须回 MySQL 取原文再给模型。
-- 时间口径：项目铁律是「时间值唯一来源 = Python 侧」，本表的 create_time/update_time
--       是【例外】——PG 侧是副本表不是事实源，且 TIMESTAMPTZ + now() 存的是
--       时间点本身（无 MySQL 那个时区坑），upsert 盖时间戳也更省事。

-- 1) 激活向量扩展。镜像里带着扩展文件，但【带着 ≠ 已启用】，必须显式 CREATE。
CREATE EXTENSION IF NOT EXISTS vector;

-- 2) 副本表
CREATE TABLE IF NOT EXISTS item_embedding (
    id          BIGSERIAL   PRIMARY KEY,
    user_id     BIGINT      NOT NULL,
    source_type VARCHAR(16) NOT NULL,
    source_id   BIGINT      NOT NULL,
    content     TEXT        NOT NULL,
    vector      VECTOR(1024) NOT NULL,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE item_embedding IS
    'embedding 副本表：MySQL 侧 cart_item / owned_item / purchase_record 等物品的向量。事实仍在 MySQL，命中后回 MySQL 取原文。';
COMMENT ON COLUMN item_embedding.source_type IS
    '来源类型：cart 购物车 / owned 物品库 / purchase 消费记录（chat 语料批②、profile 批③ 预留）';
COMMENT ON COLUMN item_embedding.source_id IS
    'MySQL 侧对应的行 id（逻辑外键，PG 侧不建真外键——副本表不该有跨库外键）';
COMMENT ON COLUMN item_embedding.content IS
    '切片文本（build_item_text 产出）。只是检索用的副本，物品改名后可能短暂不一致，以 MySQL 为准';
COMMENT ON COLUMN item_embedding.vector IS
    '1024 维向量。维度与 embedding_client 的维度校验、embed_texts 的 dimensions 参数是同一根线，改这里必须同步那两处并重建全部向量';

-- 3) 唯一索引：一件物品一条向量。upsert（ON CONFLICT）靠它当冲突键；
--    重复插入是 bug，不该被容忍。
CREATE UNIQUE INDEX IF NOT EXISTS uq_item_embedding_source
    ON item_embedding (user_id, source_type, source_id);

-- 4) 普通索引：检索必带 user_id 过滤（铁律），先按人过滤再算距离。
--    刻意不建 hnsw 向量索引：每人的向量就几百条，暴力扫描比走索引更快，
--    阈值量级在十万级再加。
CREATE INDEX IF NOT EXISTS ix_item_embedding_user
    ON item_embedding (user_id);
