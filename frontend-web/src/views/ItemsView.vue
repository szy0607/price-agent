<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { PhArchive, PhCheck, PhPlus, PhX } from '@phosphor-icons/vue'
import { createRecord, loadRecords, saveRecords, subscribeRecords } from '../utils/parameterRecords'

const records = ref([])
const showForm = ref(false)
const form = reactive({ name: '', brand: '', model: '', category: '', note: '' })
const items = computed(() => records.value.filter((record) => record.scope === 'items'))
const recentItems = computed(() => [...items.value].sort((a, b) => new Date(b.purchasedAt || b.updatedAt || 0) - new Date(a.purchasedAt || a.updatedAt || 0)).slice(0, 5))
const recentActive = ref(0)
const selectedItem = ref(null)
function cardStyle(index) {
  const offset = index - recentActive.value
  return { '--card-offset': offset, '--card-depth': Math.max(0, 5 - Math.abs(offset)), '--card-tilt': `${offset * -7}deg`, zIndex: 10 - Math.abs(offset) }
}
function closeItemDetail() { selectedItem.value = null }
function refresh() { records.value = loadRecords() }
function reset() { Object.assign(form, { name: '', brand: '', model: '', category: '', note: '' }); showForm.value = false }
function addItem() {
  if (!form.name.trim()) return
  const next = createRecord({ ...form, specs: form.note ? { 备注: form.note } : {}, source: '手动建档' }, 'items')
  saveRecords([...records.value, next])
  reset()
}
onMounted(() => { refresh(); window._itemsRecordsCleanup = subscribeRecords(refresh) })
onBeforeUnmount(() => { window._itemsRecordsCleanup?.(); delete window._itemsRecordsCleanup })
</script>

<template>
  <div class="min-h-[calc(100dvh-4.5rem)] bg-zinc-50 dark:bg-zinc-950"><div class="mx-auto max-w-7xl px-5 pb-20 pt-9 sm:px-8 sm:pt-12"><div class="flex flex-wrap items-end justify-between gap-5 border-b border-zinc-200 pb-7 dark:border-zinc-800"><div><p class="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">Personal archive</p><h1 class="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">物品库</h1><p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">已购买和正在使用的物品参数档案，可随时补充备注。</p></div><button type="button" class="inline-flex h-10 items-center gap-2 rounded-xl bg-accent px-3.5 text-sm font-medium text-white shadow-sm hover:bg-accent-strong" @click="showForm = true"><PhPlus :size="17" weight="bold" />直接建档</button></div>
    <section v-if="recentItems.length" class="recent-items-showcase" aria-labelledby="recent-items-title"><div class="recent-items-copy"><p id="recent-items-title" class="recent-items-label">最近买过</p></div><div class="recent-items-stage"><button v-for="(item, index) in recentItems" :key="item.id" type="button" class="recent-item-card" :class="{ active: index === recentActive }" :style="cardStyle(index)" :aria-label="`查看 ${item.name}`" @mouseenter="recentActive = index" @focus="recentActive = index" @click="recentActive = index; selectedItem = item"><span class="recent-item-card__shine"></span><img :src="item.image" :alt="item.name" /><div><small>{{ item.category }} · {{ item.brand }}</small><strong>{{ item.name }}</strong><em>{{ item.purchasedAt || '最近更新' }}</em></div></button></div></section>
    <div v-if="showForm" class="mt-6 rounded-2xl border border-blue-200 bg-blue-50/60 p-5 dark:border-blue-900/70 dark:bg-blue-950/25"><div class="flex items-center justify-between"><h2 class="font-semibold text-zinc-900 dark:text-white">为已有物品建档</h2><button type="button" title="关闭" aria-label="关闭" class="text-zinc-500" @click="reset"><PhX :size="18" /></button></div><form class="mt-4 grid gap-3 sm:grid-cols-2" @submit.prevent="addItem"><input v-model="form.name" required placeholder="物品名称 *" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><input v-model="form.brand" placeholder="品牌" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><input v-model="form.model" placeholder="型号" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><input v-model="form.category" placeholder="品类" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><input v-model="form.note" placeholder="备注（可选）" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm sm:col-span-2 dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><button type="submit" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white sm:col-span-2"><PhCheck :size="16" />保存物品档案</button></form></div>
    <div v-if="!items.length" class="mt-8 rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-16 text-center dark:border-zinc-700 dark:bg-zinc-900"><PhArchive :size="30" class="mx-auto text-zinc-400" /><p class="mt-3 text-sm font-medium text-zinc-700 dark:text-zinc-200">还没有物品档案</p></div><div v-else class="mt-8 grid gap-4 md:grid-cols-2"><article v-for="item in items" :key="item.id" class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"><div class="flex gap-4"><img :src="item.image" alt="" class="h-20 w-20 rounded-xl object-cover" /><div class="min-w-0"><p class="text-xs text-zinc-500">{{ item.category }} · {{ item.brand }}</p><h2 class="mt-1 truncate font-semibold text-zinc-900 dark:text-white">{{ item.name }}</h2><p class="mt-1 text-xs text-zinc-500">{{ item.model }}</p></div></div><div class="mt-4 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400"><span>建档来源：{{ item.source }}</span><span v-if="item.purchasedAt" class="ml-4">购买日期：{{ item.purchasedAt }}</span></div><div class="mt-3 flex flex-wrap gap-1.5"><span v-for="(value, key) in item.specs" :key="key" class="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{{ key }} {{ value }}</span></div></article></div></div></div>
    <div v-if="selectedItem" class="item-detail-modal" role="dialog" aria-modal="true" :aria-label="selectedItem.name" @click.self="closeItemDetail" @keydown.esc="closeItemDetail"><div class="item-detail-dialog"><button type="button" class="item-detail-close" aria-label="关闭参数详情" title="关闭" @click="closeItemDetail"><PhX :size="19" /></button><div class="item-detail-head"><img :src="selectedItem.image" :alt="selectedItem.name" /><div><p>{{ selectedItem.category }} · {{ selectedItem.brand }}</p><h2>{{ selectedItem.name }}</h2><span>{{ selectedItem.model }}</span></div></div><div class="item-detail-meta"><span>建档来源：{{ selectedItem.source }}</span><span v-if="selectedItem.purchasedAt">购买日期：{{ selectedItem.purchasedAt }}</span></div><div class="item-detail-specs"><div v-for="(value, key) in selectedItem.specs" :key="key"><small>{{ key }}</small><strong>{{ value }}</strong></div></div></div></div>
</template>
