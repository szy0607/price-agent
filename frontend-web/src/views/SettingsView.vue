<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  PhArrowClockwise, PhCheckCircle, PhEye, PhEyeSlash, PhFloppyDisk,
  PhKey, PhPencilSimple, PhPlus, PhSignOut, PhTrash, PhWarningCircle, PhX,
} from '@phosphor-icons/vue'
import { deleteApiKey, listApiKeys, logoutUser, saveApiKey } from '../utils/api'
import { clearAuth, getAuthUser } from '../utils/auth'

const router = useRouter()
const user = ref(getAuthUser())
const keys = ref([])
const loading = ref(true)
const pageError = ref('')
const feedback = ref('')
const editingProvider = ref('')
const selectedProvider = ref('openai')
const customProvider = ref('')
const keyValue = ref('')
const showKey = ref(false)
const saving = ref(false)
const formError = ref('')
const keyInput = ref(null)
const confirmTarget = ref(null)
const deleteDialog = ref(null)
const deleting = ref(false)
const signingOut = ref(false)

const providers = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: '通义千问' },
  { value: 'custom', label: '其他服务商' },
]
const providerNames = Object.fromEntries(providers.map((provider) => [provider.value, provider.label]))
const provider = computed(() => editingProvider.value || (selectedProvider.value === 'custom' ? customProvider.value.trim().toLowerCase() : selectedProvider.value))
const configuredProvider = computed(() => keys.value.find((item) => item.provider === provider.value))

function providerLabel(value) {
  return providerNames[value] || value
}

function displayTime(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadKeys() {
  loading.value = true
  pageError.value = ''
  keys.value = []
  try {
    keys.value = await listApiKeys()
  } catch (error) {
    if (error.status === 401) {
      clearAuth()
      await router.replace({ name: 'auth', query: { redirect: '/settings' } })
      return
    }
    pageError.value = error.status === 500 ? '密钥服务暂不可用' : (error.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function resetEditor() {
  editingProvider.value = ''
  keyValue.value = ''
  showKey.value = false
  formError.value = ''
}

async function editKey(item) {
  editingProvider.value = item.provider
  keyValue.value = ''
  showKey.value = false
  formError.value = ''
  await nextTick()
  keyInput.value?.focus()
}

async function save() {
  formError.value = ''
  feedback.value = ''
  if (!/^[a-z][a-z0-9_-]{0,63}$/.test(provider.value)) {
    formError.value = '服务商标识须以小写字母开头，只能包含字母、数字、下划线或连字符'
    return
  }
  const bytes = new TextEncoder().encode(keyValue.value)
  if (keyValue.value.length < 8 || bytes.length > 4096) {
    formError.value = 'API Key 须至少 8 个字符且不超过 4096 字节'
    return
  }
  saving.value = true
  const target = provider.value
  const replacement = Boolean(configuredProvider.value)
  try {
    await saveApiKey(target, keyValue.value)
    resetEditor()
    feedback.value = `${providerLabel(target)} ${replacement ? '已更新' : '已添加'}`
    await loadKeys()
  } catch (error) {
    formError.value = error.status === 500 ? '密钥服务暂不可用' : (error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!confirmTarget.value) return
  deleting.value = true
  const target = confirmTarget.value.provider
  try {
    await deleteApiKey(target)
    if (editingProvider.value === target) resetEditor()
    confirmTarget.value = null
    feedback.value = `${providerLabel(target)} 已移除`
    await loadKeys()
  } catch (error) {
    pageError.value = error.message || '移除失败'
    confirmTarget.value = null
  } finally {
    deleting.value = false
  }
}

async function openDelete(item) {
  confirmTarget.value = item
  await nextTick()
  deleteDialog.value?.focus()
}

async function signOut() {
  signingOut.value = true
  pageError.value = ''
  try {
    await logoutUser()
    clearAuth()
    await router.replace('/auth')
  } catch (error) {
    pageError.value = error.message || '退出失败'
  } finally {
    signingOut.value = false
  }
}

onMounted(loadKeys)
</script>

<template>
  <div class="min-h-full bg-zinc-50 dark:bg-zinc-950">
    <div class="mx-auto max-w-5xl px-5 pb-20 pt-9 sm:px-8 sm:pt-12">
      <div class="mb-9 border-b border-zinc-200 pb-6 dark:border-zinc-800">
        <h1 class="text-2xl font-semibold text-zinc-950 dark:text-white">设置</h1>
      </div>

      <p v-if="pageError" class="mb-6 flex flex-wrap items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-400/10 dark:text-red-300" role="alert">
        <PhWarningCircle :size="18" />{{ pageError }}
        <button type="button" class="ml-auto inline-flex items-center gap-1 font-medium underline" @click="loadKeys"><PhArrowClockwise :size="16" />重试</button>
      </p>
      <p v-if="feedback" class="mb-6 flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300" role="status">
        <PhCheckCircle :size="18" />{{ feedback }}
      </p>

      <section class="grid gap-5 border-b border-zinc-200 pb-9 dark:border-zinc-800 sm:grid-cols-[180px_minmax(0,1fr)]">
        <div>
          <h2 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">账号</h2>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-5">
          <div class="min-w-0">
            <p class="font-medium text-zinc-900 dark:text-white">{{ user?.username || '当前用户' }}</p>
            <p class="mt-1 break-all text-sm text-zinc-500 dark:text-zinc-400">{{ user?.user_email }}</p>
          </div>
          <button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg border border-zinc-300 px-3 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" :disabled="signingOut" @click="signOut">
            <PhSignOut :size="17" />退出登录
          </button>
        </div>
      </section>

      <section class="grid gap-5 py-9 sm:grid-cols-[180px_minmax(0,1fr)]">
        <div>
          <h2 class="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100"><PhKey :size="18" />API Key</h2>
        </div>
        <div class="min-w-0">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 pb-4 dark:border-zinc-800">
            <h3 class="text-base font-semibold text-zinc-900 dark:text-white">已连接的服务商</h3>
            <button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-accent px-3 text-sm font-medium text-white transition-colors hover:bg-accent-strong" @click="resetEditor(); keyInput?.focus()">
              <PhPlus :size="17" weight="bold" />添加密钥
            </button>
          </div>

          <div v-if="loading" class="py-9 text-sm text-zinc-500" role="status">加载中…</div>
          <div v-else-if="!pageError && keys.length === 0" class="border-b border-zinc-200 py-9 text-sm text-zinc-500 dark:border-zinc-800">尚未添加 API Key</div>
          <div v-for="item in keys" :key="item.provider" class="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 py-4 dark:border-zinc-800">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="break-all text-sm font-semibold text-zinc-900 dark:text-white">{{ providerLabel(item.provider) }}</span>
                <span v-if="item.status === 'invalid'" class="rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-400/10 dark:text-red-300">已失效</span>
                <span v-else class="rounded bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">已保存</span>
              </div>
              <p class="mt-1 font-mono text-sm text-zinc-600 dark:text-zinc-400">{{ item.masked_key }}</p>
              <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-500">更新于 {{ displayTime(item.update_time) }}</p>
            </div>
            <div class="flex items-center gap-2">
              <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-zinc-300 px-2.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" :aria-label="`替换 ${providerLabel(item.provider)} 的密钥`" @click="editKey(item)"><PhPencilSimple :size="16" />替换</button>
              <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-zinc-500 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-400/10 dark:hover:text-red-300" :title="`移除 ${providerLabel(item.provider)}`" :aria-label="`移除 ${providerLabel(item.provider)}`" @click="openDelete(item)"><PhTrash :size="18" /></button>
            </div>
          </div>

          <form class="mt-9 border-t border-zinc-200 pt-7 dark:border-zinc-800" @submit.prevent="save">
            <div class="mb-5 flex items-center justify-between gap-3">
              <h3 class="text-base font-semibold text-zinc-900 dark:text-white">{{ editingProvider ? `替换 ${providerLabel(editingProvider)}` : '添加 API Key' }}</h3>
              <button v-if="editingProvider" type="button" class="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white" @click="resetEditor">取消</button>
            </div>
            <label v-if="!editingProvider" class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              服务商
              <select v-model="selectedProvider" class="mt-2 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm text-zinc-900 focus:border-accent focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-white">
                <option v-for="item in providers" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label v-if="!editingProvider && selectedProvider === 'custom'" class="mt-5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              服务商标识
              <input v-model="customProvider" type="text" autocomplete="off" spellcheck="false" maxlength="64" placeholder="provider-name" class="mt-2 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm text-zinc-900 focus:border-accent focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" />
            </label>
            <label class="mt-5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              API Key
              <span class="relative mt-2 block">
                <input ref="keyInput" v-model="keyValue" :type="showKey ? 'text' : 'password'" autocomplete="new-password" autocapitalize="off" spellcheck="false" maxlength="4096" placeholder="粘贴 API Key" class="block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 pr-11 font-mono text-sm text-zinc-900 focus:border-accent focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" />
                <button type="button" class="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-zinc-500 hover:text-zinc-900 dark:hover:text-white" :title="showKey ? '隐藏输入' : '显示输入'" :aria-label="showKey ? '隐藏输入' : '显示输入'" @click="showKey = !showKey"><PhEyeSlash v-if="showKey" :size="18" /><PhEye v-else :size="18" /></button>
              </span>
            </label>
            <p v-if="configuredProvider && !editingProvider" class="mt-3 text-sm text-amber-700 dark:text-amber-300">保存后将替换已配置的 {{ providerLabel(provider) }} 密钥。</p>
            <p v-if="formError" class="mt-4 text-sm text-red-700 dark:text-red-300" role="alert">{{ formError }}</p>
            <div class="mt-5 flex justify-end">
              <button type="submit" :disabled="saving" class="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent-strong disabled:opacity-50"><PhFloppyDisk :size="17" />{{ saving ? '保存中…' : '保存密钥' }}</button>
            </div>
          </form>
        </div>
      </section>
    </div>

    <div v-if="confirmTarget" ref="deleteDialog" tabindex="-1" class="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/55 px-4" @click.self="confirmTarget = null" @keydown.esc="confirmTarget = null">
      <div role="alertdialog" aria-modal="true" aria-labelledby="delete-key-title" class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
        <div class="flex items-start justify-between gap-3">
          <h2 id="delete-key-title" class="text-base font-semibold text-zinc-900 dark:text-white">移除 {{ providerLabel(confirmTarget.provider) }} 密钥</h2>
          <button type="button" class="text-zinc-500 hover:text-zinc-900 dark:hover:text-white" title="关闭" aria-label="关闭" @click="confirmTarget = null"><PhX :size="19" /></button>
        </div>
        <p class="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-400">移除后，这个服务商将无法再使用该密钥。需要时可重新添加。</p>
        <div class="mt-6 flex justify-end gap-2">
          <button type="button" class="h-9 rounded-lg px-3 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800" @click="confirmTarget = null">取消</button>
          <button type="button" :disabled="deleting" class="inline-flex h-9 items-center gap-2 rounded-lg bg-red-600 px-3 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50" @click="remove"><PhTrash :size="16" />{{ deleting ? '移除中…' : '确认移除' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
