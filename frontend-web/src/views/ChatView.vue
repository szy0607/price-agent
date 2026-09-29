<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { PhChatsCircle, PhGearSix, PhPaperPlaneRight, PhPlus } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
import { getModelSetting, sendChatMessage } from '../utils/api'

let nextId = 1
const createSession = () => ({ id: nextId++, title: '新咨询', messages: [], error: '' })
const sessions = ref([createSession()])
const activeId = ref(sessions.value[0].id)
const activeSession = computed(() => sessions.value.find((session) => session.id === activeId.value))
const input = ref('')
const sending = ref(false)
const listRef = ref(null)
const modelSetting = ref({ provider: null, options: [] })
const activeModel = computed(() => modelSetting.value.options.find((item) => item.provider === modelSetting.value.provider))

function scrollToBottom() {
  nextTick(() => { if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight })
}

function addSession() {
  const session = createSession()
  sessions.value.unshift(session)
  activeId.value = session.id
  input.value = ''
  scrollToBottom()
}

function switchSession(id) {
  activeId.value = Number(id)
  scrollToBottom()
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  const session = activeSession.value
  session.error = ''
  if (!modelSetting.value.provider) {
    session.error = '请先在设置中保存 API Key 并选择咨询模型。'
    return
  }

  session.messages.push({ id: nextId++, role: 'user', text })
  if (session.title === '新咨询') session.title = text.slice(0, 24)
  input.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const messages = session.messages.slice(-12).map((message) => ({
      role: message.role, content: message.text,
    }))
    const result = await sendChatMessage(messages)
    session.messages.push({ id: nextId++, role: 'assistant', text: result.content })
  } catch (error) {
    session.error = error.message || '咨询失败，请稍后重试。'
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  try {
    modelSetting.value = await getModelSetting()
  } catch {
    activeSession.value.error = '无法读取模型设置，请稍后重试。'
  }
  const question = new URLSearchParams(window.location.search).get('q')
  if (question) input.value = question.slice(0, 4000)
})
</script>

<template>
  <div class="grid h-[calc(100dvh-4rem)] w-full grid-cols-1 overflow-hidden bg-zinc-50 md:grid-cols-[240px_minmax(0,1fr)] dark:bg-zinc-950">
    <aside class="hidden min-h-0 flex-col border-r border-zinc-200 px-3 py-4 md:flex dark:border-zinc-800">
      <button type="button" class="flex h-10 items-center gap-2 rounded-lg border border-zinc-300 px-3 text-sm font-medium text-zinc-800 hover:bg-white dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900" @click="addSession">
        <PhPlus :size="17" />新咨询
      </button>
      <div class="mt-5 px-2 text-xs font-medium text-zinc-500">会话</div>
      <div class="mt-2 flex-1 space-y-1 overflow-y-auto">
        <button v-for="session in sessions" :key="session.id" type="button" class="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm" :class="activeId === session.id ? 'bg-white font-medium text-zinc-950 shadow-sm dark:bg-zinc-900 dark:text-white' : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900'" :disabled="sending" @click="switchSession(session.id)">
          <PhChatsCircle :size="17" class="shrink-0" /><span class="truncate">{{ session.title }}</span>
        </button>
      </div>
    </aside>

    <section class="flex min-h-0 min-w-0 flex-col">
      <header class="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-zinc-200 px-4 sm:px-7 dark:border-zinc-800">
        <div class="flex min-w-0 items-center gap-2.5">
          <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent dark:bg-accent/20"><BrandIcon :size="19" /></span>
          <div class="min-w-0">
            <h1 class="truncate text-sm font-semibold text-zinc-950 dark:text-white">{{ activeSession.title }}</h1>
            <p class="truncate text-xs text-zinc-500 dark:text-zinc-400">{{ activeModel ? `${activeModel.label} · ${activeModel.model}` : '未选择咨询模型' }}</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-600 hover:bg-zinc-100 md:hidden dark:text-zinc-300 dark:hover:bg-zinc-800" title="新咨询" aria-label="新咨询" @click="addSession"><PhPlus :size="19" /></button>
          <RouterLink to="/settings" class="flex h-9 w-9 items-center justify-center rounded-lg text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800" title="模型设置" aria-label="模型设置"><PhGearSix :size="19" /></RouterLink>
        </div>
      </header>

      <div v-if="sessions.length > 1" class="border-b border-zinc-200 px-4 py-2 md:hidden dark:border-zinc-800">
        <select :value="activeId" aria-label="选择会话" class="h-9 w-full rounded-lg border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900" :disabled="sending" @change="switchSession($event.target.value)">
          <option v-for="session in sessions" :key="session.id" :value="session.id">{{ session.title }}</option>
        </select>
      </div>

      <div ref="listRef" class="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-7">
        <div v-if="!activeSession.messages.length" class="mx-auto flex h-full max-w-lg flex-col items-center justify-center text-center">
          <BrandIcon :size="35" class="text-accent" />
          <h2 class="mt-5 text-xl font-semibold text-zinc-950 dark:text-white">开始咨询</h2>
          <p v-if="!activeModel" class="mt-3 text-sm text-zinc-500">先在 <RouterLink to="/settings" class="font-medium text-accent underline">设置</RouterLink> 中保存 API Key 并选择模型。</p>
        </div>
        <div v-else class="mx-auto max-w-3xl space-y-5">
          <div v-for="message in activeSession.messages" :key="message.id" class="flex" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
            <div class="max-w-[85%] whitespace-pre-wrap break-words px-4 py-3 text-sm leading-6 sm:max-w-[78%]" :class="message.role === 'user' ? 'rounded-lg bg-accent text-white' : 'border-l-2 border-accent bg-white text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100'">{{ message.text }}</div>
          </div>
          <p v-if="sending" class="text-sm text-zinc-500" role="status">正在等待模型回复…</p>
        </div>
      </div>

      <div class="shrink-0 border-t border-zinc-200 px-4 py-4 sm:px-7 dark:border-zinc-800">
        <div class="mx-auto max-w-3xl">
          <p v-if="activeSession.error" class="mb-3 text-sm text-red-700 dark:text-red-300" role="alert">{{ activeSession.error }} <RouterLink to="/settings" class="underline">查看设置</RouterLink></p>
          <form class="flex items-end gap-2" @submit.prevent="send">
            <textarea v-model="input" rows="2" maxlength="4000" placeholder="输入你的购物问题" class="min-h-12 max-h-32 min-w-0 flex-1 resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-sm leading-6 text-zinc-900 focus:border-accent focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" @keydown.enter.exact.prevent="send"></textarea>
            <button type="submit" :disabled="!input.trim() || sending" class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-accent text-white hover:bg-accent-strong disabled:opacity-50" title="发送" aria-label="发送"><PhPaperPlaneRight :size="19" weight="bold" /></button>
          </form>
          <p class="mt-2 text-xs text-zinc-500 dark:text-zinc-400">价格和优惠以平台页面为准。</p>
        </div>
      </div>
    </section>
  </div>
</template>
