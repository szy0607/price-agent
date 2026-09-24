/**
 * Mock 数据源（网页版，2026-09-13 重构版）
 * 1) 演示商品全部为真实在售、品牌可查的商品（规格为官方口径，价格区间模拟真实市场）；
 * 2) 每个 SKU 展示淘宝 / 京东 / 拼多多三平台价格：A = 公开价，B = 领券价；
 * 3) 图片为 picsum 占位图，正式版替换为商品实拍图。
 * 价格口径：A = 直接购买；B = 领到券后；plus = 京东 PLUS 会员价；subsidy = 拼多多百亿补贴。
 * 券类型：public = 公开券；channel = 渠道专享券。
 * 演示价格仅为区间模拟，正式版由联盟查券 API 返回实时数据。
 */

/** 本地静态资源（public/images/），自动适配 vite base 路径 */
const headphoneImg = `${import.meta.env.BASE_URL}images/headphone.jpg`
const bottleImg = `${import.meta.env.BASE_URL}images/bottle.jpg`
const cleanserImg = `${import.meta.env.BASE_URL}images/cleanser.jpg`

export const PLATFORMS = {
  taobao: { name: '淘宝', api: 'taobao.tbk.item.get', keyFields: ['预估到手价', '优惠券', '促销利益点', '销量'], register: '淘宝客个人可注册', accent: '#ff5000' },
  jd: { name: '京东', api: 'jd.union.open.goods.query', keyFields: ['PLUS 会员价', '优惠券', '拼购价', '低至到手价'], register: '京粉个人可注册', accent: '#e1251b' },
  pdd: { name: '拼多多', api: 'pdd.ddk.goods.search', keyFields: ['拼团价', '百亿补贴标识', '优惠券', '店铺券'], register: '个人即可，门槛最友好', accent: '#e02e24' },
}

export const PLAT_KEYS = ['taobao', 'jd', 'pdd']

/** 口令提示语（复制口令 → 打开平台 App 自动跳转；Demo 口令，正式版由后端按联盟 API 数据生成） */
export const copyHints = {
  taobao: '复制口令，打开淘宝 App 自动跳转',
  jd: '复制口令，打开京东 App 自动跳转',
  pdd: '复制口令，打开拼多多 App 自动跳转',
}

/** 无具体商品时的平台演示口令（CouponView 兜底展示） */
export const platformCodes = {
  taobao: { code: '€Demo3QwXzKp9€', hint: 'Demo 口令：复制后打开淘宝 App 验证跳转' },
  jd: { code: '【京东】DemoXz2VnQmKc 复制打开京东', hint: 'Demo 口令：复制后打开京东 App 验证跳转' },
  pdd: { code: '#DemoJf8kQw3p#', hint: 'Demo 口令：复制后打开拼多多 App 验证跳转' },
}

export const products = [
  {
    id: 'p-headphone',
    category: '数码影音',
    brand: 'Sony 索尼',
    name: 'WH-1000XM5 无线降噪耳机',
    model: 'WH-1000XM5',
    desc: '头戴式主动降噪耳机，8 麦克风降噪系统，LDAC 高解析无线，通勤与学习场景。',
    image: headphoneImg,
    conclusion:
      '追求性价比选「黑色」：拼多多百亿补贴约 2199 元最低。京东 PLUS 会员价 2249 元且售后最快；淘宝渠道券 2349 元。在意音质选 LDAC + 30mm 镀铝振膜，三款颜色核心规格一致，仅颜色差异。',
    skus: [
      {
        name: '黑色',
        image: headphoneImg,
        stock: '有货',
        specs: { 颜色: '黑色', 驱动单元: '30mm 镀铝液晶振膜', 蓝牙: '5.2 / LDAC', 续航: '30h（开降噪）/ 40h', 重量: '约 250g', 快充: '3 分钟 ≈ 3 小时' },
        prices: {
          taobao: {
            a: 2599, b: 2349,
            coupon: { type: 'channel', name: '渠道专享券', amount: 250, threshold: 0, note: '需通过专属渠道领取，领不到则按公开价购买' },
            code: '€Xm5BkD2Qp7K€', sales: '月销 9000+',
          },
          jd: {
            a: 2599, b: 2399, plus: 2249,
            coupon: { type: 'public', name: '平台券', amount: 200, threshold: 2599, note: '领券中心可领，满 2599 减 200' },
            code: '【京东】Xm5D2Qp7Kc 复制打开京东', sales: '月销 1.2 万+',
          },
          pdd: {
            a: 2499, b: 2199, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 300, threshold: 2499, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Xm5D2Qp7K#', sales: '已拼 2.8 万件',
          },
        },
      },
      {
        name: '银色',
        image: headphoneImg,
        stock: '有货',
        specs: { 颜色: '银色', 驱动单元: '30mm 镀铝液晶振膜', 蓝牙: '5.2 / LDAC', 续航: '30h（开降噪）/ 40h', 重量: '约 250g', 快充: '3 分钟 ≈ 3 小时' },
        prices: {
          taobao: {
            a: 2599, b: 2349,
            coupon: { type: 'channel', name: '渠道专享券', amount: 250, threshold: 0, note: '需通过专属渠道领取，领不到则按公开价购买' },
            code: '€Xm5SkD2Qp7K€', sales: '月销 6000+',
          },
          jd: {
            a: 2599, b: 2399, plus: 2249,
            coupon: { type: 'public', name: '平台券', amount: 200, threshold: 2599, note: '领券中心可领，满 2599 减 200' },
            code: '【京东】Xm5SkD2Qp7 复制打开京东', sales: '月销 8000+',
          },
          pdd: {
            a: 2499, b: 2199, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 300, threshold: 2499, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Xm5SkD2Qp7#', sales: '已拼 1.9 万件',
          },
        },
      },
      {
        name: '深蓝',
        image: headphoneImg,
        stock: '库存紧张',
        specs: { 颜色: '深蓝', 驱动单元: '30mm 镀铝液晶振膜', 蓝牙: '5.2 / LDAC', 续航: '30h（开降噪）/ 40h', 重量: '约 250g', 快充: '3 分钟 ≈ 3 小时' },
        prices: {
          taobao: {
            a: 2699, b: 2449,
            coupon: { type: 'channel', name: '渠道专享券', amount: 250, threshold: 0, note: '需通过专属渠道领取，领不到则按公开价购买' },
            code: '€Xm5BlD2Qp7K€', sales: '月销 2000+',
          },
          jd: {
            a: 2699, b: 2499, plus: 2349,
            coupon: { type: 'public', name: '平台券', amount: 200, threshold: 2699, note: '领券中心可领，满 2699 减 200' },
            code: '【京东】Xm5BlD2Qp7 复制打开京东', sales: '月销 3000+',
          },
          pdd: {
            a: 2599, b: 2299, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 300, threshold: 2599, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Xm5BlD2Qp7#', sales: '已拼 7000 件',
          },
        },
      },
    ],
  },
  {
    id: 'p-bottle',
    category: '家居日用',
    brand: 'ZOJIRUSHI 象印',
    name: 'SM-SA 系列不锈钢保温杯',
    model: 'SM-SA48 / SM-SA60',
    desc: '一键弹盖超轻保温杯，约 200g，双层真空，通勤、户外与母婴场景。',
    image: bottleImg,
    conclusion:
      '通勤自用选「480ml 黑色」：京东 PLUS 价 169 元最划算。常泡茶或需更大容量选「600ml」款。颜色仅外观差异，保温性能一致（6 小时 ≥75℃）。',
    skus: [
      {
        name: '480ml · 黑色',
        image: bottleImg,
        stock: '有货',
        specs: { 型号: 'SM-SA48-BM', 容量: '480ml', 内胆: '304 不锈钢（双层真空）', 保温: '6h ≥ 75℃', 重量: '约 200g', 杯盖: '一键弹盖' },
        prices: {
          taobao: {
            a: 219, b: 189,
            coupon: { type: 'public', name: '店铺券', amount: 30, threshold: 199, note: '店铺首页可领，满 199 减 30' },
            code: '€Sa48BkD2Qp7€', sales: '月销 3000+',
          },
          jd: {
            a: 219, b: 179, plus: 169,
            coupon: { type: 'public', name: '平台券', amount: 40, threshold: 199, note: '领券中心可领，满 199 减 40' },
            code: '【京东】Sa48BkD2Qp7 复制打开京东', sales: '月销 5000+',
          },
          pdd: {
            a: 199, b: 159, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 40, threshold: 199, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Sa48BkD2Qp7#', sales: '已拼 1.2 万件',
          },
        },
      },
      {
        name: '480ml · 天蓝',
        image: bottleImg,
        stock: '有货',
        specs: { 型号: 'SM-SA48-AQ', 容量: '480ml', 内胆: '304 不锈钢（双层真空）', 保温: '6h ≥ 75℃', 重量: '约 200g', 杯盖: '一键弹盖' },
        prices: {
          taobao: {
            a: 219, b: 189,
            coupon: { type: 'public', name: '店铺券', amount: 30, threshold: 199, note: '店铺首页可领，满 199 减 30' },
            code: '€Sa48AqD2Qp7€', sales: '月销 2500+',
          },
          jd: {
            a: 219, b: 179, plus: 169,
            coupon: { type: 'public', name: '平台券', amount: 40, threshold: 199, note: '领券中心可领，满 199 减 40' },
            code: '【京东】Sa48AqD2Qp7 复制打开京东', sales: '月销 4000+',
          },
          pdd: {
            a: 199, b: 159, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 40, threshold: 199, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Sa48AqD2Qp7#', sales: '已拼 9000 件',
          },
        },
      },
      {
        name: '600ml · 黑色',
        image: bottleImg,
        stock: '有货',
        specs: { 型号: 'SM-SA60-BM', 容量: '600ml', 内胆: '304 不锈钢（双层真空）', 保温: '6h ≥ 75℃', 重量: '约 250g', 杯盖: '一键弹盖' },
        prices: {
          taobao: {
            a: 259, b: 219,
            coupon: { type: 'public', name: '店铺券', amount: 40, threshold: 239, note: '店铺首页可领，满 239 减 40' },
            code: '€Sa60BkD2Qp7€', sales: '月销 1800+',
          },
          jd: {
            a: 259, b: 219, plus: 199,
            coupon: { type: 'public', name: '平台券', amount: 40, threshold: 239, note: '领券中心可领，满 239 减 40' },
            code: '【京东】Sa60BkD2Qp7 复制打开京东', sales: '月销 3000+',
          },
          pdd: {
            a: 239, b: 189, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 50, threshold: 239, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Sa60BkD2Qp7#', sales: '已拼 6000 件',
          },
        },
      },
    ],
  },
  {
    id: 'p-cleanser',
    category: '美妆个护',
    brand: 'freeplus 芙丽芳丝',
    name: '净润洗面霜 100g',
    model: '净润洗面霜',
    desc: '氨基酸表活洁面，弱酸性配方，无香料无色素，敏感肌可用。',
    image: cleanserImg,
    conclusion:
      '自用推荐「两支装」：拼多多百亿补贴后约 168 元，单支成本最低。首次尝试先买「单支装」试肤；京东 PLUS 价 112 元且物流最快，适合急用。',
    skus: [
      {
        name: '单支装 100g',
        image: cleanserImg,
        stock: '有货',
        specs: { 规格: '100g / 支', 表活: '氨基酸表活', pH: '弱酸性（约 5.5）', 适用: '全肤质 / 敏感肌', 配方: '无香料无色素' },
        prices: {
          taobao: {
            a: 150, b: 125,
            coupon: { type: 'public', name: '店铺券', amount: 25, threshold: 139, note: '店铺首页可领，满 139 减 25' },
            code: '€Fp1sD2Qp7K€', sales: '月销 8000+',
          },
          jd: {
            a: 150, b: 119, plus: 112,
            coupon: { type: 'public', name: '平台券', amount: 31, threshold: 139, note: '领券中心可领，满 139 减 31' },
            code: '【京东】Fp1sD2Qp7K 复制打开京东', sales: '月销 1 万+',
          },
          pdd: {
            a: 139, b: 96, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 43, threshold: 139, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Fp1sD2Qp7K#', sales: '已拼 3.6 万件',
          },
        },
      },
      {
        name: '两支装（约 4 个月量）',
        image: cleanserImg,
        stock: '有货',
        specs: { 规格: '100g × 2', 表活: '氨基酸表活', pH: '弱酸性（约 5.5）', 适用: '全肤质 / 敏感肌', 配方: '无香料无色素' },
        prices: {
          taobao: {
            a: 260, b: 219,
            coupon: { type: 'channel', name: '渠道专享券', amount: 41, threshold: 259, note: '需通过专属渠道领取；领不到可走店铺公开券' },
            code: '€Fp2sD2Qp7K€', sales: '月销 5000+',
          },
          jd: {
            a: 260, b: 219, plus: 205,
            coupon: { type: 'public', name: '平台券', amount: 41, threshold: 259, note: '领券中心可领，满 259 减 41' },
            code: '【京东】Fp2sD2Qp7K 复制打开京东', sales: '月销 7000+',
          },
          pdd: {
            a: 249, b: 168, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 81, threshold: 249, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Fp2sD2Qp7K#', sales: '已拼 2.1 万件',
          },
        },
      },
      {
        name: '替换装 90g',
        image: cleanserImg,
        stock: '有货',
        specs: { 规格: '90g / 支', 表活: '氨基酸表活', pH: '弱酸性（约 5.5）', 适用: '需自备按压瓶', 配方: '无香料无色素' },
        prices: {
          taobao: {
            a: 120, b: 99,
            coupon: { type: 'public', name: '店铺券', amount: 21, threshold: 109, note: '店铺首页可领，满 109 减 21' },
            code: '€Fp3sD2Qp7K€', sales: '月销 3000+',
          },
          jd: {
            a: 120, b: 95, plus: 89,
            coupon: { type: 'public', name: '平台券', amount: 25, threshold: 109, note: '领券中心可领，满 109 减 25' },
            code: '【京东】Fp3sD2Qp7K 复制打开京东', sales: '月销 4000+',
          },
          pdd: {
            a: 109, b: 79, subsidy: true,
            coupon: { type: 'public', name: '百亿补贴券', amount: 30, threshold: 109, note: '百亿补贴价自动生效，可再领补贴券' },
            code: '#Fp3sD2Qp7K#', sales: '已拼 1.4 万件',
          },
        },
      },
    ],
  },
]

/** 某 SKU 在指定平台的价格对象 */
export const priceAt = (sku, plat) => sku.prices[plat]

/** 某商品在某平台的最低领券价 SKU */
export const cheapest = (product, plat) =>
  product.skus.reduce((acc, s) => (s.prices[plat].b < acc.prices[plat].b ? s : acc), product.skus[0])

/** 某商品全场（跨平台）最低到手价平台 */
export const bestPlat = (product) => {
  let best = { plat: 'taobao', sku: product.skus[0], price: Infinity }
  for (const p of PLAT_KEYS) {
    const sku = cheapest(product, p)
    const price = sku.prices[p].b
    if (price < best.price) best = { plat: p, sku, price }
  }
  return best
}

/** 优惠类型获取策略（设计稿 3.2 v0.3） */
export const platformBenefits = [
  { platform: 'taobao', name: '店铺券 / 商品券（券后价）', viaApi: true, how: 'API 双价展示' },
  { platform: 'taobao', name: '跨店满减 / 单品直降', viaApi: true, how: 'API 展示促销利益点' },
  { platform: 'taobao', name: '淘金币（账号维度）', viaApi: false, how: 'RAG 规则：下单页勾选淘金币' },
  { platform: 'taobao', name: '天降红包（千人千面）', viaApi: false, how: '不承诺，下单页留意专属红包' },
  { platform: 'jd', name: 'PLUS 会员价', viaApi: true, how: 'API 双价展示 + 画像记录会员身份' },
  { platform: 'jd', name: '优惠券 / 拼购价', viaApi: true, how: 'API 双价展示' },
  { platform: 'pdd', name: '百亿补贴', viaApi: true, how: 'API 标识 + 补贴价展示' },
  { platform: 'pdd', name: '拼团价 / 店铺券', viaApi: true, how: 'API 双价展示' },
  { platform: 'pdd', name: '首页限时折扣（千人千面）', viaApi: false, how: '不承诺，以页面实时价为准' },
]

export const couponTypes = [
  {
    key: 'public',
    name: '公开券',
    tone: 'green',
    desc: '店铺券 / 平台券 / 满减券，用户自己在商品页、店铺页或领券中心即可领取。',
    rule: '给出具体领券路径与使用门槛（满 X 可用）。',
  },
  {
    key: 'channel',
    name: '渠道专享券（隐藏券 / 联盟券）',
    tone: 'amber',
    desc: '必须通过推广渠道才能领取的券，不是所有人都能领到。',
    rule: '明确说明限制，同时展示「能否领到」两个价格：能领按 B 价，领不到按 A 价，不误导。',
  },
]

export const couponSteps = {
  taobao: [
    '打开商品页，在「优惠券」区域领取店铺券 / 商品券',
    '进入店铺首页「领券中心」查看店铺专属券',
    '结算页确认跨店满减已勾选（如每满 300 减 50）',
    '账号有淘金币时，在下单页勾选淘金币抵扣',
  ],
  jd: [
    '在商品页「促销」区域领取平台券 / 店铺券',
    'PLUS 会员在结算页确认按 PLUS 价结算',
    '领券中心搜索品类券，可与店铺券叠加时优先叠加',
    '结算页核对「到手价」与测算结果是否一致',
  ],
  pdd: [
    '商品页直接显示拼团价，选择「单独拼团」参团',
    '确认商品带「百亿补贴」标识，补贴价自动生效',
    '店铺券在商品页一键领取，满门槛自动抵扣',
    '限时折扣等千人千面权益以页面实时价为准',
  ],
}

export const apiContract = [
  { fn: 'search_product(keyword)', desc: '候选商品列表' },
  { fn: 'get_item_detail(item_id)', desc: '商品详情 + SKU 款式信息' },
  { fn: 'get_price_with_coupon(item_id)', desc: '公开价 / 券后价 / 活动价' },
  { fn: 'get_coupon_info(item_id)', desc: '券类型 / 面额 / 限制 / 领券路径' },
]

/** Demo 意图匹配（真实链路由 A1 理解/路由 Agent 完成） */
export function matchProduct(text) {
  const t = (text || '').toLowerCase()
  const linkHit = /item\.taobao|jd\.com\/|pinduoduo|yangkeduo/.test(t)
  const byTitle = products.find((p) => t.includes(p.name.replace(/\s/g, '').slice(0, 4)))
  if (byTitle) return { product: byTitle, viaLink: linkHit }
  const dict = [
    ['xm5', 'p-headphone'], ['索尼', 'p-headphone'], ['sony', 'p-headphone'], ['耳机', 'p-headphone'], ['降噪', 'p-headphone'], ['蓝牙', 'p-headphone'],
    ['象印', 'p-bottle'], ['保温杯', 'p-bottle'], ['杯子', 'p-bottle'], ['水杯', 'p-bottle'], ['zojirushi', 'p-bottle'],
    ['芙丽芳丝', 'p-cleanser'], ['freeplus', 'p-cleanser'], ['洁面', 'p-cleanser'], ['洗面奶', 'p-cleanser'], ['护肤', 'p-cleanser'],
  ]
  for (const [kw, id] of dict) {
    if (t.includes(kw)) return { product: products.find((p) => p.id === id), viaLink: linkHit }
  }
  if (linkHit) return { product: products[0], viaLink: true }
  return { product: null, viaLink: linkHit }
}
