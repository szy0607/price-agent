const PLATFORM_KEYS = ['taobao', 'jd', 'pdd']

function parseCsv(text) {
  const rows = []
  let row = []
  let cell = ''
  let quoted = false

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        cell += '"'
        index += 1
      } else {
        quoted = !quoted
      }
    } else if (char === ',' && !quoted) {
      row.push(cell.trim())
      cell = ''
    } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[index + 1] === '\n') index += 1
      row.push(cell.trim())
      if (row.some(Boolean)) rows.push(row)
      row = []
      cell = ''
    } else {
      cell += char
    }
  }

  row.push(cell.trim())
  if (row.some(Boolean)) rows.push(row)
  if (rows.length < 2) throw new Error('CSV 至少需要表头和一条商品数据')

  const headers = rows[0].map((header, index) => index === 0 ? header.replace(/^\uFEFF/, '') : header)
  return rows.slice(1).map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ''])))
}

function numberFrom(...values) {
  for (const value of values) {
    if (value === '' || value === null || value === undefined) continue
    const number = Number(value)
    if (Number.isFinite(number) && number >= 0) return number
  }
  return null
}

function objectFrom(value) {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value
  if (typeof value !== 'string' || !value.trim().startsWith('{')) return null
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

function normalizeProduct(raw, index, { fileName, fallbackImages }) {
  const name = String(raw.name || raw.product_name || '').trim()
  if (!name) throw new Error(`第 ${index + 1} 条商品缺少 name 字段`)

  const nestedPrices = objectFrom(raw.prices) || raw.prices || {}
  const availablePrice = numberFrom(
    raw.price,
    raw.taobao_price, raw.jd_price, raw.pdd_price,
    nestedPrices.taobao?.b, nestedPrices.jd?.b, nestedPrices.pdd?.b,
  )
  if (availablePrice === null) throw new Error(`「${name}」缺少可用价格`)

  const image = String(raw.image || fallbackImages[index % fallbackImages.length] || '')
  const specs = objectFrom(raw.specs) || {
    数据来源: fileName,
    导入方式: '用户商品库',
  }
  const prices = {}

  for (const platform of PLATFORM_KEYS) {
    const nested = nestedPrices[platform] || {}
    const salePrice = numberFrom(nested.b, nested.price, raw[`${platform}_price`], raw[platform], availablePrice)
    const originalPrice = numberFrom(nested.a, raw[`${platform}_original_price`], salePrice)
    prices[platform] = {
      a: originalPrice,
      b: salePrice,
      ...(platform === 'jd' && numberFrom(nested.plus, raw.jd_plus_price) !== null
        ? { plus: numberFrom(nested.plus, raw.jd_plus_price) }
        : {}),
      subsidy: platform === 'pdd' && String(nested.subsidy ?? raw.pdd_subsidy).toLowerCase() === 'true',
      coupon: {
        type: 'public',
        name: '文件导入价',
        amount: Math.max(0, originalPrice - salePrice),
        threshold: 0,
        note: '本地导入演示数据',
      },
    }
  }

  return {
    id: String(raw.id || `custom-${index + 1}-${name}`).replace(/\s+/g, '-'),
    category: String(raw.category || '自定义商品'),
    brand: String(raw.brand || '用户商品库'),
    name,
    model: String(raw.model || '自定义导入'),
    image,
    conclusion: String(raw.conclusion || `该商品来自「${fileName}」，当前仅用于验证自定义商品库的导入与比价展示流程。`),
    skus: [{
      name: String(raw.sku || raw.sku_name || '默认款式'),
      image,
      stock: String(raw.stock || '库存待同步'),
      specs,
      prices,
    }],
  }
}

export function parseProductLibrary(text, { fileName = 'product-library.json', fallbackImages = [] } = {}) {
  if (!text.trim()) throw new Error('商品库文件不能为空')

  let records
  if (fileName.toLowerCase().endsWith('.csv')) {
    records = parseCsv(text)
  } else {
    const parsed = JSON.parse(text)
    records = Array.isArray(parsed) ? parsed : (Array.isArray(parsed.products) ? parsed.products : [parsed])
  }

  if (!records.length) throw new Error('商品库中没有可导入的商品')
  return records.slice(0, 50).map((record, index) => normalizeProduct(record, index, { fileName, fallbackImages }))
}
