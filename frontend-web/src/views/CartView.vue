<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowRight, PhCheck, PhFileArrowUp, PhMagnifyingGlass, PhPlus, PhShoppingCart, PhTrash, PhX } from '@phosphor-icons/vue'
import { createRecord, loadRecords, saveRecords, subscribeRecords } from '../utils/parameterRecords'

const router = useRouter()
const records = ref([])
const selectedIds = ref([])
const draft = ref(null)
const fileInput = ref(null)
const isExtracting = ref(false)
const toast = ref('')
const draftForm = reactive({ name: '', brand: '', model: '', category: '', specsText: '' })

const cartRecords = computed(() => records.value.filter((item) => item.scope === 'cart'))

function refresh() {
  records.value = loadRecords()
  selectedIds.value = selectedIds.value.filter((id) => cartRecords.value.some((item) => item.id === id))
}

function notify(message) {
  toast.value = message
  window.setTimeout(() => { toast.value = '' }, 2600)
}

function startDraft(input) {
  draft.value = input
  draftForm.name = input.name
  draftForm.brand = input.brand
  draftForm.model = input.model
  draftForm.category = input.category
  draftForm.specsText = Object.entries(input.specs).map(([key, value]) => `${key}: ${value}`).join('\n')
}

function simulateExtraction(fileName = '') {
  isExtracting.value = true
  window.setTimeout(() => {
    isExtracting.value = false
    startDraft({
      name: fileName.includes('杯') ? 'SM-SA 系列不锈钢保温杯' : 'WH-1000XM5 无线降噪耳机',
      brand: fileName.includes('杯') ? 'ZOJIRUSHI 象印' : 'Sony 索尼',
      model: fileName.includes('杯') ? 'SM-SA48-BM' : 'WH-1000XM5',
      category: fileName.includes('杯') ? '家居日用' : '数码影音',
      source: fileName ? '图片识别 · 待确认' : '演示识别 · 待确认',
      specs: fileName.includes('杯')
        ? { 容量: '480ml', 内胆: '304 不锈钢（双层真空）', 保温: '6h ≥ 75℃' }
        : { 颜色: '黑色', 蓝牙: '5.2 / LDAC', 续航: '30h（开降噪）' },
    })
  }, 650)
}

function handleFile(event) {
  const file = event.target.files?.[0]
  if (file) simulateExtraction(file.name)
  event.target.value = ''
}

function confirmDraft() {
  if (!draftForm.name.trim()) return
  const specs = Object.fromEntries(draftForm.specsText.split('\n').map((line) => line.split(':')).filter(([key, value]) => key?.trim() && value?.trim()).map(([key, value]) => [key.trim(), value.trim()]))
  const next = [...records.value.filter((item) => item.scope !== 'cart'), ...records.value.filter((item) => item.scope === 'cart'), createRecord({ ...draftForm, specs, image: draft.value?.image })]
  saveRecords(next)
  draft.value = null
  notify('参数已确认，商品已加入购物车')
}

function removeRecord(id) {
  saveRecords(records.value.filter((item) => item.id !== id))
  notify('已从购物车移除')
}

function markPurchased(item) {
  saveRecords(records.value.map((record) => record.id === item.id ? { ...record, scope: 'items', purchasedAt: new Date().toISOString().slice(0, 10), updatedAt: new Date().toISOString() } : record))
  selectedIds.value = selectedIds.value.filter((id) => id !== item.id)
  notify('已移入物品库')
}

function consultSelected() {
  if (!selectedIds.value.length) return
  router.push({ path: '/chat', query: { items: selectedIds.value.join(',') } })
}

onMounted(() => { refresh(); window._recordsCleanup = subscribeRecords(refresh) })
onBeforeUnmount(() => { window._recordsCleanup?.(); delete window._recordsCleanup })
</script>

<template>
  <div class="min-h-[calc(100dvh-4.5rem)] bg-zinc-50 dark:bg-zinc-950">
    <div class="mx-auto max-w-6xl px-5 pb-20 pt-9 sm:px-8 sm:pt-12">
      <div class="flex flex-wrap items-end justify-between gap-5 border-b border-zinc-200 pb-7 dark:border-zinc-800">
        <div><p class="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">Parameter workspace</p><h1 class="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">购物车</h1><p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">只保存已确认的商品参数，不结算、不记录价格。</p></div>
        <div class="flex items-center gap-2"><input ref="fileInput" type="file" accept="image/*,.json,.csv" class="hidden" @change="handleFile" /><button type="button" class="inline-flex h-10 items-center gap-2 rounded-xl border border-zinc-300 bg-white px-3.5 text-sm font-medium text-zinc-800 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800" @click="fileInput?.click()"><PhFileArrowUp :size="17" />上传识别</button><button type="button" class="inline-flex h-10 items-center gap-2 rounded-xl bg-accent px-3.5 text-sm font-medium text-white shadow-sm hover:bg-accent-strong" @click="simulateExtraction()"><PhPlus :size="17" weight="bold" />演示添加</button></div>
      </div>

      <div class="mt-7 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section>
          <div class="mb-3 flex items-center justify-between gap-3"><h2 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">待咨询商品 <span class="ml-1 text-zinc-400">{{ cartRecords.length }}</span></h2><button type="button" :disabled="!selectedIds.length" class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-accent hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-blue-950/40" @click="consultSelected">带入咨询 <PhArrowRight :size="16" /></button></div>
          <div v-if="!cartRecords.length" class="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-16 text-center dark:border-zinc-700 dark:bg-zinc-900"><PhShoppingCart :size="30" class="mx-auto text-zinc-400" /><p class="mt-3 text-sm font-medium text-zinc-700 dark:text-zinc-200">购物车还是空的</p><p class="mt-1 text-sm text-zinc-500">上传商品图片或使用演示添加，开始建立参数档案。</p></div>
          <div v-else class="space-y-3"><article v-for="item in cartRecords" :key="item.id" class="flex gap-4 rounded-2xl border border-zinc-200 bg-white p-4 shadow-[0_8px_24px_-24px_rgba(15,23,42,.5)] dark:border-zinc-800 dark:bg-zinc-900"><input v-model="selectedIds" :value="item.id" type="checkbox" class="mt-1 h-4 w-4 accent-blue-600" :aria-label="`选择 ${item.name}`" /><img :src="item.image" alt="" class="h-20 w-20 rounded-xl bg-zinc-100 object-cover dark:bg-zinc-800" /><div class="min-w-0 flex-1"><div class="flex items-start justify-between gap-3"><div><p class="text-xs text-zinc-500">{{ item.category }} · {{ item.brand }}</p><h3 class="mt-1 truncate font-semibold text-zinc-900 dark:text-white">{{ item.name }}</h3><p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{{ item.model }} · {{ item.source }}</p></div><button type="button" class="text-zinc-400 hover:text-red-600" title="移除" aria-label="移除" @click="removeRecord(item.id)"><PhTrash :size="17" /></button></div><div class="mt-3 flex flex-wrap gap-1.5"><span v-for="(value, key) in item.specs" :key="key" class="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{{ key }} {{ value }}</span></div><button type="button" class="mt-3 text-xs font-medium text-accent hover:underline" @click="markPurchased(item)">标记已购买，移入物品库</button></div></article></div>
        </section>

        <aside class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"><div class="flex items-center gap-2"><PhMagnifyingGlass :size="18" class="text-accent" /><h2 class="font-semibold text-zinc-900 dark:text-white">参数识别草稿</h2></div><p class="mt-2 text-sm leading-6 text-zinc-500">识别和网络补全只生成草稿，确认前不会写入你的档案。</p><div v-if="isExtracting" class="mt-6 rounded-xl bg-zinc-50 p-4 text-sm text-zinc-500 dark:bg-zinc-800/70" role="status">正在提取商品参数…</div><form v-else-if="draft" class="mt-5 space-y-4" @submit.prevent="confirmDraft"><label class="block text-xs font-medium text-zinc-500">商品名称<input v-model="draftForm.name" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label><div class="grid grid-cols-2 gap-3"><label class="block text-xs font-medium text-zinc-500">品牌<input v-model="draftForm.brand" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label><label class="block text-xs font-medium text-zinc-500">型号<input v-model="draftForm.model" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label></div><label class="block text-xs font-medium text-zinc-500">品类<input v-model="draftForm.category" class="mt-1.5 block h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label><label class="block text-xs font-medium text-zinc-500">参数键值对<textarea v-model="draftForm.specsText" rows="5" class="mt-1.5 block w-full resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm leading-6 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" /></label><p class="text-xs leading-5 text-amber-700 dark:text-amber-300">身份键：{{ draftForm.brand }} + {{ draftForm.model }} + {{ draftForm.name }}</p><div class="flex gap-2"><button type="submit" class="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white hover:bg-accent-strong"><PhCheck :size="16" />确认加入购物车</button><button type="button" class="inline-flex h-10 w-10 items-center justify-center rounded-lg text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800" title="关闭草稿" aria-label="关闭草稿" @click="draft = null"><PhX :size="17" /></button></div></form><div v-else class="mt-6 rounded-xl border border-dashed border-zinc-300 px-4 py-8 text-center text-sm text-zinc-500 dark:border-zinc-700">点击“演示添加”或上传图片，查看 A2′ 商品情报草稿。</div></aside>
      </div>
      <p v-if="toast" class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white shadow-xl" role="status">{{ toast }}</p>
    </div>
  </div>
</template>
