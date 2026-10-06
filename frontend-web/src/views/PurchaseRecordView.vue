<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowRight, PhCheck, PhMagnifyingGlass, PhPlus, PhShoppingCart, PhTrash, PhX } from '@phosphor-icons/vue'
import {
  createPurchaseRecord,
  deletePurchaseRecord,
  listPurchaseRecords,
  previewPurchaseLink,
  updatePurchaseRecord,
} from '../utils/api'

const router = useRouter()
const records = ref([])
const selectedIds = ref([])
const loading = ref(true)
const busy = ref(false)
const editingId = ref(null)
const showForm = ref(false)
const toast = ref('')
const draftHint = ref('')
const form = reactive({ name: '', productUrl: '', platform: '', price: '', specsText: '', purchasedAt: '', note: '' })

const emptyForm = { ...form }
const priced = computed(() => records.value.filter((item) => item.price !== null && item.price !== undefined))
const totalSpent = computed(() => priced.value.reduce((sum, item) => sum + item.price, 0))

function notify(message) {
  toast.value = message
  window.setTimeout(() => { toast.value = '' }, 2600)
}

function specsFromText(text) {
  return Object.fromEntries(
    text
      .split('\n')
      .map((line) => line.split(/[:：]/))
      .filter((parts) => parts[0]?.trim() && parts[1]?.trim())
      .map((parts) => [parts[0].trim(), parts.slice(1).join(':').trim()]),
  )
}

function textFromSpecs(specs) {
  return Object.entries(specs || {}).map(([key, value]) => `${key}: ${value}`).join('\n')
}

// 表单里是浏览器本地墙上时钟，交给后端前换成真正的 UTC；
// 后端存 naive UTC、回给前端时补 Z，所以显示端再按本地时区渲染回去。
function wallClockToUtc(value) {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

function utcToLocalInput(value) {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
}

function formatDate(value) {
  if (!value) return '日期未记'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '日期未记' : parsed.toLocaleDateString('zh-CN')
}

function payloadFromForm() {
  return {
    name: form.name.trim(),
    product_url: form.productUrl.trim() || null,
    platform: form.platform.trim() || null,
    price: form.price === '' ? null : Number(form.price),
    specs: specsFromText(form.specsText),
    purchased_at: wallClockToUtc(form.purchasedAt),
    note: form.note.trim() || null,
  }
}

async function refresh() {
  loading.value = true
  try {
    records.value = await listPurchaseRecords()
    selectedIds.value = selectedIds.value.filter((id) => records.value.some((item) => item.id === id))
  } catch (error) {
    notify(error.message || '消费记录读取失败')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  draftHint.value = ''
  Object.assign(form, emptyForm)
  showForm.value = true
}

function startEdit(item) {
  editingId.value = item.id
  draftHint.value = ''
  Object.assign(form, {
    name: item.name,
    productUrl: item.product_url || '',
    platform: item.platform || '',
    price: item.price === null || item.price === undefined ? '' : String(item.price),
    specsText: textFromSpecs(item.specs),
    purchasedAt: utcToLocalInput(item.purchased_at),
    note: item.note || '',
  })
  showForm.value = true
}

// 只填表单，不落库：抓回来的内容是「待确认草稿」，按下保存才算用户确认过。
async function handlePreview() {
  if (!form.productUrl.trim()) {
    notify('先粘贴商品链接')
    return
  }
  busy.value = true
  try {
    const draft = await previewPurchaseLink(form.productUrl.trim())
    form.name = form.name.trim() || draft.name_suggestion
    form.platform = form.platform.trim() || draft.platform
    draftHint.value = `已从商品页面识别：${draft.name_suggestion}（来源：${draft.source}，确认后才保存）`
    if (form.name === draft.name_suggestion) notify('已填入识别结果，确认无误后保存')
  } catch (error) {
    draftHint.value = ''
    notify(error.message || '没能读到该商品页面，请直接手动填写')
  } finally {
    busy.value = false
  }
}

async function save() {
  if (!form.name.trim() || busy.value) return
  busy.value = true
  try {
    const payload = payloadFromForm()
    if (editingId.value) {
      await updatePurchaseRecord(editingId.value, payload)
      notify('已更新这条消费记录')
    } else {
      await createPurchaseRecord(payload)
      notify('已记录这条消费')
    }
    showForm.value = false
    editingId.value = null
    Object.assign(form, emptyForm)
    await refresh()
  } catch (error) {
    notify(error.message || '保存失败')
  } finally {
    busy.value = false
  }
}

async function remove(item) {
  try {
    await deletePurchaseRecord(item.id)
    notify('已删除')
    await refresh()
  } catch (error) {
    notify(error.message || '删除失败')
  }
}

function consultSelected() {
  if (!selectedIds.value.length) return
  router.push({ path: '/chat', query: { records: selectedIds.value.join(',') } })
}

onMounted(refresh)
</script>

<template>
  <div class="min-h-[calc(100dvh-4.5rem)] bg-zinc-50 dark:bg-zinc-950">
    <div class="mx-auto max-w-6xl px-5 pb-20 pt-9 sm:px-8 sm:pt-12">
      <div class="flex flex-wrap items-end justify-between gap-5 border-b border-zinc-200 pb-7 dark:border-zinc-800">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">Purchase history</p>
          <h1 class="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">消费记录</h1>
          <p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">自己记买过什么：商品名、链接、价格、平台、规格、购买时间。价格是当时记录值，不校验现价。</p>
        </div>
        <div class="flex items-end gap-4">
          <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-3.5 text-sm font-medium text-white" @click="resetForm"><PhPlus :size="17" />新增记录</button>
          <div class="text-right"><p class="text-xs text-zinc-500">已填价格</p><p class="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">{{ priced.length }} 条</p></div>
          <div class="text-right"><p class="text-xs text-zinc-500">合计</p><p class="mt-1 text-lg font-semibold text-zinc-900 dark:text-white">{{ totalSpent.toFixed(2) }} 元</p></div>
        </div>
      </div>

      <div class="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section>
          <div class="mb-3 flex items-center justify-between gap-3">
            <h2 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">我的消费记录 <span class="ml-1 text-zinc-400">{{ records.length }}</span></h2>
            <button type="button" :disabled="!selectedIds.length" class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-accent hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-blue-950/40" @click="consultSelected">带进咨询 <PhArrowRight :size="16" /></button>
          </div>

          <div v-if="loading" class="rounded-2xl border border-zinc-200 bg-white px-6 py-16 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900" role="status">正在读取…</div>
          <div v-else-if="!records.length" class="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-16 text-center dark:border-zinc-700 dark:bg-zinc-900">
            <PhShoppingCart :size="30" class="mx-auto text-zinc-400" />
            <p class="mt-3 text-sm font-medium text-zinc-700 dark:text-zinc-200">还没有消费记录</p>
            <p class="mt-1 text-sm text-zinc-500">点击“新增记录”后填写。</p>
          </div>
          <div v-else class="space-y-3">
            <article v-for="item in records" :key="item.id" class="flex gap-4 rounded-2xl border border-zinc-200 bg-white p-4 shadow-[0_8px_24px_-24px_rgba(15,23,42,.5)] dark:border-zinc-800 dark:bg-zinc-900">
              <input v-model="selectedIds" :value="item.id" type="checkbox" class="mt-1 h-4 w-4 accent-blue-600" :aria-label="`选择 ${item.name}`" />
              <div class="min-w-0 flex-1">
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="text-xs text-zinc-500">{{ item.platform || '平台未记' }} · {{ formatDate(item.purchased_at) }}</p>
                    <h3 class="mt-1 truncate font-semibold text-zinc-900 dark:text-white">{{ item.name }}</h3>
                    <a v-if="item.product_url" :href="item.product_url" target="_blank" rel="noopener noreferrer nofollow" class="mt-1 block truncate text-xs text-accent hover:underline">{{ item.product_url }}</a>
                  </div>
                  <div class="flex shrink-0 items-center gap-2">
                    <span class="text-sm font-semibold text-zinc-900 dark:text-white">{{ item.price === null || item.price === undefined ? '—' : `${item.price} 元` }}</span>
                    <button type="button" class="text-zinc-400 hover:text-accent" title="编辑" aria-label="编辑" @click="startEdit(item)"><PhCheck :size="17" /></button>
                    <button type="button" class="text-zinc-400 hover:text-red-600" title="删除" aria-label="删除" @click="remove(item)"><PhTrash :size="17" /></button>
                  </div>
                </div>
                <div v-if="Object.keys(item.specs || {}).length" class="mt-3 flex flex-wrap gap-1.5">
                  <span v-for="(value, key) in item.specs" :key="key" class="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{{ key }} {{ value }}</span>
                </div>
                <p v-if="item.note" class="mt-2 text-xs text-zinc-500 dark:text-zinc-400">备注：{{ item.note }}</p>
              </div>
            </article>
          </div>
        </section>

        <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-4" role="dialog" aria-modal="true" @click.self="showForm = false" @keydown.esc="showForm = false">
        <aside class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
          <div class="flex items-center justify-between gap-2">
            <h2 class="font-semibold text-zinc-900 dark:text-white">{{ editingId ? '编辑记录' : '新增记录' }}</h2>
            <button type="button" class="text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800" title="关闭" aria-label="关闭" @click="showForm = false"><PhX :size="17" /></button>
          </div>
          <p class="mt-2 text-sm leading-6 text-zinc-500">链接识别只生成草稿，保存前你可以改任何一项。</p>

          <form class="mt-5 space-y-4" @submit.prevent="save">
            <label class="block text-xs font-medium text-zinc-500">商品链接（选填）
              <div class="mt-1.5 flex gap-2">
                <input v-model="form.productUrl" type="url" maxlength="512" placeholder="https://item.jd.com/….html" class="block h-10 min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" />
                <button type="button" :disabled="busy" class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg border border-zinc-300 bg-white px-3 text-sm font-medium text-zinc-800 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800" @click="handlePreview"><PhMagnifyingGlass :size="16" />识别</button>
              </div>
            </label>
            <p v-if="draftHint" class="rounded-lg bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800 dark:bg-blue-950/40 dark:text-blue-200">{{ draftHint }}</p>

            <label class="block text-xs font-medium text-zinc-500">商品名<input v-model="form.name" maxlength="256" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label>

            <div class="grid grid-cols-2 gap-3">
              <label class="block text-xs font-medium text-zinc-500">平台<input v-model="form.platform" maxlength="64" placeholder="京东 / 淘宝…" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label>
              <label class="block text-xs font-medium text-zinc-500">价格（元）<input v-model="form.price" type="number" min="0" step="0.01" inputmode="decimal" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label>
            </div>

            <label class="block text-xs font-medium text-zinc-500">购买时间<input v-model="form.purchasedAt" type="datetime-local" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label>

            <label class="block text-xs font-medium text-zinc-500">规格键值对（每行一条）<textarea v-model="form.specsText" rows="4" placeholder="颜色: 黑色&#10;容量: 256G" class="mt-1.5 block w-full resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm leading-6 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label>

            <label class="block text-xs font-medium text-zinc-500">备注<textarea v-model="form.note" rows="2" maxlength="512" class="mt-1.5 block w-full resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm leading-6 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label>

            <button type="submit" :disabled="busy || !form.name.trim()" class="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50">
              <PhPlus v-if="!editingId" :size="16" weight="bold" /><PhCheck v-else :size="16" />{{ editingId ? '保存修改' : '添加消费记录' }}
            </button>
          </form>
        </aside></div>
      </div>

      <p v-if="toast" class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white shadow-xl" role="status">{{ toast }}</p>
    </div>
  </div>
</template>
