const STORAGE_KEY = 'price-agent-parameter-records'
const CHANGE_EVENT = 'price-agent-records-changed'

const seedRecords = [
  {
    id: 'record-headphone',
    scope: 'cart',
    name: 'WH-1000XM5 无线降噪耳机',
    brand: 'Sony 索尼',
    model: 'WH-1000XM5',
    category: '数码影音',
    image: `${import.meta.env.BASE_URL}images/headphone.jpg`,
    source: '用户确认',
    updatedAt: '2026-09-30T09:20:00.000Z',
    specs: { 颜色: '黑色', 蓝牙: '5.2 / LDAC', 续航: '30h（开降噪）', 重量: '约 250g' },
  },
  {
    id: 'record-bottle',
    scope: 'items',
    name: 'SM-SA 系列不锈钢保温杯',
    brand: 'ZOJIRUSHI 象印',
    model: 'SM-SA48-BM',
    category: '家居日用',
    image: `${import.meta.env.BASE_URL}images/bottle.jpg`,
    source: '用户确认',
    updatedAt: '2026-09-28T11:10:00.000Z',
    purchasedAt: '2026-09-18',
    note: '办公室日常使用',
    specs: { 容量: '480ml', 内胆: '304 不锈钢（双层真空）', 保温: '6h ≥ 75℃', 重量: '约 200g' },
  },
  {
    id: 'record-cleanser',
    scope: 'items',
    name: '净润洗面霜 100g',
    brand: 'freeplus 芙丽芳丝',
    model: '净润洗面霜',
    category: '美妆个护',
    image: `${import.meta.env.BASE_URL}images/cleanser.jpg`,
    source: '用户确认',
    updatedAt: '2026-09-25T08:40:00.000Z',
    purchasedAt: '2026-09-12',
    specs: { 规格: '100g', 表活: '氨基酸表活', 适用: '全肤质 / 敏感肌' },
  },
  {
    id: 'record-desk-headphone',
    scope: 'items',
    name: '无线降噪耳机',
    brand: 'Sony 索尼',
    model: 'WH-1000XM5',
    category: '数码影音',
    image: `${import.meta.env.BASE_URL}images/headphone.jpg`,
    source: '用户确认',
    updatedAt: '2026-09-22T14:10:00.000Z',
    purchasedAt: '2026-09-06',
    specs: { 颜色: '黑色', 蓝牙: '5.2 / LDAC', 续航: '30h', 重量: '约 250g' },
  },
  {
    id: 'record-travel-bottle',
    scope: 'items',
    name: '轻量便携保温杯',
    brand: 'ZOJIRUSHI 象印',
    model: 'SM-SA60-BM',
    category: '家居日用',
    image: `${import.meta.env.BASE_URL}images/bottle.jpg`,
    source: '用户确认',
    updatedAt: '2026-09-18T10:30:00.000Z',
    purchasedAt: '2026-08-28',
    specs: { 容量: '600ml', 内胆: '304 不锈钢', 保温: '6h ≥ 75℃', 重量: '约 250g' },
  },
  {
    id: 'record-care-set',
    scope: 'items',
    name: '日常清洁护理套装',
    brand: 'freeplus 芙丽芳丝',
    model: '旅行装',
    category: '美妆个护',
    image: `${import.meta.env.BASE_URL}images/cleanser.jpg`,
    source: '用户确认',
    updatedAt: '2026-09-10T16:25:00.000Z',
    purchasedAt: '2026-08-15',
    specs: { 规格: '洁面 + 旅行装', 配方: '无香料无色素', 适用: '敏感肌' },
  },
]

function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

export function loadRecords() {
  if (typeof window === 'undefined') return clone(seedRecords)
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null')
    if (!Array.isArray(parsed) || !parsed.length) return clone(seedRecords)
    const existingIds = new Set(parsed.map((record) => record.id))
    const missingDemoItems = seedRecords.filter((record) => record.scope === 'items' && !existingIds.has(record.id))
    return [...parsed, ...clone(missingDemoItems)]
  } catch {
    return clone(seedRecords)
  }
}

export function saveRecords(records) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(records))
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export function subscribeRecords(handler) {
  window.addEventListener(CHANGE_EVENT, handler)
  return () => window.removeEventListener(CHANGE_EVENT, handler)
}

export function createRecord(input, scope = 'cart') {
  return {
    id: `record-${Date.now()}`,
    scope,
    name: input.name.trim(),
    brand: input.brand.trim() || '待确认品牌',
    model: input.model.trim() || '待确认型号',
    category: input.category.trim() || '未分类',
    image: input.image || `${import.meta.env.BASE_URL}images/headphone.jpg`,
    source: input.source || '用户确认',
    updatedAt: new Date().toISOString(),
    specs: { ...(input.specs || {}) },
  }
}

export { CHANGE_EVENT }
