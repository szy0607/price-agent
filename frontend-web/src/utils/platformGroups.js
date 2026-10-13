// 消费记录「平台卡片组」的分组与筛选。合并动作必须和筛选共用同一份成员表：
// 曾经卡片组在 PlatformDeck 内部自造 key='其他' 再 emit，视图按 platform==='其他'
// 去筛，而没有任何记录真叫这个名字，点「其他」永远是空集。
const MERGE_LABEL = '其他'
const MAX_CARDS = 6

// purchase_record 没有 category 列（分表决策 #29/#30），分组维度用真实存在的 platform。
export function platformOf(item) {
  return (item.platform || '').trim() || '平台未记'
}

export function groupByPlatform(records, maxCards = MAX_CARDS) {
  const tally = new Map()
  for (const item of records) {
    const key = platformOf(item)
    const group = tally.get(key) || { key, count: 0, total: 0 }
    group.count += 1
    group.total += item.price || 0
    tally.set(key, group)
  }

  const sorted = [...tally.values()].sort((a, b) => b.count - a.count)
  if (sorted.length <= maxCards) {
    return { groups: sorted, members: indexMembers(sorted) }
  }

  const head = sorted.slice(0, maxCards - 1)
  const tail = sorted.slice(maxCards - 1)
  // 真有人把平台填成「其他」时并入这张卡，避免两张同名卡
  const clash = head.findIndex((group) => group.key === MERGE_LABEL)
  if (clash >= 0) tail.push(...head.splice(clash, 1))

  const groups = [
    ...head,
    {
      key: MERGE_LABEL,
      count: tail.reduce((sum, group) => sum + group.count, 0),
      total: tail.reduce((sum, group) => sum + group.total, 0),
      merged: tail.map((group) => group.key),
    },
  ]
  return { groups, members: indexMembers(groups) }
}

export function filterByGroup(records, members, key) {
  if (!key) return [...records]
  const covered = members.get(key)
  // 组已经不存在（比如删了几笔后不再需要「其他」）时返回空集，
  // 由视图的「筛出空集就取消筛选」把它清掉，不要假装匹配全部
  return covered ? records.filter((item) => covered.includes(platformOf(item))) : []
}

function indexMembers(groups) {
  return new Map(groups.map((group) => [group.key, group.merged || [group.key]]))
}
