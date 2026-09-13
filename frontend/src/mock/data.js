/**
 * Mock 数据源（对应设计稿中的 D4 Mock 数据源，开发/演示用）
 * 命名遵循设计稿约定：统一使用「查询/采集/情报」，不使用「爬取」字样。
 * 价格口径（双价展示策略）：
 *   价格 A（公开价）——用户直接购买的价格
 *   价格 B（领券价）——领到券后的价格
 * 券类型：public=公开券（商品页/店铺页可领）；channel=渠道专享券（需通过推广渠道领取）
 */

export const PLATFORMS = {
  taobao: { name: '淘宝', color: '#ff5000' },
  jd: { name: '京东', color: '#e1251b' },
  pdd: { name: '拼多多', color: '#e02e24' },
}

export const products = [
  {
    id: 'p-earphone',
    category: '数码配件',
    emoji: '🎧',
    title: '无线降噪耳机 Pro',
    intro: '主动降噪、头戴式蓝牙耳机，适合通勤与学习场景。',
    platform: 'taobao',
    sales: '月销 2.3 万+',
    skus: [
      {
        name: '星夜黑',
        specs: {
          颜色: '星夜黑',
          续航: '40h（开降噪 30h）',
          降噪深度: '-42dB',
          单元: '40mm 动圈',
          重量: '252g',
          蓝牙: '5.4 / 双设备连接',
        },
        priceA: 799,
        priceB: 649,
        coupon: { type: 'channel', name: '渠道专享券', amount: 150, threshold: 0, note: '需通过专属渠道领取，领不到则按公开价购买' },
        promotion: '跨店满减：每满 300 减 50',
        stock: '有货',
      },
      {
        name: '皓月白',
        specs: {
          颜色: '皓月白',
          续航: '40h（开降噪 30h）',
          降噪深度: '-42dB',
          单元: '40mm 动圈',
          重量: '252g',
          蓝牙: '5.4 / 双设备连接',
        },
        priceA: 799,
        priceB: 679,
        coupon: { type: 'channel', name: '渠道专享券', amount: 120, threshold: 0, note: '需通过专属渠道领取，领不到则按公开价购买' },
        promotion: '跨店满减：每满 300 减 50',
        stock: '有货',
      },
      {
        name: '远峰蓝（限量）',
        specs: {
          颜色: '远峰蓝',
          续航: '40h（开降噪 30h）',
          降噪深度: '-45dB',
          单元: '40mm 镀铍动圈',
          重量: '248g',
          蓝牙: '5.4 / 双设备连接 / LDAC',
        },
        priceA: 999,
        priceB: 899,
        coupon: { type: 'public', name: '店铺券', amount: 100, threshold: 900, note: '商品页可直接领取，满 900 可用' },
        promotion: '单品直降 100 元',
        stock: '库存紧张',
      },
    ],
    conclusion:
      '追求性价比选「星夜黑」：可领渠道专享券，领到后到手 649 元；若在意音质且能接受限量款溢价，「远峰蓝」配置最高（LDAC 高清音频 + 更深降噪）。三款核心降噪与续航一致，差异主要在配色、单元与音频编码。',
  },
  {
    id: 'p-bottle',
    category: '家居日用',
    emoji: '🥤',
    title: '316 不锈钢保温杯 750ml',
    intro: '大容量保温杯，316 内胆，适合通勤、户外与母婴场景。',
    platform: 'jd',
    sales: '月销 8000+',
    skus: [
      {
        name: '基础款 · 磨砂黑',
        specs: {
          容量: '750ml',
          内胆: '316 不锈钢',
          保温: '6h ≥ 65℃',
          杯盖: '直饮盖',
          重量: '385g',
        },
        priceA: 129,
        priceB: 109,
        coupon: { type: 'public', name: '平台券', amount: 20, threshold: 99, note: '领券中心可领，满 99 减 20' },
        promotion: 'PLUS 会员价 99 元',
        stock: '有货',
        plusPrice: 99,
      },
      {
        name: '基础款 · 奶白',
        specs: {
          容量: '750ml',
          内胆: '316 不锈钢',
          保温: '6h ≥ 65℃',
          杯盖: '直饮盖',
          重量: '385g',
        },
        priceA: 129,
        priceB: 109,
        coupon: { type: 'public', name: '平台券', amount: 20, threshold: 99, note: '领券中心可领，满 99 减 20' },
        promotion: 'PLUS 会员价 99 元',
        stock: '有货',
        plusPrice: 99,
      },
      {
        name: '茶水分离款',
        specs: {
          容量: '750ml（茶仓 80ml）',
          内胆: '316 不锈钢',
          保温: '12h ≥ 60℃',
          杯盖: '茶水分离盖',
          重量: '452g',
        },
        priceA: 179,
        priceB: 149,
        coupon: { type: 'public', name: '店铺券', amount: 30, threshold: 150, note: '店铺首页可领，满 150 减 30' },
        promotion: '满 300 减 40（可凑单）',
        stock: '有货',
        plusPrice: 139,
      },
    ],
    conclusion:
      '日常通勤选「基础款」：PLUS 会员到手 99 元，性价比最高；常泡茶选「茶水分离款」，保温与茶仓更实用。奶白与磨砂黑仅配色差异。',
  },
  {
    id: 'p-cleanser',
    category: '美妆个护',
    emoji: '🧴',
    title: '氨基酸温和洁面乳 120g',
    intro: '氨基酸表活洁面，弱酸性配方，适合敏感肌与日常清洁。',
    platform: 'pdd',
    sales: '已拼 5.6 万件',
    skus: [
      {
        name: '单支装',
        specs: {
          规格: '120g',
          表活: '氨基酸（椰油酰甘氨酸钾）',
          pH: '5.5 弱酸性',
          适用: '全肤质 / 敏感肌',
          质地: '绵密泡沫',
        },
        priceA: 59,
        priceB: 45,
        coupon: { type: 'public', name: '店铺券', amount: 14, threshold: 50, note: '商品页可领，满 50 减 14' },
        promotion: '百亿补贴',
        stock: '有货',
        subsidy: true,
      },
      {
        name: '两支装（180 天量）',
        specs: {
          规格: '120g × 2',
          表活: '氨基酸（椰油酰甘氨酸钾）',
          pH: '5.5 弱酸性',
          适用: '全肤质 / 敏感肌',
          质地: '绵密泡沫',
        },
        priceA: 99,
        priceB: 79,
        coupon: { type: 'channel', name: '渠道专享券', amount: 20, threshold: 90, note: '需通过专属渠道领取；领不到可走店铺公开券' },
        promotion: '百亿补贴',
        stock: '有货',
        subsidy: true,
      },
      {
        name: '替换装（环保芯）',
        specs: {
          规格: '100g 替换芯',
          表活: '氨基酸（椰油酰甘氨酸钾）',
          pH: '5.5 弱酸性',
          适用: '需自备按压瓶',
          质地: '绵密泡沫',
        },
        priceA: 39,
        priceB: 35,
        coupon: { type: 'public', name: '店铺券', amount: 4, threshold: 30, note: '商品页可领，满 30 减 4' },
        promotion: '—',
        stock: '有货',
      },
    ],
    conclusion:
      '自用推荐「两支装」：拼团 + 百亿补贴 + 渠道券后约 79 元，单支成本最低；首次尝试可先买「单支装」试肤。替换装适合已回购的老用户。',
  },
]

/** 优惠类型获取策略（设计稿 3.2 v0.3）——用于领券指引页的平台权益矩阵 */
export const platformBenefits = [
  { platform: 'taobao', name: '店铺券 / 商品券（券后价）', viaApi: true, how: 'API 双价展示' },
  { platform: 'taobao', name: '跨店满减 / 单品直降', viaApi: true, how: 'API 展示促销利益点' },
  { platform: 'taobao', name: '淘金币（账号维度）', viaApi: false, how: 'RAG 规则 → 下单页勾选淘金币' },
  { platform: 'taobao', name: '消费券（政府/平台发放）', viaApi: false, how: 'RAG 规则 → 提示领取入口' },
  { platform: 'taobao', name: '天降红包（千人千面）', viaApi: false, how: '不承诺 → 下单页留意专属红包' },
  { platform: 'jd', name: 'PLUS 会员价', viaApi: true, how: 'API 双价展示 + 画像记录会员身份' },
  { platform: 'jd', name: '优惠券 / 拼购价', viaApi: true, how: 'API 双价展示' },
  { platform: 'pdd', name: '百亿补贴', viaApi: true, how: 'API 标识 + 补贴价展示' },
  { platform: 'pdd', name: '拼团价 / 店铺券', viaApi: true, how: 'API 双价展示' },
  { platform: 'pdd', name: '首页限时折扣（千人千面）', viaApi: false, how: '不承诺 → 以页面实时价为准' },
]

/** 券类型知识（设计稿 3.2 双价展示策略） */
export const couponTypes = [
  {
    key: 'public',
    name: '公开券',
    color: '#0abf7e',
    desc: '店铺券 / 平台券 / 满减券，用户自己在商品页、店铺页或领券中心即可领取。',
    rule: '给出具体领券路径与使用门槛（满 X 可用）。',
  },
  {
    key: 'channel',
    name: '渠道专享券（隐藏券 / 联盟券）',
    color: '#ff9d00',
    desc: '必须通过推广渠道才能领取的券。不是所有人都能领到。',
    rule: '明确说明使用限制，同时展示「能否领到券」两个价格：能领 → B 价；领不到 → A 价。不误导。',
  },
]

/** 领券步骤（通用指引，非推广链接——设计稿已定：不提供 CPS 推广链接） */
export const couponSteps = {
  taobao: [
    '打开商品页，查看「优惠券」区域，点击领取店铺券 / 商品券',
    '进入店铺首页「领券中心」查看店铺专属券',
    '结算页确认跨店满减已勾选（如每满 300 减 50）',
    '账号有淘金币的话，在下单页勾选淘金币抵扣',
  ],
  jd: [
    '商品页「促销」区域点击领取平台券 / 店铺券',
    'PLUS 会员在结算页确认按 PLUS 价结算',
    '领券中心搜索品类券，可与店铺券叠加时优先叠加',
    '结算页核对「到手价」与我们的测算是否一致',
  ],
  pdd: [
    '商品页直接显示拼团价，选择「单独拼团」参团',
    '查看商品标题旁「百亿补贴」标识，补贴价自动生效',
    '店铺券在商品页一键领取，满门槛自动抵扣',
    '首页限时折扣等千人千面权益以页面实时价为准',
  ],
}

/** 统一适配层 4 接口（设计稿 3.2）——Demo 中由 Mock 数据直接模拟返回 */
export const apiContract = [
  { fn: 'search_product(keyword)', desc: '候选商品列表' },
  { fn: 'get_item_detail(item_id)', desc: '商品详情 + SKU 款式信息' },
  { fn: 'get_price_with_coupon(item_id)', desc: '公开价 / 券后价 / 活动价' },
  { fn: 'get_coupon_info(item_id)', desc: '券类型 / 面额 / 使用限制 / 领券路径' },
]

/** 根据用户输入做最简单的意图匹配（Demo 演示用，真实链路由 A1 理解/路由 Agent 完成） */
export function matchProduct(text) {
  const t = (text || '').toLowerCase()
  const linkHit = /item\.taobao|jd\.com\/|pinduoduo|yangkeduo/.test(t)
  // 标题匹配 → 关键词表匹配 → 链接兜底
  const byTitle = products.find((p) => t.includes(p.title.replace(/\s/g, '').slice(0, 4)))
  if (byTitle) return { product: byTitle, viaLink: linkHit }
  const dict = [
    ['耳机', 'p-earphone'], ['降噪', 'p-earphone'], ['蓝牙', 'p-earphone'],
    ['保温杯', 'p-bottle'], ['杯子', 'p-bottle'], ['水杯', 'p-bottle'],
    ['洁面', 'p-cleanser'], ['洗面奶', 'p-cleanser'], ['护肤', 'p-cleanser'],
  ]
  for (const [kw, id] of dict) {
    if (t.includes(kw)) return { product: products.find((p) => p.id === id), viaLink: linkHit }
  }
  if (linkHit) return { product: products[0], viaLink: true }
  return { product: null, viaLink: linkHit }
}
