/**
 * 个人购物助手 · 用户画像（Demo 版）
 * 定位：通过用户的 query 读取 / 更新用户信息，做出个性化服务。
 * 本机 localStorage 持久化（仅存演示偏好，不采集敏感信息）。
 * 真实版：画像由后端 User Profile Agent 管理与更新，前端只读结果。
 */
import { PLATFORMS } from '../mock/data'

const PROFILE_KEY = 'price-agent-profile'

export const defaultProfile = {
  name: '访客',
  priceSensitive: true, // 价格敏感：优先性价比
  qualityFirst: false, // 品质优先：要旗舰 / 顶配
  preferredPlatform: 'jd', // 常用平台
  budget: null, // 预算上限（元）
  student: false, // 学生身份
  membership: [], // 会员身份：jdPlus / taobaoVIP
  interests: [], // 近期关注品类
  consultCount: 0, // 累计咨询次数
  updatedAt: null,
}

export function loadProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    if (raw) return { ...defaultProfile, ...JSON.parse(raw) }
  } catch {
    /* localStorage 不可用时使用默认画像 */
  }
  return { ...defaultProfile }
}

export function saveProfile(profile) {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
  } catch {
    /* 忽略写入失败 */
  }
}

/**
 * 从用户 query 中解析个人信息与意图（Demo 规则版）。
 * 返回 { updates: 需合并进画像的字段, notes: 面向用户的话术确认列表 }
 */
export function parseQuery(text) {
  const t = (text || '').trim()
  const updates = {}
  const notes = []

  // 预算：如「3000 以内」「预算 2500 左右」「不超过 2000 元」
  const budgetRe = /(?:预算|准备|打算|不超过|低于|控制在)\s*(\d{2,6})\s*(?:元|块钱|块)?|(\d{2,6})\s*(?:元|块钱|块)?\s*(?:以内|以下|内|左右|附近)/
  const bm = t.match(budgetRe)
  if (bm) {
    const val = Number(bm[1] || bm[2])
    if (val >= 10) {
      updates.budget = val
      notes.push(`已记住你的预算：${val} 元以内，推荐会优先落在预算内。`)
    }
  }

  // 平台偏好
  if (/淘宝|天猫/.test(t)) {
    updates.preferredPlatform = 'taobao'
    notes.push(`明白，本次优先展示淘宝渠道的券后价。`)
  } else if (/京东/.test(t)) {
    updates.preferredPlatform = 'jd'
    notes.push(`明白，本次优先展示京东渠道的券后价。`)
  } else if (/拼多多|pdd/i.test(t)) {
    updates.preferredPlatform = 'pdd'
    notes.push(`明白，本次优先展示拼多多百亿补贴价。`)
  }

  // 学生身份
  if (/学生|在校|大学生|宿舍/.test(t)) {
    updates.student = true
    notes.push(`已识别学生身份，会优先找学生党更友好的渠道价。`)
  }

  // 价格敏感 vs 品质优先
  if (/性价比|便宜|实惠|划算|省钱|学生/.test(t)) {
    updates.priceSensitive = true
    updates.qualityFirst = false
  } else if (/品质|旗舰|顶配|最好|最强|音质|高端/.test(t)) {
    updates.qualityFirst = true
    updates.priceSensitive = false
    notes.push(`收到，你更看重品质，我会把配置与体验放在价格前面说。`)
  }

  // 会员身份
  if (/plus/i.test(t)) {
    updates.membership = [...(loadProfile().membership || []), 'jdPlus']
    notes.push(`已记录你是京东 PLUS 会员，PLUS 价会直接展示。`)
  }
  if (/88vip|88会员/i.test(t)) {
    updates.membership = [...(loadProfile().membership || []), 'taobaoVIP']
    notes.push(`已记录你是淘宝 88VIP，结算时可叠加 95 折权益。`)
  }

  return { updates, notes }
}

/** 画像展示名（用于右栏面板） */
export function profileSummary(profile) {
  const tags = []
  if (profile.priceSensitive) tags.push('价格敏感')
  if (profile.qualityFirst) tags.push('品质优先')
  if (profile.student) tags.push('学生')
  if (profile.membership.includes('jdPlus')) tags.push('京东 PLUS')
  if (profile.membership.includes('taobaoVIP')) tags.push('88VIP')
  return {
    platLabel: PLATFORMS[profile.preferredPlatform]?.name || '京东',
    tags,
  }
}

/**
 * 生成「为你定制」推荐附注（展示在推荐结论之后）。
 * plat：当前展示的平台。
 */
export function buildPersonalNote(product, plat, profile) {
  const notes = []
  const bp = profile.preferredPlatform
  if (bp && plat === bp) notes.push(`你常用${PLATFORMS[bp].name}，这里优先展示了${PLATFORMS[bp].name}的券后价。`)
  if (profile.membership.includes('jdPlus') && plat === 'jd') notes.push(`你是京东 PLUS 会员，PLUS 价已一并展示（比券后价更低）。`)
  if (profile.membership.includes('taobaoVIP') && plat === 'taobao') notes.push(`88VIP 结算页可再叠 95 折，实际到手会更低。`)
  if (profile.student && plat === 'pdd') notes.push(`学生党：拼多多百亿补贴价通常是最低渠道，可优先考虑。`)
  if (profile.budget) {
    const min = Math.min(...product.skus.map((s) => s.prices[plat].b))
    if (min <= profile.budget) notes.push(`全场最低到手 ¥${min}，在你的 ${profile.budget} 元预算内。`)
    else notes.push(`该平台最低到手 ¥${min}，略超你的 ${profile.budget} 元预算，可看其他平台的券后价。`)
  }
  return notes
}
