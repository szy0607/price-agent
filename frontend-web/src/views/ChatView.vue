<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { PhArchive, PhChatsCircle, PhCpu, PhGearSix, PhPackage, PhPaperPlaneRight, PhPlus, PhShoppingCart, PhX } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
import { listCartItems, listConversations, listConversationMessages, listOwnedItems, resolveImageUrl, sendChatMessage } from '../utils/api'

const placeholderImage = `${import.meta.env.BASE_URL}images/placeholder-item.png`
function imageFallback(event) { event.target.src = placeholderImage }

// ---------- 会话：懒创建，activeConversationId = null 即「新咨询」草稿 ----------
const conversations = ref([])
const activeConversationId = ref(null)
const messages = ref([])
const loadingConversations = ref(false)
const loadingMessages = ref(false)

// ---------- 右侧商品面板（勾选随每条消息作为 item_refs 发出） ----------
const cartItems = ref([])
const ownedItems = ref([])
const selectedRefs = ref(new Set()) // key 形如 "cart:12" / "owned:3"
const panelOpen = ref(false) // 移动端抽屉

const input = ref('')
const sending = ref(false)
const errorMessage = ref('')
const listRef = ref(null)
const modelSummary = { label: '默认模型', detail: '由设置中的默认 API Key 提供' }

// 最近一条 assistant 消息实际用的模型名（后端按 user 消息为 NULL 的口径存的）
const lastReplyModel = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    if (messages.value[i].role === 'assistant') return messages.value[i].model || null
  }
  return null
})

const activeTitle = computed(() => {
  if (activeConversationId.value === null) return '新咨询'
  return conversations.value.find((c) => c.id === activeConversationId.value)?.title || '会话'
})

// 与后端 _fallback_title 同口径：折叠空白、去首尾标点、截断 100——草稿标题先本地算，刷新后以服务端为准
function fallbackTitle(text) {
  const folded = ' '.join(text.split()).replace(/^[。！？!?.,，；;：:、~～…\s]+|[。！？!?.,，；;：:、~～…\s]+$/g, '')
  return folded.slice(0, 100) || '新咨询'
}

const selectedList = computed(() => [...selectedRefs.value].map((key) => {
  const [src, id] = key.split(':')
  const pool = src === 'cart' ? cartItems.value : ownedItems.value
  const item = pool.find((i) => i.id === Number(id))
  return item ? { src, id: item.id, name: item.name, category: item.category, image: item.image } : null
}).filter(Boolean))

function refKey(src, id) { return `${src}:${id}` }
function toggleRef(src, id) {
  const key = refKey(src, id)
  if (selectedRefs.value.has(key)) selectedRefs.value.delete(key)
  else selectedRefs.value.add(key)
}
function removeRef(src, id) { selectedRefs.value.delete(refKey(src, id)) }

function scrollToBottom() {
  nextTick(() => { if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight })
}

async function loadConversations() {
  loadingConversations.value = true
  try {
    conversations.value = await listConversations()
  } catch {
    conversations.value = []
  } finally {
    loadingConversations.value = false
  }
}

async function loadPickerItems() {
  try {
    const [cart, owned] = await Promise.all([listCartItems(), listOwnedItems()])
    cartItems.value = cart || []
    ownedItems.value = owned || []
    // 商品可能已在别处删掉：勾选键对齐存活集合，免得发送时后端 40001
    const alive = new Set([
      ...cartItems.value.map((i) => refKey('cart', i.id)),
      ...ownedItems.value.map((i) => refKey('owned', i.id)),
    ])
    for (const key of [...selectedRefs.value]) {
      if (!alive.has(key)) selectedRefs.value.delete(key)
    }
  } catch {
    // 面板加载失败不阻塞对话：只是没有可引用商品
  }
}

async function openConversation(id) {
  if (sending.value) return
  activeConversationId.value = id
  loadingMessages.value = true
  errorMessage.value = ''
  try {
    messages.value = await listConversationMessages(id)
  } catch (error) {
    errorMessage.value = error.message || '历史消息加载失败'
    messages.value = []
  } finally {
    loadingMessages.value = false
    scrollToBottom()
  }
}

function startNewChat() {
  if (sending.value) return
  activeConversationId.value = null
  messages.value = []
  errorMessage.value = ''
  scrollToBottom()
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  errorMessage.value = ''
  input.value = ''
  // 乐观上屏：后端先落 user 再调模型、失败也留痕，本地先渲染与库一致
  messages.value.push({ id: `local-user-${Date.now()}`, role: 'user', content: text })
  sending.value = true
  scrollToBottom()
  try {
    const result = await sendChatMessage({
      conversationId: activeConversationId.value,
      text,
      itemRefs: selectedList.value,
    })
    messages.value.push({ id: `local-reply-${Date.now()}`, role: 'assistant', content: result.reply, model: result.model })
    if (activeConversationId.value === null) {
      // 懒创建落地：记住服务端返回的真实 id，草稿标题转正，插到列表最前
      activeConversationId.value = result.conversation_id
      conversations.value.unshift({ id: result.conversation_id, title: fallbackTitle(text), update_time: new Date().toISOString() })
    } else {
      // 已有会话：服务端 touch 已推进 update_time，本地同步把它挪到最前
      const index = conversations.value.findIndex((c) => c.id === activeConversationId.value)
      if (index > 0) {
        const [row] = conversations.value.splice(index, 1)
        conversations.value.unshift(row)
      }
    }
  } catch (error) {
    errorMessage.value = error.message || '发送失败，请稍后重试。'
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  await Promise.all([loadConversations(), loadPickerItems()])
})
</script>

<template>
  <!-- 单根节点：路由过渡的契约（tests/frontend-contracts.test.mjs），移动端抽屉也必须在根内 -->
  <div>
    <div class="grid h-[calc(100dvh-4.5rem)] w-full grid-cols-1 overflow-hidden bg-zinc-50 md:grid-cols-[240px_minmax(0,1fr)_300px] dark:bg-zinc-950">
    <!-- 左：会话列表（真实数据，懒创建） -->
    <aside class="hidden min-h-0 flex-col border-r border-zinc-200 px-3 py-4 md:flex dark:border-zinc-800">
      <button type="button" class="flex h-10 items-center gap-2 rounded-lg border border-zinc-300 px-3 text-sm font-medium text-zinc-800 hover:bg-white dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900" :disabled="sending" @click="startNewChat">
        <PhPlus :size="17" />新咨询
      </button>
      <div class="mt-5 px-2 text-xs font-medium text-zinc-500">会话</div>
      <div class="mt-2 flex-1 space-y-1 overflow-y-auto">
        <p v-if="loadingConversations" class="px-3 py-2 text-xs text-zinc-400">加载中…</p>
        <p v-else-if="!conversations.length" class="px-3 py-2 text-xs text-zinc-400">还没有会话，发第一条消息即创建</p>
        <button v-for="conversation in conversations" :key="conversation.id" type="button" class="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm" :class="activeConversationId === conversation.id ? 'bg-white font-medium text-zinc-950 shadow-sm dark:bg-zinc-900 dark:text-white' : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900'" :disabled="sending" @click="openConversation(conversation.id)">
          <PhChatsCircle :size="17" class="shrink-0" /><span class="truncate">{{ conversation.title }}</span>
        </button>
      </div>
    </aside>

    <!-- 中：对话主区 -->
    <section class="flex min-h-0 min-w-0 flex-col">
      <header class="flex h-[4.5rem] shrink-0 items-center justify-between gap-3 border-b border-zinc-200/80 bg-white/70 px-4 backdrop-blur-sm sm:px-7 dark:border-zinc-800 dark:bg-zinc-950/70">
        <div class="flex min-w-0 items-center gap-2.5">
          <div class="min-w-0">
            <h1 class="truncate text-sm font-semibold text-zinc-950 dark:text-white">{{ activeTitle }}</h1>
            <div class="mt-0.5 flex min-h-4 min-w-0 items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
              <PhCpu :size="13" weight="duotone" class="shrink-0" />
              <span class="truncate font-medium">{{ modelSummary.label }}</span>
              <span class="shrink-0 text-zinc-300 dark:text-zinc-700">·</span>
              <span class="truncate">{{ modelSummary.detail }}</span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="flex h-9 items-center gap-1.5 rounded-lg border border-zinc-300 px-2.5 text-xs font-medium text-zinc-700 md:hidden dark:border-zinc-700 dark:text-zinc-200" @click="panelOpen = true">
            <PhPackage :size="15" />引用商品<span v-if="selectedList.length" class="text-accent">{{ selectedList.length }}</span>
          </button>
          <button type="button" class="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-600 hover:bg-zinc-100 md:hidden dark:text-zinc-300 dark:hover:bg-zinc-800" title="新咨询" aria-label="新咨询" :disabled="sending" @click="startNewChat"><PhPlus :size="19" /></button>
          <RouterLink to="/settings" class="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800" title="模型设置" aria-label="模型设置"><PhGearSix :size="19" /></RouterLink>
        </div>
      </header>

      <div v-if="conversations.length > 1" class="border-b border-zinc-200 px-4 py-2 md:hidden dark:border-zinc-800">
        <select :value="activeConversationId ?? ''" aria-label="选择会话" class="h-9 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900" :disabled="sending" @change="openConversation(Number($event.target.value))">
          <option value="" disabled>新咨询</option>
          <option v-for="conversation in conversations" :key="conversation.id" :value="conversation.id">{{ conversation.title }}</option>
        </select>
      </div>

      <div ref="listRef" class="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-7">
        <div v-if="selectedList.length" class="mx-auto mb-5 flex max-w-3xl flex-wrap items-center gap-2 rounded-xl border border-blue-100 bg-blue-50/70 px-3 py-2 text-xs text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/30 dark:text-blue-200">
          <PhPackage :size="14" class="shrink-0" />
          <span class="shrink-0">已引用 {{ selectedList.length }} 件商品：</span>
          <span v-for="ref_ in selectedList" :key="`${ref_.src}-${ref_.id}`" class="inline-flex items-center gap-1 rounded-md bg-white/80 px-1.5 py-0.5 font-medium dark:bg-zinc-900/80">
            {{ ref_.name }}
            <button type="button" class="text-blue-400 hover:text-blue-600" :aria-label="`取消引用 ${ref_.name}`" @click="removeRef(ref_.src, ref_.id)"><PhX :size="11" /></button>
          </span>
        </div>
        <div v-if="!messages.length && !loadingMessages" class="mx-auto flex h-full max-w-lg flex-col items-center justify-center text-center">
          <BrandIcon :size="35" class="text-accent" />
          <h2 class="mt-5 text-xl font-semibold text-zinc-950 dark:text-white">开始咨询</h2>
          <p class="mt-3 text-sm text-zinc-500">先在 <RouterLink to="/settings" class="font-medium text-accent underline">设置</RouterLink> 中保存 API Key 并设为默认。</p>
          <p class="mt-2 text-sm text-zinc-500">在右侧勾选购物车 / 物品库的商品，模型回答时会一并参考。</p>
        </div>
        <template v-else>
          <div class="mx-auto max-w-3xl space-y-5">
            <div v-for="message in messages" :key="message.id" class="flex" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
              <div class="max-w-[85%] whitespace-pre-wrap break-words px-4 py-3 text-sm leading-6 sm:max-w-[78%]" :class="message.role === 'user' ? 'rounded-lg bg-accent text-white' : 'border-l-2 border-accent bg-white text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100'">{{ message.content }}</div>
            </div>
            <p v-if="lastReplyModel" class="text-xs text-zinc-400" role="status">本次回复由 {{ lastReplyModel }} 生成</p>
          </div>
        </template>
        <p v-if="loadingMessages" class="mt-4 text-center text-sm text-zinc-500" role="status">正在加载历史消息…</p>
        <p v-if="sending" class="mt-4 text-sm text-zinc-500" role="status">正在等待模型回复…</p>
      </div>

      <div class="shrink-0 border-t border-zinc-200 px-4 py-4 sm:px-7 dark:border-zinc-800">
        <div class="mx-auto max-w-3xl">
          <p v-if="errorMessage" class="mb-3 text-sm text-red-700 dark:text-red-300" role="alert">{{ errorMessage }} <RouterLink to="/settings" class="underline">查看设置</RouterLink></p>
          <form class="flex items-end gap-2" @submit.prevent="send">
            <textarea v-model="input" rows="2" maxlength="4000" placeholder="输入你的购物问题" class="min-h-12 max-h-32 min-w-0 flex-1 resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm leading-6 text-zinc-900 focus:border-accent focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" @keydown.enter.exact.prevent="send"></textarea>
            <button type="submit" :disabled="!input.trim() || sending" class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-accent text-white hover:bg-accent-strong disabled:opacity-50" title="发送" aria-label="发送"><PhPaperPlaneRight :size="19" weight="bold" /></button>
          </form>
          <p class="mt-2 text-xs text-zinc-500 dark:text-zinc-400">价格和优惠以平台页面为准。</p>
        </div>
      </div>
    </section>

    <!-- 右：商品引用面板（桌面常驻） -->
    <aside class="hidden min-h-0 flex-col border-l border-zinc-200 bg-white/60 md:flex dark:border-zinc-800 dark:bg-zinc-900/40">
      <div class="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-200 px-4 text-sm font-medium text-zinc-800 dark:border-zinc-800 dark:text-zinc-200">
        <PhPackage :size="16" />引用商品
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <template v-if="cartItems.length || ownedItems.length">
          <div v-if="cartItems.length" class="mb-4">
            <div class="mb-1.5 flex items-center gap-1.5 px-1 text-xs font-medium text-zinc-500"><PhShoppingCart :size="13" />购物车（想买）</div>
            <button v-for="item in cartItems" :key="`cart-${item.id}`" type="button" class="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800" :class="selectedRefs.has(refKey('cart', item.id)) ? 'bg-accent/10 ring-1 ring-accent/40' : ''" @click="toggleRef('cart', item.id)">
              <img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-9 w-9 shrink-0 rounded-md object-cover" @error="imageFallback" />
              <span class="min-w-0 flex-1"><span class="block truncate text-sm text-zinc-800 dark:text-zinc-200">{{ item.name }}</span><span class="block truncate text-xs text-zinc-400">{{ item.category || '未分类' }}</span></span>
              <span class="flex h-4 w-4 shrink-0 items-center justify-center rounded border" :class="selectedRefs.has(refKey('cart', item.id)) ? 'border-accent bg-accent text-white' : 'border-zinc-300 dark:border-zinc-600'"><span v-if="selectedRefs.has(refKey('cart', item.id))" class="text-[10px] leading-none">✓</span></span>
            </button>
          </div>
          <div v-if="ownedItems.length">
            <div class="mb-1.5 flex items-center gap-1.5 px-1 text-xs font-medium text-zinc-500"><PhArchive :size="13" />物品库（已持有）</div>
            <button v-for="item in ownedItems" :key="`owned-${item.id}`" type="button" class="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800" :class="selectedRefs.has(refKey('owned', item.id)) ? 'bg-accent/10 ring-1 ring-accent/40' : ''" @click="toggleRef('owned', item.id)">
              <img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-9 w-9 shrink-0 rounded-md object-cover" @error="imageFallback" />
              <span class="min-w-0 flex-1"><span class="block truncate text-sm text-zinc-800 dark:text-zinc-200">{{ item.name }}</span><span class="block truncate text-xs text-zinc-400">{{ item.category || '未分类' }}</span></span>
              <span class="flex h-4 w-4 shrink-0 items-center justify-center rounded border" :class="selectedRefs.has(refKey('owned', item.id)) ? 'border-accent bg-accent text-white' : 'border-zinc-300 dark:border-zinc-600'"><span v-if="selectedRefs.has(refKey('owned', item.id))" class="text-[10px] leading-none">✓</span></span>
            </button>
          </div>
        </template>
        <div v-else class="px-2 py-6 text-center text-xs text-zinc-400">
          还没有商品<br />去 <RouterLink to="/cart" class="text-accent underline">购物车</RouterLink> 或 <RouterLink to="/items" class="text-accent underline">物品库</RouterLink> 添加
        </div>
      </div>
      <p class="shrink-0 border-t border-zinc-200 px-4 py-2.5 text-xs text-zinc-400 dark:border-zinc-800">勾选的商品会随每条消息一起发给模型参考</p>
    </aside>
  </div>

  <!-- 右：商品引用面板（移动端抽屉） -->
  <div v-if="panelOpen" class="fixed inset-0 z-40 md:hidden">
    <div class="absolute inset-0 bg-black/40" @click="panelOpen = false"></div>
    <aside class="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col bg-white dark:bg-zinc-900">
      <div class="flex h-12 shrink-0 items-center justify-between border-b border-zinc-200 px-4 text-sm font-medium text-zinc-800 dark:border-zinc-800 dark:text-zinc-200">
        <span class="flex items-center gap-2"><PhPackage :size="16" />引用商品</span>
        <button type="button" class="text-zinc-500 hover:text-zinc-800" aria-label="关闭" @click="panelOpen = false"><PhX :size="18" /></button>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <template v-if="cartItems.length || ownedItems.length">
          <div v-if="cartItems.length" class="mb-4">
            <div class="mb-1.5 flex items-center gap-1.5 px-1 text-xs font-medium text-zinc-500"><PhShoppingCart :size="13" />购物车（想买）</div>
            <button v-for="item in cartItems" :key="`m-cart-${item.id}`" type="button" class="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800" :class="selectedRefs.has(refKey('cart', item.id)) ? 'bg-accent/10 ring-1 ring-accent/40' : ''" @click="toggleRef('cart', item.id)">
              <img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-9 w-9 shrink-0 rounded-md object-cover" @error="imageFallback" />
              <span class="min-w-0 flex-1"><span class="block truncate text-sm text-zinc-800 dark:text-zinc-200">{{ item.name }}</span><span class="block truncate text-xs text-zinc-400">{{ item.category || '未分类' }}</span></span>
              <span class="flex h-4 w-4 shrink-0 items-center justify-center rounded border" :class="selectedRefs.has(refKey('cart', item.id)) ? 'border-accent bg-accent text-white' : 'border-zinc-300 dark:border-zinc-600'"><span v-if="selectedRefs.has(refKey('cart', item.id))" class="text-[10px] leading-none">✓</span></span>
            </button>
          </div>
          <div v-if="ownedItems.length">
            <div class="mb-1.5 flex items-center gap-1.5 px-1 text-xs font-medium text-zinc-500"><PhArchive :size="13" />物品库（已持有）</div>
            <button v-for="item in ownedItems" :key="`m-owned-${item.id}`" type="button" class="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800" :class="selectedRefs.has(refKey('owned', item.id)) ? 'bg-accent/10 ring-1 ring-accent/40' : ''" @click="toggleRef('owned', item.id)">
              <img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-9 w-9 shrink-0 rounded-md object-cover" @error="imageFallback" />
              <span class="min-w-0 flex-1"><span class="block truncate text-sm text-zinc-800 dark:text-zinc-200">{{ item.name }}</span><span class="block truncate text-xs text-zinc-400">{{ item.category || '未分类' }}</span></span>
              <span class="flex h-4 w-4 shrink-0 items-center justify-center rounded border" :class="selectedRefs.has(refKey('owned', item.id)) ? 'border-accent bg-accent text-white' : 'border-zinc-300 dark:border-zinc-600'"><span v-if="selectedRefs.has(refKey('owned', item.id))" class="text-[10px] leading-none">✓</span></span>
            </button>
          </div>
        </template>
        <div v-else class="px-2 py-6 text-center text-xs text-zinc-400">
          还没有商品<br />去 <RouterLink to="/cart" class="text-accent underline">购物车</RouterLink> 或 <RouterLink to="/items" class="text-accent underline">物品库</RouterLink> 添加
        </div>
      </div>
      <p class="shrink-0 border-t border-zinc-200 px-4 py-2.5 text-xs text-zinc-400 dark:border-zinc-800">勾选的商品会随每条消息一起发给模型参考</p>
    </aside>
  </div>
  </div>
</template>
