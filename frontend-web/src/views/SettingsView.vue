<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowClockwise, PhCheckCircle, PhEye, PhEyeSlash, PhKey, PhPencilSimple, PhPlus, PhStar, PhTrash, PhWarningCircle, PhX } from '@phosphor-icons/vue'
import { createApiKey, createEmbeddingKey, deleteApiKey, deleteEmbeddingKey, listApiKeys, listEmbeddingKeys, setDefaultApiKey, setDefaultEmbeddingKey, updateApiKey, updateEmbeddingKey } from '../utils/api'
import { clearAuth } from '../utils/auth'

const router = useRouter()
const keys = ref([])
const eKeys = ref([])
const loading = ref(true)
const eLoading = ref(true)
const saving = ref(false)
const deleting = ref(false)
const settingDefault = ref(false)
const pageError = ref('')
const ePageError = ref('')
const feedback = ref('')
const formError = ref('')
const showForm = ref(false)
const showKey = ref(false)
const editingId = ref(null)
const formKind = ref('chat')   // 'chat' 推理模型 | 'embedding' 向量模型，两套列表复用同一表单
const confirmTarget = ref(null)
const confirmKind = ref('chat')
const keyInput = ref(null)
const deleteDialog = ref(null)
const form = ref({ provider: '', base_url: '', api_key: '', model_name: '' })

function resetForm(kind) {
  editingId.value = null
  formKind.value = kind
  form.value = { provider: '', base_url: '', api_key: '', model_name: '' }
  showKey.value = false
  formError.value = ''
  showForm.value = true
  nextTick(() => keyInput.value?.focus())
}

function editKey(kind, item) {
  editingId.value = item.id
  formKind.value = kind
  form.value = { provider: item.provider || '', base_url: item.base_url || '', api_key: '', model_name: item.model_name || '' }
  showKey.value = false
  formError.value = ''
  showForm.value = true
  nextTick(() => keyInput.value?.focus())
}

function closeForm() { if (!saving.value) showForm.value = false }
function displayKey(item) { return item.key_suffix ? `••••${item.key_suffix}` : '已保存' }

async function loadKeys() {
  loading.value = true
  pageError.value = ''
  try { keys.value = await listApiKeys() } catch (error) {
    if (error.status === 401) { clearAuth(); await router.replace({ name: 'auth', query: { redirect: '/settings' } }); return }
    pageError.value = error.status === 500 ? '密钥服务暂不可用' : (error.message || '加载失败')
  } finally { loading.value = false }
}

async function loadEmbeddingKeys() {
  eLoading.value = true
  ePageError.value = ''
  try { eKeys.value = await listEmbeddingKeys() } catch (error) {
    if (error.status === 401) { clearAuth(); await router.replace({ name: 'auth', query: { redirect: '/settings' } }); return }
    ePageError.value = error.status === 500 ? '密钥服务暂不可用' : (error.message || '加载失败')
  } finally { eLoading.value = false }
}

async function save() {
  formError.value = ''; feedback.value = ''
  const value = form.value
  if (!value.provider.trim()) { formError.value = '请填写服务商标识'; return }
  if (!/^https:\/\//i.test(value.base_url.trim())) { formError.value = 'Base URL 必须以 https:// 开头'; return }
  if (value.api_key.trim().length < 1) { formError.value = '请填写 API Key'; return }
  if (!value.model_name.trim()) { formError.value = '请填写模型名称'; return }
  saving.value = true
  try {
    const payload = { provider: value.provider.trim(), base_url: value.base_url.trim(), api_key: value.api_key.trim(), model_name: value.model_name.trim() }
    const kind = formKind.value
    if (editingId.value) {
      if (kind === 'embedding') await updateEmbeddingKey(editingId.value, payload)
      else await updateApiKey(editingId.value, payload)
    } else {
      if (kind === 'embedding') await createEmbeddingKey(payload)
      else await createApiKey(payload)
    }
    showForm.value = false
    feedback.value = editingId.value
      ? (kind === 'embedding' ? '向量模型已更新' : 'API Key 已更新')
      : (kind === 'embedding' ? '向量模型已添加' : 'API Key 已添加')
    if (kind === 'embedding') await loadEmbeddingKeys()
    else await loadKeys()
  } catch (error) { formError.value = error.status === 500 ? '密钥服务暂不可用' : (error.message || '保存失败') } finally { saving.value = false }
}

async function remove() {
  if (!confirmTarget.value) return
  deleting.value = true
  try {
    if (confirmKind.value === 'embedding') { await deleteEmbeddingKey(confirmTarget.value.id); feedback.value = '向量模型已移除'; await loadEmbeddingKeys() }
    else { await deleteApiKey(confirmTarget.value.id); feedback.value = 'API Key 已移除'; await loadKeys() }
    confirmTarget.value = null
  } catch (error) {
    if (confirmKind.value === 'embedding') ePageError.value = error.message || '移除失败'
    else pageError.value = error.message || '移除失败'
    confirmTarget.value = null
  } finally { deleting.value = false }
}

async function makeDefault(kind, item) {
  if (item.is_default || settingDefault.value) return
  settingDefault.value = true
  if (kind === 'embedding') ePageError.value = ''
  else pageError.value = ''
  try {
    if (kind === 'embedding') { await setDefaultEmbeddingKey(item.id); feedback.value = `${item.provider} 已设为默认向量模型`; await loadEmbeddingKeys() }
    else { await setDefaultApiKey(item.id); feedback.value = `${item.provider} 已设为默认模型`; await loadKeys() }
  } catch (error) {
    if (kind === 'embedding') ePageError.value = error.message || '设置默认向量模型失败'
    else pageError.value = error.message || '设置默认模型失败'
  } finally { settingDefault.value = false }
}

async function openDelete(kind, item) { confirmKind.value = kind; confirmTarget.value = item; await nextTick(); deleteDialog.value?.focus() }
onMounted(() => { loadKeys(); loadEmbeddingKeys() })
</script>

<template>
  <div class="min-h-full bg-zinc-50 dark:bg-zinc-950">
    <div class="mx-auto max-w-5xl px-5 pb-20 pt-9 sm:px-8 sm:pt-12">
      <div class="mb-9 border-b border-zinc-200 pb-6 dark:border-zinc-800"><h1 class="text-2xl font-semibold text-zinc-950 dark:text-white">设置</h1><p class="mt-2 text-sm text-zinc-500">管理模型连接。聊天用默认推理 Key；对话里的语义检索用默认向量模型 Key。两者相互独立。</p></div>
      <p v-if="pageError" class="mb-6 flex flex-wrap items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-400/10 dark:text-red-300" role="alert"><PhWarningCircle :size="18" />{{ pageError }}<button type="button" class="ml-auto inline-flex items-center gap-1 font-medium underline" @click="loadKeys"><PhArrowClockwise :size="16" />重试</button></p>
      <p v-if="ePageError" class="mb-6 flex flex-wrap items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-400/10 dark:text-red-300" role="alert"><PhWarningCircle :size="18" />{{ ePageError }}<button type="button" class="ml-auto inline-flex items-center gap-1 font-medium underline" @click="loadEmbeddingKeys"><PhArrowClockwise :size="16" />重试</button></p>
      <p v-if="feedback" class="mb-6 flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300" role="status"><PhCheckCircle :size="18" />{{ feedback }}</p>
      <section class="grid gap-5 border-t border-zinc-200 py-9 dark:border-zinc-800 sm:grid-cols-[180px_minmax(0,1fr)]">
        <div><h2 class="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100"><PhKey :size="18" />API Key</h2></div>
        <div class="min-w-0">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 pb-4 dark:border-zinc-800"><h3 class="text-base font-semibold text-zinc-900 dark:text-white">推理模型（聊天）</h3><button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-accent px-3 text-sm font-medium text-white transition-colors hover:bg-accent-strong" @click="resetForm('chat')"><PhPlus :size="17" weight="bold" />添加密钥</button></div>
          <div v-if="loading" class="py-9 text-sm text-zinc-500" role="status">加载中…</div>
          <div v-else-if="!pageError && keys.length === 0" class="border-b border-zinc-200 py-9 text-sm text-zinc-500 dark:border-zinc-800">尚未添加 API Key</div>
          <div v-for="item in keys" :key="item.id" class="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 py-4 dark:border-zinc-800">
            <div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="break-all text-sm font-semibold text-zinc-900 dark:text-white">{{ item.provider }}</span><span v-if="item.is_default" class="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-400/10 dark:text-amber-300"><PhStar :size="12" weight="fill" />默认</span><span v-if="item.status === 'invalid'" class="rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-400/10 dark:text-red-300">已失效</span></div><p class="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{{ item.base_url }}</p><p class="mt-1 font-mono text-xs text-zinc-500">{{ displayKey(item) }} · {{ item.model_name }}</p></div>
            <div class="flex items-center gap-2"><button v-if="!item.is_default" type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-zinc-300 px-2.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" :disabled="settingDefault" @click="makeDefault('chat', item)"><PhStar :size="16" />设默认</button><button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-zinc-300 px-2.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" :aria-label="`编辑 ${item.provider}`" @click="editKey('chat', item)"><PhPencilSimple :size="16" />编辑</button><button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-zinc-500 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-400/10 dark:hover:text-red-300" :title="`移除 ${item.provider}`" :aria-label="`移除 ${item.provider}`" @click="openDelete('chat', item)"><PhTrash :size="18" /></button></div>
          </div>
          <p class="mt-5 text-xs leading-5 text-zinc-500">API Key 只会安全保存，列表中仅显示末四位。Base URL 必须使用 HTTPS。</p>
        </div>
      </section>
      <section class="grid gap-5 border-t border-zinc-200 py-9 dark:border-zinc-800 sm:grid-cols-[180px_minmax(0,1fr)]">
        <div><h2 class="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100"><PhKey :size="18" />向量模型</h2></div>
        <div class="min-w-0">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 pb-4 dark:border-zinc-800"><h3 class="text-base font-semibold text-zinc-900 dark:text-white">语义检索（RAG）</h3><button type="button" class="inline-flex h-9 items-center gap-2 rounded-lg bg-accent px-3 text-sm font-medium text-white transition-colors hover:bg-accent-strong" @click="resetForm('embedding')"><PhPlus :size="17" weight="bold" />添加向量模型</button></div>
          <div v-if="eLoading" class="py-9 text-sm text-zinc-500" role="status">加载中…</div>
          <div v-else-if="!ePageError && eKeys.length === 0" class="border-b border-zinc-200 py-9 text-sm text-zinc-500 dark:border-zinc-800">尚未添加向量模型。对话中的语义检索需要它；未配置时检索功能不可用。</div>
          <div v-for="item in eKeys" :key="item.id" class="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-200 py-4 dark:border-zinc-800">
            <div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="break-all text-sm font-semibold text-zinc-900 dark:text-white">{{ item.provider }}</span><span v-if="item.is_default" class="inline-flex items-center gap-1 rounded bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-400/10 dark:text-amber-300"><PhStar :size="12" weight="fill" />默认</span><span v-if="item.status === 'invalid'" class="rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-400/10 dark:text-red-300">已失效</span></div><p class="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{{ item.base_url }}</p><p class="mt-1 font-mono text-xs text-zinc-500">{{ displayKey(item) }} · {{ item.model_name }}</p></div>
            <div class="flex items-center gap-2"><button v-if="!item.is_default" type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-zinc-300 px-2.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" :disabled="settingDefault" @click="makeDefault('embedding', item)"><PhStar :size="16" />设默认</button><button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-zinc-300 px-2.5 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" :aria-label="`编辑 ${item.provider}`" @click="editKey('embedding', item)"><PhPencilSimple :size="16" />编辑</button><button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-zinc-500 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-400/10 dark:hover:text-red-300" :title="`移除 ${item.provider}`" :aria-label="`移除 ${item.provider}`" @click="openDelete('embedding', item)"><PhTrash :size="18" /></button></div>
          </div>
          <p class="mt-5 text-xs leading-5 text-zinc-500">向量模型与推理模型相互独立，可配不同平台。更换向量模型后，旧向量全部作废，需重建全部向量数据。</p>
        </div>
      </section>
    </div>

    <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-4" role="dialog" aria-modal="true" @click.self="closeForm" @keydown.esc="closeForm"><div class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900"><div class="flex items-center justify-between"><h2 class="font-semibold">{{ editingId ? (formKind === 'embedding' ? '编辑向量模型' : '编辑 API Key') : (formKind === 'embedding' ? '添加向量模型' : '添加 API Key') }}</h2><button type="button" aria-label="关闭" title="关闭" @click="closeForm"><PhX :size="17" /></button></div><form class="mt-5 space-y-3" @submit.prevent="save"><label class="block text-sm font-medium">服务商标识<input v-model="form.provider" required maxlength="32" placeholder="例如 openai" class="mt-1 h-10 w-full rounded-lg border px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" /></label><label class="block text-sm font-medium">Base URL<input v-model="form.base_url" required type="url" placeholder="https://api.example.com/v1" class="mt-1 h-10 w-full rounded-lg border px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" /></label><label class="block text-sm font-medium">模型名称<input v-model="form.model_name" required maxlength="128" :placeholder="formKind === 'embedding' ? '例如 qwen3.7-text-embedding-flash' : '例如 gpt-4o-mini'" class="mt-1 h-10 w-full rounded-lg border px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" /></label><label class="block text-sm font-medium">API Key<span class="relative mt-1 block"><input ref="keyInput" v-model="form.api_key" :required="!editingId" :type="showKey ? 'text' : 'password'" maxlength="256" :placeholder="editingId ? '留空则保持原 Key' : '输入 API Key'" class="h-10 w-full rounded-lg border px-3 pr-10 text-sm dark:border-zinc-700 dark:bg-zinc-950" /><button type="button" class="absolute right-1 top-1 flex h-8 w-8 items-center justify-center text-zinc-500" :title="showKey ? '隐藏 API Key' : '显示 API Key'" :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'" @click="showKey = !showKey"><PhEyeSlash v-if="showKey" :size="17" /><PhEye v-else :size="17" /></button></span></label><p v-if="formError" class="text-sm text-red-600 dark:text-red-300" role="alert">{{ formError }}</p><div class="flex justify-end gap-2 pt-2"><button type="button" class="h-10 rounded-lg border px-4 text-sm" @click="closeForm">取消</button><button type="submit" :disabled="saving" class="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-white disabled:opacity-50"><PhCheckCircle :size="16" />{{ saving ? '保存中…' : '保存' }}</button></div></form></div></div>
    <div v-if="confirmTarget" class="fixed inset-0 z-[60] flex items-center justify-center bg-zinc-950/50 px-4" role="presentation" @click.self="confirmTarget = null"><div ref="deleteDialog" tabindex="-1" class="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-xl outline-none dark:border-zinc-800 dark:bg-zinc-900" role="dialog" aria-modal="true" aria-labelledby="delete-title"><h2 id="delete-title" class="font-semibold">移除{{ confirmKind === 'embedding' ? '向量模型' : 'API Key' }}？</h2><p class="mt-2 text-sm text-zinc-500">将移除 {{ confirmTarget.provider }} 的连接配置。</p><div class="mt-5 flex justify-end gap-2"><button type="button" class="h-10 rounded-lg border px-4 text-sm" @click="confirmTarget = null">取消</button><button type="button" class="h-10 rounded-lg bg-red-600 px-4 text-sm font-medium text-white disabled:opacity-50" :disabled="deleting" @click="remove">{{ deleting ? '移除中…' : '确认移除' }}</button></div></div></div>
  </div>
</template>
