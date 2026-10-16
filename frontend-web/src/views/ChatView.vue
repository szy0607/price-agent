<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { PhArchive, PhChatsCircle, PhCpu, PhPackage, PhPaperPlaneRight, PhPlus, PhShoppingCart, PhStop, PhX } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
import ItemChip from '../components/ItemChip.vue'
import ItemRow from '../components/ItemRow.vue'
import { marked } from 'marked'
import { listCartItems, listConversations, listConversationMessages, listOwnedItems, streamChatMessage } from '../utils/api'

marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text) {
  return marked.parse(text || '')
}

// 后端 item_refs 上限，与 chat_sche.py 的 max_length=5 同口径：前端先拦，
// 否则第 6 件能勾上但发送必被 pydantic 拒（40001）
const MAX_REFS = 5
const REF_MARK = '【用户引用商品】'

// user 消息落库时是「【用户引用商品】\n<每行一条 src#id 名称｜specs>\n\n原话」
// （后端 chat_service._format_item 的格式）。这里拆回结构化 refs + 原话渲染，
// 免得历史消息把商品块原文裸露给用户。拆不动就整体当纯文本，不丢内容。
function parseUserContent(content) {
  const raw = content || ''
  if (!raw.startsWith(REF_MARK)) return { refs: [], text: raw }
  const rest = raw.slice(REF_MARK.length)
  const cut = rest.indexOf('\n\n')
  if (cut === -1) return { refs: [], text: raw }
  const refs = rest.slice(0, cut).split('\n').filter(Boolean).map((line) => {
    const matched = /^([a-z]+)#(\d+)\s+(.*)$/.exec(line)
    if (!matched) return null
    const name = matched[3].split('｜')[0].trim()
    return name ? { src: matched[1], id: Number(matched[2]), name } : null
  }).filter(Boolean)
  if (!refs.length) return { refs: [], text: raw }
  return { refs, text: rest.slice(cut + 2) }
}

// 消息统一结构 { id, role, text, refs, model, status }：历史加载与乐观上屏走同一形状，
// 否则同一条消息刷新前后显示不一致（乐观上屏没有商品块文本）
function toMessage(row) {
  if (row.role === 'user') {
    const { refs, text } = parseUserContent(row.content)
    return { id: row.id, role: row.role, text, refs, model: null, status: row.status ?? 'completed' }
  }
  return { id: row.id, role: row.role, text: row.content, refs: [], model: row.model ?? null, status: row.status ?? 'completed' }
}

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
// 四态：idle 空闲 / streaming 正在收字 / stopping 已点停止，等服务端落库 / error 出错
// stopping 必须单独存在：abort 只是断开连接，服务端还在异步写库，立刻解锁会让用户
// 连发两条，assistant 缺失导致上下文断裂（设计文档 §5.9）
const sendState = ref('idle')
const sending = computed(() => sendState.value !== 'idle')
const errorMessage = ref('')
const listRef = ref(null)
const modelSummary = { label: '默认模型', detail: '由设置中的默认 API Key 提供' }
const abortRef = ref(null)

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
  const folded = text.replace(/\s+/g, ' ').trim().replace(/^[。！？!?.,，；;：:、~～…\s]+|[。！？!?.,，；;：:、~～…\s]+$/g, '')
  return folded.slice(0, 100) || '新咨询'
}

const selectedList = computed(() => [...selectedRefs.value].map((key) => {
  const [src, id] = key.split(':')
  const pool = src === 'cart' ? cartItems.value : ownedItems.value
  const item = pool.find((i) => i.id === Number(id))
  return item ? { src, id: item.id, name: item.name, category: item.category, image: item.image } : null
}).filter(Boolean))

function refKey(src, id) { return `${src}:${id}` }
const atMaxRefs = computed(() => selectedRefs.value.size >= MAX_REFS)
function toggleRef(src, id) {
  const key = refKey(src, id)
  if (selectedRefs.value.has(key)) selectedRefs.value.delete(key)
  else if (selectedRefs.value.size < MAX_REFS) selectedRefs.value.add(key)
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
    messages.value = (await listConversationMessages(id)).map(toMessage)
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
  sendState.value = 'streaming'
  // 乐观上屏：后端先落 user 再调模型、失败也留痕，本地先渲染与库一致。
  // refs 取快照（拷贝一份），发送成功后清勾选也不会把这条消息的引用清空。
  const snapshot = selectedList.value.map((ref_) => ({ src: ref_.src, id: ref_.id, name: ref_.name }))
  messages.value.push({ id: `local-user-${Date.now()}`, role: 'user', text, refs: snapshot, model: null, status: 'completed' })
  // 🔴 assistant 占位气泡必须在 fetch **之前** push：第一个 delta 到达时才有容器可追加。
  // text 为空 + status='streaming' → 模板渲染成「正在思考…」（meta 到首个 delta 有 1~3 秒空窗，
  // 这段时间不能白屏，见设计文档 §6.5）
  const replyId = `local-reply-${Date.now()}`
  messages.value.push({ id: replyId, role: 'assistant', text: '', refs: [], model: null, status: 'streaming' })
  scrollToBottom()

  const controller = new AbortController()
  abortRef.value = controller
  const reply = messages.value[messages.value.length - 1]
  let interrupted = false

  try {
    await streamChatMessage(
      {
        conversationId: activeConversationId.value,
        text,
        itemRefs: selectedList.value,
      },
      (event, data) => {
        if (event === 'meta') {
          reply.model = data.model
          if (activeConversationId.value === null) {
            // 懒创建落地：meta 先于任何文本到达，标题转正不用等模型答完
            activeConversationId.value = data.conversation_id
            conversations.value.unshift({
              id: data.conversation_id,
              title: fallbackTitle(text),
              update_time: new Date().toISOString(),
            })
          } else {
            const index = conversations.value.findIndex((c) => c.id === activeConversationId.value)
            if (index > 0) {
              const [row] = conversations.value.splice(index, 1)
              conversations.value.unshift(row)
            }
          }
          scrollToBottom()
        } else if (event === 'delta') {
          reply.text += data.text
          scrollToBottom()
        } else if (event === 'error') {
          // 后端已翻译成用户可读中文；失败不能只存在于流里，输入框上方也要显示
          errorMessage.value = data.error
        } else if (event === 'done') {
          reply.status = data.status
          if (data.message_id) reply.id = data.message_id
          if (data.status === 'interrupted') interrupted = true
        }
        // event === 'agent'：子 agent「在调用」提示位，当前后端还没发，先按协议留着
      },
      controller.signal,
    )
    // 流正常读完：服务端此时已落库，sendState 才回到 idle
    sendState.value = 'idle'
    // 勾选即「这条消息的附件」，发完即清（10-14 的「跨消息保持」口径废止）；
    // 只在成功收流后清——失败时留着让用户直接重试，不必重勾一遍
    selectedRefs.value.clear()
  } catch (error) {
    if (error.name === 'AbortError' || interrupted) {
      // 主动中断：abort 只断开连接，**服务端还在异步落库**（设计文档 §5.9）。
      // 立刻解锁会让用户连发两条，而上一条 assistant 可能还没写进去。
      // 保守做法：先转 stopping，稍后重拉历史确认落库，再解锁。
      sendState.value = 'stopping'
      reply.status = 'interrupted'
      await refreshAfterInterrupt()
      sendState.value = 'idle'
    } else {
      errorMessage.value = error.message || '发送失败，请稍后重试。'
      // 生成失败：可能是空输出（服务端不落 assistant），把占位气泡撤掉，
      // 避免留一个永远转圈的空气泡
      const index = messages.value.findIndex((m) => m.id === replyId)
      if (index !== -1 && !reply.text) messages.value.splice(index, 1)
      sendState.value = 'idle'
    }
  } finally {
    abortRef.value = null
    scrollToBottom()
  }
}

// 中断后重拉当前会话，确认服务端真的落库了再解锁输入框。
// 若那一轮 assistant 没落进去（极端情况），把它补成 interrupted 占位，
// 免得历史里出现「用户问了但没回答」的空洞。
async function refreshAfterInterrupt() {
  const conversationId = activeConversationId.value
  if (conversationId === null) return
  try {
    const rows = await listConversationMessages(conversationId)
    const fresh = rows.map(toMessage)
    const lastReply = [...fresh].reverse().find((m) => m.role === 'assistant')
    if (lastReply && (lastReply.status === 'interrupted' || lastReply.text)) {
      messages.value = fresh
      return
    }
  } catch {
    /* 拉不到就保持现状：至少用户还能看到本地那条文本 */
  }
}

function stopGenerating() {
  if (sendState.value !== 'streaming') return
  sendState.value = 'stopping'
  abortRef.value?.abort()
}

onBeforeUnmount(() => {
  // 切路由/关页面时也要断流，否则生成器还在跑、后台还在写库
  abortRef.value?.abort()
})

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
        </div>
      </header>

      <div v-if="conversations.length > 1" class="border-b border-zinc-200 px-4 py-2 md:hidden dark:border-zinc-800">
        <select :value="activeConversationId ?? ''" aria-label="选择会话" class="h-9 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900" :disabled="sending" @change="openConversation(Number($event.target.value))">
          <option value="" disabled>新咨询</option>
          <option v-for="conversation in conversations" :key="conversation.id" :value="conversation.id">{{ conversation.title }}</option>
        </select>
      </div>

      <div ref="listRef" class="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-7">
        <div v-if="!messages.length && !loadingMessages" class="mx-auto flex h-full max-w-lg flex-col items-center justify-center text-center">
          <BrandIcon :size="35" class="text-accent" />
          <h2 class="mt-5 text-xl font-semibold text-zinc-950 dark:text-white">开始咨询</h2>
          <p class="mt-3 text-sm text-zinc-500">先在 <RouterLink to="/settings" class="font-medium text-accent underline">设置</RouterLink> 中保存 API Key 并设为默认。</p>
          <p class="mt-2 text-sm text-zinc-500">在右侧勾选购物车 / 物品库的商品，模型回答时会一并参考。</p>
        </div>
        <template v-else>
          <div class="mx-auto max-w-3xl space-y-5">
            <div v-for="message in messages" :key="message.id" class="flex" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
              <div class="max-w-[85%] break-words px-4 py-3 text-sm leading-6 sm:max-w-[78%]" :class="message.role === 'user' ? 'rounded-lg bg-accent text-white' : 'border-l-2 border-accent bg-white text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100'">
                <div v-if="message.refs && message.refs.length" class="mb-2 flex flex-wrap gap-1.5">
                  <ItemChip v-for="ref_ in message.refs" :key="`${ref_.src}-${ref_.id}`" :src="ref_.src" :name="ref_.name" :on-accent="message.role === 'user'" />
                </div>
                <!-- 🔴 没有文本且status='streaming' = 占位气泡。meta 到首个 delta 之间
                     有 1~3 秒空窗，这段时间渲染成「正在思考…」，不能白屏（设计文档 §6.5） -->
                <span v-if="message.role === 'assistant' && !message.text" class="text-zinc-400">
                  {{ message.status === 'streaming' ? '正在思考…' : '' }}
                  <span v-if="message.status === 'streaming'" class="ml-0.5 inline-block animate-pulse">▍</span>
                </span>
                <span v-else-if="message.role === 'assistant'" class="md-body" v-html="renderMarkdown(message.text)"></span>
                <span v-else class="whitespace-pre-wrap">{{ message.text }}</span>
                <!-- 生成结局角标：中断/失败在刷新后也要看得见，所以历史消息也渲染
                     （status 来自后端 MessageOutSchema，不是前端本地状态） -->
                <p v-if="message.role === 'assistant' && message.status && message.status !== 'streaming' && message.status !== 'completed'" class="mt-2 text-xs" :class="message.status === 'interrupted' ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400'">
                  {{ message.status === 'interrupted' ? '已停止' : '生成失败' }}
                </p>
              </div>
            </div>
            <p v-if="lastReplyModel" class="text-xs text-zinc-400" role="status">本次回复由 {{ lastReplyModel }} 生成</p>
          </div>
        </template>
        <p v-if="loadingMessages" class="mt-4 text-center text-sm text-zinc-500" role="status">正在加载历史消息…</p>
      </div>

      <div class="shrink-0 border-t border-zinc-200 px-4 py-4 sm:px-7 dark:border-zinc-800">
        <div class="mx-auto max-w-3xl">
          <!-- 引用区放在输入框这一屏里（不随消息滚动），否则对话一长就看不到自己引了哪些商品 -->
          <div v-if="selectedList.length" class="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-blue-100 bg-blue-50/70 px-3 py-2 text-xs text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/30 dark:text-blue-200">
            <PhPackage :size="14" class="shrink-0" />
            <span class="shrink-0">已引用 {{ selectedList.length }} 件商品<template v-if="atMaxRefs">（上限 {{ MAX_REFS }} 件）</template>：</span>
            <ItemChip v-for="ref_ in selectedList" :key="`${ref_.src}-${ref_.id}`" :src="ref_.src" :name="ref_.name" removable @remove="removeRef(ref_.src, ref_.id)" />
          </div>
          <p v-if="errorMessage" class="mb-3 text-sm text-red-700 dark:text-red-300" role="alert">{{ errorMessage }} <RouterLink to="/settings" class="underline">查看设置</RouterLink></p>
          <form class="flex items-end gap-2" @submit.prevent="send">
            <textarea v-model="input" rows="2" maxlength="4000" :placeholder="sendState === 'stopping' ? '正在停止…' : '输入你的购物问题'" :disabled="sendState === 'stopping'" class="min-h-12 max-h-32 min-w-0 flex-1 resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm leading-6 text-zinc-900 focus:border-accent focus:outline-none disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" @keydown.enter.exact.prevent="send"></textarea>
            <!-- 🔴 stopping 期间按钮保持禁用、不能变回发送：abort 只断开连接，服务端还在
                 异步写库，立刻解锁会让用户连发两条（设计文档 §5.9） -->
            <button v-if="sendState === 'streaming'" type="button" class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200" title="停止生成" aria-label="停止生成" @click="stopGenerating"><PhStop :size="18" weight="fill" /></button>
            <button v-else type="submit" :disabled="!input.trim() || sendState === 'stopping'" class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-accent text-white hover:bg-accent-strong disabled:opacity-50" title="发送" aria-label="发送"><PhPaperPlaneRight :size="19" weight="bold" /></button>
          </form>
          <p class="mt-2 text-xs text-zinc-500 dark:text-zinc-400">价格和优惠以平台页面为准。</p>
        </div>
      </div>
    </section>

    <!-- 右：商品引用面板（桌面常驻）。购物车 / 物品库上下各占一半，各自框内独立滚动，
         所以 min-h-0 不能少——flex 子项默认 min-height:auto，少了它会被内容撑破变整页滚动 -->
    <aside class="hidden min-h-0 flex-col overflow-hidden border-l border-zinc-200 bg-white/60 md:flex dark:border-zinc-800 dark:bg-zinc-900/40">
      <div class="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-200 px-4 text-sm font-medium text-zinc-800 dark:border-zinc-800 dark:text-zinc-200">
        <PhPackage :size="16" />引用商品
      </div>

      <div class="flex min-h-0 flex-1 flex-col border-b border-zinc-200 dark:border-zinc-800">
        <div class="flex shrink-0 items-center gap-1.5 px-4 py-2 text-xs font-medium text-zinc-500">
          <PhShoppingCart :size="13" />购物车（想买）<span class="text-zinc-400">{{ cartItems.length }}</span>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          <ItemRow
            v-for="item in cartItems"
            :key="`cart-${item.id}`"
            :item="item"
            src="cart"
            :selected="selectedRefs.has(refKey('cart', item.id))"
            :disabled="atMaxRefs && !selectedRefs.has(refKey('cart', item.id))"
            @toggle="toggleRef('cart', item.id)"
          />
          <p v-if="!cartItems.length" class="px-2 py-4 text-center text-xs text-zinc-400">
            购物车还没有商品<br /><RouterLink to="/cart" class="text-accent underline">去添加</RouterLink>
          </p>
        </div>
      </div>

      <div class="flex min-h-0 flex-1 flex-col">
        <div class="flex shrink-0 items-center gap-1.5 px-4 py-2 text-xs font-medium text-zinc-500">
          <PhArchive :size="13" />物品库（已持有）<span class="text-zinc-400">{{ ownedItems.length }}</span>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
          <ItemRow
            v-for="item in ownedItems"
            :key="`owned-${item.id}`"
            :item="item"
            src="owned"
            :selected="selectedRefs.has(refKey('owned', item.id))"
            :disabled="atMaxRefs && !selectedRefs.has(refKey('owned', item.id))"
            @toggle="toggleRef('owned', item.id)"
          />
          <p v-if="!ownedItems.length" class="px-2 py-4 text-center text-xs text-zinc-400">
            物品库还没有商品<br /><RouterLink to="/items" class="text-accent underline">去添加</RouterLink>
          </p>
        </div>
      </div>

      <p class="shrink-0 border-t border-zinc-200 px-4 py-2.5 text-xs text-zinc-400 dark:border-zinc-800">最多引用 {{ MAX_REFS }} 件，发送后自动清空</p>
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
            <ItemRow
              v-for="item in cartItems"
              :key="`m-cart-${item.id}`"
              :item="item"
              src="cart"
              :selected="selectedRefs.has(refKey('cart', item.id))"
              :disabled="atMaxRefs && !selectedRefs.has(refKey('cart', item.id))"
              @toggle="toggleRef('cart', item.id)"
            />
          </div>
          <div v-if="ownedItems.length">
            <div class="mb-1.5 flex items-center gap-1.5 px-1 text-xs font-medium text-zinc-500"><PhArchive :size="13" />物品库（已持有）</div>
            <ItemRow
              v-for="item in ownedItems"
              :key="`m-owned-${item.id}`"
              :item="item"
              src="owned"
              :selected="selectedRefs.has(refKey('owned', item.id))"
              :disabled="atMaxRefs && !selectedRefs.has(refKey('owned', item.id))"
              @toggle="toggleRef('owned', item.id)"
            />
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

<style scoped>
.md-body :deep(p) {
  margin: 0 0 0.6em;
  line-height: 1.7;
}
.md-body :deep(p:last-child) {
  margin-bottom: 0;
}
.md-body :deep(strong) {
  font-weight: 600;
  color: #18181b;
}
.md-body :deep(ul), .md-body :deep(ol) {
  margin: 0.4em 0 0.7em;
  padding-left: 1.4em;
}
.md-body :deep(li) {
  margin: 0.25em 0;
  line-height: 1.65;
}
.md-body :deep(li::marker) {
  color: #3b82f6;
}
.md-body :deep(code) {
  background: #f1f5f9;
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.88em;
  font-family: ui-monospace, monospace;
}
.md-body :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.3em 0.9em;
  border-left: 3px solid #3b82f6;
  background: #f8fafc;
  border-radius: 0 6px 6px 0;
  color: #475569;
}
.md-body :deep(a) {
  color: #2563eb;
  text-decoration: underline;
}
.md-body :deep(h1), .md-body :deep(h2), .md-body :deep(h3) {
  margin: 0.6em 0 0.3em;
  line-height: 1.3;
}
.md-body :deep(h3) { font-size: 1.05em; }
.md-body :deep(hr) {
  margin: 0.8em 0;
  border: 0;
  border-top: 1px solid #e2e8f0;
}
</style>
