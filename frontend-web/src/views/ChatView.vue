<script setup>
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { PhArrowBendUpLeft, PhBrain, PhCaretDown, PhCheck, PhCheckCircle, PhCopy, PhCpu, PhDatabase, PhPaperclip, PhPaperPlaneRight, PhUserCircle, PhX } from '@phosphor-icons/vue'
import DualPriceCard from '../components/DualPriceCard.vue'
import BrandIcon from '../components/BrandIcon.vue'
import { matchProduct, products, cheapest, PLATFORMS, PLAT_KEYS, bestPlat } from '../mock/data'
import { copyText } from '../utils/copy'
import { loadProfile, saveProfile, parseQuery, buildPersonalNote, profileSummary } from '../utils/profile'

const input = ref('')
const typing = ref(false)
const listRef = ref(null)
const fileInput = ref(null)
const attachedImage = ref(null)
const imgError = ref('')
const copiedKey = ref(null)
const imageUrls = new Set()

// 用户画像（localStorage 持久化）
const profile = ref(loadProfile())
const summary = computed(() => profileSummary(profile.value))
const memoryItems = computed(() => [
  profile.value.budget ? `预算 ¥${profile.value.budget} 内` : '',
  `常用${summary.value.platLabel}`,
  ...summary.value.tags,
].filter(Boolean))

// 会话模型：左栏是会话切换器，每个会话持有独立的消息流、平台与当前商品
let uid = 1
const traceBlueprint = [
  { agent: 'A1', label: '意图与画像解析', tool: 'parse_intent()', detail: '识别预算、平台偏好和购买场景', icon: markRaw(PhBrain) },
  { agent: 'A2', label: '商品情报 Agent', tool: 'search_product()', detail: '定位商品、款式与关键规格', icon: markRaw(PhDatabase) },
  { agent: 'A3', label: '价格情报 Agent', tool: 'get_price_with_coupon()', detail: '采集三平台公开价、券后价与会员价', icon: markRaw(PhCpu) },
  { agent: 'A5', label: '推荐引导 Agent', tool: 'build_personal_note()', detail: '根据价格和你的偏好生成建议', icon: markRaw(PhUserCircle) },
]

function makeTrace(state = 'complete') {
  return {
    state,
    expanded: state === 'running',
    steps: traceBlueprint.map((step, index) => ({
      ...step,
      status: state === 'running' ? (index === 0 ? 'running' : 'queued') : 'complete',
    })),
  }
}

function buildConversation(product, plat) {
  const prompt = product.id === 'p-headphone'
    ? '3000 以内推荐降噪耳机，我平时通勤用'
    : product.id === 'p-bottle'
      ? '保温杯京东买划算吗？我更在意轻便'
      : '我是学生，洁面乳怎么买更省？'
  return [
    { id: uid++, role: 'user', type: 'text', text: prompt },
    { id: uid++, role: 'agent', type: 'trace', trace: makeTrace() },
    { id: uid++, role: 'agent', type: 'card', product, plat, lead: `已采集「${product.name}」的款式与价格情报：` },
    { id: uid++, role: 'agent', type: 'compare', product, plat },
    { id: uid++, role: 'agent', type: 'recommend', product, plat },
  ]
}

const sessions = reactive(
  products.map((p, i) => {
    const plat = bestPlat(p).plat
    return {
      id: p.id,
      title: `${p.brand} · ${p.name}`,
      time: ['10:24', '昨天', '周二'][i],
      product: p,
      plat,
      activeProduct: p,
      messages: buildConversation(p, plat),
    }
  }),
)
const activeSessionId = ref(sessions[0].id)
const activeSession = computed(() => sessions.find((s) => s.id === activeSessionId.value))
const activeProduct = computed(() => activeSession.value.activeProduct)
// 平台切换跟随当前会话
const sessionPlat = computed({
  get: () => activeSession.value.plat,
  set: (v) => (activeSession.value.plat = v),
})

function switchSession(id) {
  if (activeSessionId.value === id) return
  activeSessionId.value = id
  nextTick(scrollToBottom)
}

function scrollToBottom() {
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

const samples = ['3000 以内推荐降噪耳机', '保温杯京东买划算吗', '我是学生，洁面乳怎么买最省']

function push(msg) {
  const message = { id: uid++, ...msg }
  activeSession.value.messages.push(message)
  nextTick(scrollToBottom)
  return message
}

function toggleTrace(message) {
  if (message.type === 'trace') message.trace.expanded = !message.trace.expanded
}

function send(text) {
  const content = (text ?? input.value).trim()
  if ((!content && !attachedImage.value) || typing.value) return

  // —— 个性化：从 query 读取 / 更新用户信息 ——
  const { updates, notes } = parseQuery(content)
  profile.value.consultCount += 1
  profile.value.updatedAt = Date.now()
  if (Object.keys(updates).length) {
    Object.assign(profile.value, updates)
    saveProfile(profile.value)
    // 有画像更新时，优先展示对应平台
    if (updates.preferredPlatform) sessionPlat.value = updates.preferredPlatform
  } else {
    saveProfile(profile.value)
  }

  const img = attachedImage.value
  push({ role: 'user', type: 'text', text: content, image: img })
  const traceMessage = push({ role: 'agent', type: 'trace', trace: makeTrace('running') })
  traceBlueprint.forEach((_, index) => {
    window.setTimeout(() => {
      traceMessage.trace.steps.forEach((step, stepIndex) => {
        step.status = stepIndex < index ? 'complete' : stepIndex === index ? 'running' : 'queued'
      })
      if (index === traceBlueprint.length - 1) {
        traceMessage.trace.steps[index].status = 'complete'
        traceMessage.trace.state = 'complete'
        traceMessage.trace.expanded = false
      }
    }, 220 + index * 220)
  })
  input.value = ''
  attachedImage.value = null
  imgError.value = ''
  typing.value = true

  // 画像确认话术（让用户感知到"被记住了"）
  if (notes.length) {
    push({ role: 'agent', type: 'text', text: notes.join('\n') })
  }
  window.setTimeout(() => reply(content, !!img, notes.length > 0), 600)
}

function pickImage(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    imgError.value = '仅支持图片格式（JPG / PNG / WebP）'
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    imgError.value = '图片不能超过 5MB'
    return
  }
  if (attachedImage.value) {
    URL.revokeObjectURL(attachedImage.value)
    imageUrls.delete(attachedImage.value)
  }
  attachedImage.value = URL.createObjectURL(file)
  imageUrls.add(attachedImage.value)
  imgError.value = ''
}

function removeImage() {
  if (attachedImage.value) {
    URL.revokeObjectURL(attachedImage.value)
    imageUrls.delete(attachedImage.value)
  }
  attachedImage.value = null
  imgError.value = ''
}

function resizeInput(event) {
  const el = event.target
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 128)}px`
}

async function copyCode(product, plat) {
  const key = `${product.id}-${plat}`
  const code = cheapest(product, plat).prices[plat].code
  const ok = await copyText(code)
  if (!ok) return false
  copiedKey.value = key
  window.setTimeout(() => {
    if (copiedKey.value === key) copiedKey.value = null
  }, 2000)
  return true
}

function reply(content, hasImage, hasNotes) {
  const { product, viaLink } = matchProduct(content)
  if (!product) {
    push({
      role: 'agent',
      type: 'text',
      text: hasImage
        ? '已收到商品图片。我还需要商品链接或商品名（如「索尼耳机」「象印保温杯」「芙丽芳丝」）来定位款式，才能采集价格情报。'
        : '我暂时没识别到具体商品。可以：① 粘贴淘宝 / 京东 / 拼多多商品链接；② 直接说品类或品牌，比如「3000 以内降噪耳机」。',
    })
    typing.value = false
    return
  }
  activeSession.value.activeProduct = product
  const plat = sessionPlat.value
  push({
    role: 'agent',
    type: 'card',
    product,
    plat,
    lead: hasImage
      ? '已收到图片并定位到商品，通过联盟查券 API 采集到款式与价格情报：'
      : viaLink
        ? '已通过联盟查券 API 采集到该商品的款式与价格情报：'
        : `已采集「${product.name}」的款式与价格情报：`,
  })
  window.setTimeout(() => push({ role: 'agent', type: 'compare', product, plat }), 500)
  window.setTimeout(() => {
    push({ role: 'agent', type: 'recommend', product, plat })
    typing.value = false
  }, 1000)
}

const best = computed(() => (activeProduct.value ? cheapest(activeProduct.value, sessionPlat.value) : null))
const personalNotes = computed(() => (activeProduct.value ? buildPersonalNote(activeProduct.value, sessionPlat.value, profile.value) : []))
const platTabs = PLAT_KEYS.map((k) => ({ key: k, name: PLATFORMS[k].name, accent: PLATFORMS[k].accent }))

onMounted(() => {
  const q = new URLSearchParams(window.location.search).get('q')
  if (q) send(q)
})

onBeforeUnmount(() => {
  imageUrls.forEach((url) => URL.revokeObjectURL(url))
  imageUrls.clear()
})
</script>

<template>
  <div class="grid h-[calc(100dvh-4rem)] w-full grid-cols-1 overflow-hidden md:grid-cols-[260px_minmax(0,1fr)] lg:grid-cols-[260px_minmax(0,1fr)_380px]">
    <!-- 左栏：会话切换器 -->
    <aside class="hidden min-h-0 flex-col border-r border-zinc-200/70 md:flex dark:border-zinc-800">
      <div class="px-5 pb-2 pt-5 text-xs font-medium text-zinc-500 dark:text-zinc-400">咨询会话</div>
      <div class="flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
        <button
          v-for="s in sessions"
          :key="s.id"
          class="w-full rounded-[10px] px-3 py-2.5 text-left transition-colors"
          :disabled="typing"
          :class="
            activeSessionId === s.id
              ? 'bg-accent-soft dark:bg-accent/15'
              : 'hover:bg-zinc-200/60 disabled:cursor-not-allowed disabled:opacity-60 dark:hover:bg-zinc-800/70'
          "
          @click="switchSession(s.id)"
        >
          <div
            class="truncate text-[13px]"
            :class="activeSessionId === s.id ? 'font-medium text-accent-strong dark:text-blue-300' : ''"
          >
            {{ s.title }}
          </div>
          <div class="mt-0.5 text-[11px] text-zinc-500 dark:text-zinc-400">{{ s.time }}</div>
        </button>
      </div>
      <div class="border-t border-zinc-200/70 px-5 py-4 text-[11px] leading-relaxed text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        Demo 由本地 Mock 数据驱动；画像仅存本机（localStorage），正式版由后端 User Profile Agent 管理。
      </div>
    </aside>

    <!-- 中栏：对话 -->
    <section class="flex min-h-0 min-w-0 flex-col">
      <div class="flex items-center justify-between gap-3 border-b border-zinc-200/70 px-4 py-2.5 dark:border-zinc-800 sm:px-8">
        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent dark:bg-accent/15 dark:text-blue-300"><BrandIcon :size="18" /></span>
          <div class="min-w-0"><div class="truncate text-xs font-semibold">智能咨询工作台</div><div class="mt-0.5 truncate text-[10px] text-zinc-500 dark:text-zinc-400">对话、价格情报与推荐在同一条链路完成</div></div>
        </div>
        <div class="hidden shrink-0 items-center gap-2.5 text-[10px] text-zinc-500 sm:flex dark:text-zinc-400"><span class="flex items-center gap-1"><span class="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>联盟数据源</span><span class="h-3 w-px bg-zinc-200 dark:bg-zinc-700"></span><span>画像已启用</span></div>
      </div>
      <div class="flex items-center gap-3 border-b border-zinc-200/70 px-4 py-2.5 md:hidden dark:border-zinc-800">
        <label for="mobile-session" class="shrink-0 text-xs font-medium text-zinc-500 dark:text-zinc-400">当前会话</label>
        <select
          id="mobile-session"
          class="min-w-0 flex-1 rounded-[9px] border border-zinc-200 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          :value="activeSessionId"
          :disabled="typing"
          @change="switchSession($event.target.value)"
        >
          <option v-for="s in sessions" :key="s.id" :value="s.id">{{ s.title }}</option>
        </select>
        <span class="shrink-0 text-[11px] text-zinc-400">{{ PLATFORMS[sessionPlat].name }}</span>
      </div>
      <div ref="listRef" class="w-full flex-1 space-y-6 overflow-y-auto px-4 py-6 sm:px-8">
        <div v-for="m in activeSession.messages" :key="m.id" class="msg-in flex" :class="m.role === 'user' ? 'justify-end' : 'justify-start'">
          <!-- 用户 -->
          <div v-if="m.role === 'user'" class="max-w-[75%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm leading-relaxed text-white">
            <img v-if="m.image" :src="m.image" :alt="m.text || '用户上传的商品图片'" class="mb-2 max-h-48 rounded-lg object-cover" />
            <p v-if="m.text">{{ m.text }}</p>
          </div>

          <!-- Agent -->
          <div v-else class="flex w-full max-w-none gap-3">
            <span class="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft dark:bg-accent/20">
              <BrandIcon :size="18" />
            </span>
            <div class="min-w-0 flex-1">
              <!-- 纯文本（含画像确认话术） -->
              <div v-if="m.type === 'text'" class="whitespace-pre-wrap rounded-2xl rounded-tl-md border border-zinc-200 bg-white px-4 py-2.5 text-sm leading-relaxed dark:border-zinc-800 dark:bg-zinc-900">
                {{ m.text }}
              </div>

              <!-- Agent 协作过程：默认收起，用户可展开查看每个工具节点 -->
              <div v-else-if="m.type === 'trace'" class="overflow-hidden rounded-2xl rounded-tl-md border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
                <button :aria-expanded="m.trace.expanded" class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/60" @click="toggleTrace(m)">
                  <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent dark:bg-accent/15 dark:text-blue-300">
                    <PhCpu :size="16" weight="bold" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="block text-[13px] font-semibold">{{ m.trace.state === 'running' ? '正在分析这次咨询' : '本次咨询已完成分析' }}</span>
                    <span class="mt-0.5 block text-[11px] text-zinc-500 dark:text-zinc-400">{{ m.trace.state === 'running' ? 'Agent 正在协作获取可验证的信息' : '过程可追溯，结论来自商品与价格数据' }}</span>
                  </span>
                  <span v-if="m.trace.state === 'complete'" class="flex items-center gap-1 text-[11px] text-price-b dark:text-emerald-400"><PhCheckCircle :size="14" weight="fill" /> 已完成</span>
                  <span class="text-zinc-400 transition-transform" :class="m.trace.expanded ? 'rotate-180' : ''"><PhCaretDown :size="16" /></span>
                </button>
                <div v-if="m.trace.expanded" class="border-t border-zinc-100 px-4 py-3 dark:border-zinc-800">
                  <div v-for="(step, stepIndex) in m.trace.steps" :key="step.agent" class="relative flex gap-3 pb-3 last:pb-0">
                    <div v-if="stepIndex < m.trace.steps.length - 1" class="absolute left-[11px] top-6 h-full w-px bg-zinc-200 dark:bg-zinc-700"></div>
                    <span class="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-md" :class="step.status === 'complete' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300' : step.status === 'running' ? 'bg-accent-soft text-accent dark:bg-accent/15 dark:text-blue-300' : 'bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500'">
                      <component :is="step.icon" :size="13" weight="bold" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="flex flex-wrap items-center gap-2 text-xs font-medium"><span class="font-mono text-[10px] text-zinc-400">{{ step.agent }}</span>{{ step.label }}<span v-if="step.status === 'running'" class="h-1.5 w-1.5 animate-pulse rounded-full bg-accent"></span><code class="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-normal text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">{{ step.tool }}</code></span>
                      <span class="mt-0.5 block text-[11px] leading-relaxed text-zinc-500 dark:text-zinc-400">{{ step.detail }}</span>
                    </span>
                  </div>
                </div>
              </div>

              <!-- 情报卡：三平台双价卡 -->
              <div v-else-if="m.type === 'card'" class="rounded-2xl rounded-tl-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
                <p class="text-[13px] text-zinc-600 dark:text-zinc-300">{{ m.lead }}</p>
                <div class="mt-3 flex items-center gap-3">
                  <img :src="m.product.image" :alt="m.product.name" class="h-12 w-12 rounded-lg object-cover" loading="lazy" />
                  <div class="min-w-0 flex-1">
                    <RouterLink :to="{ path: '/compare', query: { id: m.product.id } }" class="truncate text-sm font-semibold hover:text-accent">
                      {{ m.product.name }}
                    </RouterLink>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400">{{ m.product.brand }} · {{ m.product.skus.length }} 个款式 · 三平台比价</div>
                  </div>
                  <span class="font-mono text-sm font-bold text-price-b dark:text-emerald-400">¥{{ cheapest(m.product, m.plat).prices[m.plat].b }} 起</span>
                </div>
                <div class="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                  <RouterLink :to="{ path: '/compare', query: { id: m.product.id, plat: m.plat, source: 'chat' } }" class="inline-flex items-center rounded-[9px] border border-accent/30 bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent-strong transition-colors hover:bg-accent/10 dark:border-accent/30 dark:bg-accent/10 dark:text-blue-200">
                    加入对比工作台
                  </RouterLink>
                  <span class="text-[11px] text-zinc-400">可继续上传其他商品进行横向比较</span>
                </div>
                <div class="mt-3">
                  <DualPriceCard :product="m.product" v-model:plat="m.plat" />
                </div>
              </div>

              <!-- 对比摘要（按当前平台） -->
              <div v-else-if="m.type === 'compare'" class="overflow-hidden rounded-2xl rounded-tl-md border border-zinc-200 dark:border-zinc-800">
                <div class="flex items-center justify-between bg-white px-4 pt-3 dark:bg-zinc-900">
                  <span class="text-xs text-zinc-500 dark:text-zinc-400">三款横向对比 · {{ PLATFORMS[m.plat].name }}渠道价</span>
                  <RouterLink :to="{ path: '/compare', query: { id: m.product.id, plat: m.plat } }" class="text-xs text-accent hover:text-accent-strong">
                    完整参数对比
                  </RouterLink>
                </div>
                <table class="w-full bg-white text-left text-[13px] dark:bg-zinc-900">
                  <thead>
                    <tr class="bg-zinc-50 text-[11px] text-zinc-500 dark:bg-zinc-800/60 dark:text-zinc-400">
                      <th class="px-4 py-2.5 font-medium">款式</th>
                      <th class="px-4 py-2.5 text-right font-medium">公开价 A</th>
                      <th class="px-4 py-2.5 text-right font-medium">领券价 B</th>
                      <th class="hidden px-4 py-2.5 font-medium sm:table-cell">券</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-zinc-100 dark:divide-zinc-800">
                    <tr v-for="s in m.product.skus" :key="s.name">
                      <td class="px-4 py-2.5">{{ s.name }}</td>
                      <td class="px-4 py-2.5 text-right font-mono text-price-a dark:text-red-400">¥{{ s.prices[m.plat].a }}</td>
                      <td class="px-4 py-2.5 text-right font-mono font-semibold text-price-b dark:text-emerald-400">¥{{ s.prices[m.plat].b }}</td>
                      <td class="hidden px-4 py-2.5 sm:table-cell">
                        <span
                          class="rounded-md px-1.5 py-0.5 text-[11px]"
                          :class="s.prices[m.plat].coupon.type === 'public'
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
                            : 'bg-amber-100 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'"
                        >
                          {{ s.prices[m.plat].coupon.type === 'public' ? '公开券' : '渠道专享' }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- 推荐结论（含为你定制附注） -->
              <div v-else-if="m.type === 'recommend'" class="rounded-2xl rounded-tl-md border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
                <p class="text-sm leading-relaxed">{{ m.product.conclusion }}</p>
                <div
                  v-if="buildPersonalNote(m.product, m.plat, profile).length"
                  class="mt-3 rounded-[10px] bg-accent-soft px-3.5 py-2.5 text-[13px] leading-relaxed text-accent-strong dark:bg-accent/15 dark:text-blue-200"
                >
                  <p v-for="(n, i) in buildPersonalNote(m.product, m.plat, profile)" :key="i">· {{ n }}</p>
                </div>
                <div class="mt-3 flex flex-wrap items-center gap-3">
                  <RouterLink
                    :to="{ path: '/coupon', query: { id: m.product.id, plat: m.plat } }"
                    class="inline-flex items-center gap-1 rounded-[10px] bg-accent px-4 py-2 text-[13px] font-medium text-white transition-transform hover:bg-accent-strong active:scale-[0.98]"
                  >
                    查看领券步骤
                  </RouterLink>
                  <button
                    class="inline-flex items-center gap-1.5 rounded-[10px] border border-zinc-300 px-4 py-2 text-[13px] font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                    @click="copyCode(m.product, m.plat)"
                  >
                    <PhCheck v-if="copiedKey === `${m.product.id}-${m.plat}`" :size="14" weight="bold" class="text-price-b dark:text-emerald-400" />
                    <PhCopy v-else :size="14" />
                    {{ copiedKey === `${m.product.id}-${m.plat}` ? '已复制' : `复制${PLATFORMS[m.plat].name}口令` }}
                  </button>
                  <RouterLink :to="{ path: '/compare', query: { id: m.product.id, plat: m.plat } }" class="text-[13px] text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200">
                    完整参数对比
                  </RouterLink>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 打字中 -->
        <div v-if="typing" class="msg-in flex justify-start">
          <div class="flex gap-3">
            <span class="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft dark:bg-accent/20">
              <BrandIcon :size="18" />
            </span>
            <div class="flex items-center gap-1.5 rounded-2xl rounded-tl-md border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
              <span class="motion-safe:animate-bounce h-1.5 w-1.5 rounded-full bg-zinc-400 [animation-delay:0ms]"></span>
              <span class="motion-safe:animate-bounce h-1.5 w-1.5 rounded-full bg-zinc-400 [animation-delay:150ms]"></span>
              <span class="motion-safe:animate-bounce h-1.5 w-1.5 rounded-full bg-zinc-400 [animation-delay:300ms]"></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="border-t border-zinc-200/70 dark:border-zinc-800">
        <div class="w-full px-4 py-4 sm:px-8">
        <div class="mb-2.5 flex flex-wrap gap-1.5">
          <button
            v-for="s in samples"
            :key="s"
            class="rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600 transition-colors hover:border-accent hover:text-accent dark:border-zinc-700 dark:text-zinc-300"
            @click="send(s)"
          >
            {{ s }}
          </button>
        </div>
        <!-- 图片预览 -->
        <div v-if="attachedImage" class="mb-2.5 flex items-center gap-3 rounded-[10px] border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900">
          <img :src="attachedImage" alt="已选商品图片" class="h-11 w-11 shrink-0 rounded-lg object-cover" />
          <div class="min-w-0 flex-1 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
            <p class="truncate">已添加商品图片，将随消息一起发送</p>
            <p v-if="imgError" class="text-red-500 dark:text-red-400">{{ imgError }}</p>
          </div>
          <button
            aria-label="移除已添加的商品图片"
            class="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
            @click="removeImage"
          >
            <PhX :size="14" weight="bold" />
          </button>
        </div>
        <div class="flex items-end gap-2">
          <button
            class="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[10px] border border-zinc-300 text-zinc-500 transition-colors hover:border-accent hover:text-accent dark:border-zinc-700 dark:text-zinc-400"
            title="上传商品图片（≤ 5MB）"
            @click="fileInput?.click()"
          >
            <PhPaperclip :size="18" />
          </button>
          <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="pickImage" />
          <textarea
            v-model="input"
            rows="1"
            maxlength="200"
            placeholder="粘贴商品链接，或直接提问，如「3000 以内降噪耳机」，Enter 发送"
            class="max-h-32 flex-1 resize-none rounded-[10px] border border-zinc-300 bg-white px-3.5 py-2.5 text-sm placeholder:text-zinc-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 dark:border-zinc-700 dark:bg-zinc-900"
            @input="resizeInput"
            @keydown.enter.exact.prevent="send()"
          ></textarea>
          <button
            class="inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-4 py-2.5 text-sm font-medium text-white transition-transform enabled:hover:bg-accent-strong enabled:active:scale-[0.98] disabled:opacity-40"
            :disabled="(!input.trim() && !attachedImage) || typing"
            @click="send()"
          >
            <PhPaperPlaneRight :size="15" weight="bold" />
            发送
          </button>
        </div>
        <p class="mt-2 text-[11px] text-zinc-500 dark:text-zinc-400">
          AI 仅提供信息与建议，不代下单。价格以平台页面为准。
        </p>
        </div>
      </div>
    </section>

    <!-- 右栏：为你定制 + 商品情报面板 -->
    <aside class="hidden min-h-0 flex-col gap-4 overflow-y-auto border-l border-zinc-200/70 p-5 lg:flex dark:border-zinc-800">
      <!-- 用户画像卡 -->
      <div class="rounded-2xl border border-accent/25 bg-accent-soft p-4 dark:border-accent/30 dark:bg-accent/10">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-[13px] font-semibold text-accent-strong dark:text-blue-200">为你定制</div>
            <div class="mt-0.5 text-[10px] text-accent/70 dark:text-blue-300/70">User Profile Agent · 本机记忆</div>
          </div>
          <span class="rounded-md bg-white px-1.5 py-0.5 text-[10px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
            已咨询 {{ profile.consultCount }} 次
          </span>
        </div>
        <div class="mt-2.5 flex flex-wrap gap-1.5">
          <span v-for="item in memoryItems" :key="item" class="rounded-md bg-white px-2 py-1 text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            {{ item }}
          </span>
        </div>
        <div class="mt-3 rounded-[10px] border border-white/80 bg-white/60 px-3 py-2.5 dark:border-zinc-700/70 dark:bg-zinc-900/40">
          <div class="flex items-center justify-between text-[10px] font-medium text-zinc-500 dark:text-zinc-400"><span>记忆将影响</span><span class="font-mono text-accent">A1 → A5</span></div>
          <p class="mt-1 text-[11px] leading-relaxed text-zinc-600 dark:text-zinc-300">平台排序、预算筛选、会员价展示和推荐解释。</p>
        </div>
        <p class="mt-2.5 text-[11px] leading-relaxed text-zinc-500 dark:text-zinc-400">
          在提问里说预算、平台、身份（学生 / PLUS 等），我会记住并用于后续推荐。
        </p>
      </div>

      <template v-if="activeProduct">
        <div>
          <div class="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
            <PhArrowBendUpLeft :size="13" />
            当前咨询商品
          </div>
          <h3 class="mt-1.5 text-[15px] font-semibold tracking-tight">{{ activeProduct.name }}</h3>
        </div>

        <!-- 平台切换 + 双价卡 -->
        <div class="flex w-fit rounded-[10px] border border-zinc-200 bg-white p-1 dark:border-zinc-700 dark:bg-zinc-900">
          <button
            v-for="t in platTabs"
            :key="t.key"
            class="rounded-lg px-3.5 py-1.5 text-[13px] font-medium transition-colors"
            :class="
              sessionPlat === t.key
                ? 'text-white'
                : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
            "
            :style="sessionPlat === t.key ? { backgroundColor: t.accent } : {}"
            @click="sessionPlat = t.key"
          >
            {{ t.name }}
          </button>
        </div>
        <DualPriceCard :product="activeProduct" v-model:plat="sessionPlat" />

        <p class="rounded-[10px] bg-accent-soft px-4 py-3 text-[13px] leading-relaxed text-accent-strong dark:bg-accent/15 dark:text-blue-200">
          {{ activeProduct.conclusion }}
        </p>

        <!-- 为你定制附注 -->
        <div
          v-if="personalNotes.length"
          class="rounded-[10px] border border-zinc-200 px-4 py-3 text-[13px] leading-relaxed text-zinc-600 dark:border-zinc-700 dark:text-zinc-300"
        >
          <div class="mb-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400">针对你的建议</div>
          <p v-for="(n, i) in personalNotes" :key="i" class="leading-relaxed">· {{ n }}</p>
        </div>

        <RouterLink
          :to="{ path: '/coupon', query: { id: activeProduct.id, plat: sessionPlat } }"
          class="inline-flex items-center justify-center gap-1.5 rounded-[10px] border border-zinc-300 px-4 py-2.5 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          领券步骤（{{ PLATFORMS[sessionPlat].name }}最低 ¥{{ best.prices[sessionPlat].b }}）
        </RouterLink>
        <button
          class="inline-flex items-center justify-center gap-1.5 rounded-[10px] bg-accent px-4 py-2.5 text-sm font-medium text-white transition-transform enabled:hover:bg-accent-strong enabled:active:scale-[0.98]"
          @click="copyCode(activeProduct, sessionPlat)"
        >
          <PhCheck v-if="copiedKey === `${activeProduct.id}-${sessionPlat}`" :size="15" weight="bold" />
          <PhCopy v-else :size="15" />
          {{ copiedKey === `${activeProduct.id}-${sessionPlat}` ? '已复制' : `复制${PLATFORMS[sessionPlat].name}口令，去 App 下单` }}
        </button>
        <p class="text-[11px] leading-relaxed text-zinc-500 dark:text-zinc-400">{{ PLATFORMS[sessionPlat].name }}渠道口令，复制后打开对应 App 自动跳转。</p>
      </template>
      <!-- 空状态 -->
      <div v-else class="m-auto max-w-[24ch] text-center text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">
        发起咨询后，你的画像、商品情报、双价测算与推荐结论会显示在这里。
      </div>
    </aside>
  </div>
</template>
