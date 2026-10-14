<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { PhArchive, PhArrowLeft, PhArrowRight, PhCheck, PhPlus, PhTrash, PhX } from '@phosphor-icons/vue'
import GroupPickerModal from '../components/GroupPickerModal.vue'
import { createOwnedItem, deleteOwnedItem, listLatestOwnedItems, listOwnedItems, resolveImageUrl, updateOwnedItem, uploadImage } from '../utils/api'

const items = ref([])
const recentItems = ref([])
const loading = ref(true)
const recentLoading = ref(true)
const saving = ref(false)
const editingId = ref(null)
const showForm = ref(false)
const selectedItem = ref(null)
const recentActive = ref(0)
const toast = ref('')
const uploading = ref(false)
const fileInput = ref(null)
const nameInput = ref(null)
const groupPickerItem = ref(null)
const form = reactive({ name: '', category: '', price: '', specsList: [], image: '', note: '', platform: '', purchasedAt: '' })
const placeholderImage = `${import.meta.env.BASE_URL}images/placeholder-item.png`

const recentCountLabel = computed(() => recentItems.value.length ? `最近购买 · ${recentItems.value.length} 件` : '最近购买')
function recentDate(item) {
  const raw = item.purchased_at || item.create_time
  if (!raw) return '最近更新'
  const date = new Date(raw)
  return Number.isNaN(date.getTime()) ? '最近更新' : date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
}
function notify(message) { toast.value = message; window.setTimeout(() => { toast.value = '' }, 2600) }
function objectToSpecList(specs) { return Object.entries(specs || {}).map(([k, v]) => ({ key: k, value: String(v ?? '') })) }
function specListToObject(list) { const out = {}; for (const row of list || []) { const k = (row.key || '').trim(); if (k) out[k] = (row.value || '').trim() } return out }
function imageFallback(event) { event.target.src = placeholderImage }
// 图片地址放宽：http(s) 外链，或以 / 开头的本地上传路径（/uploads/xxx.jpg）
function validImageUrl(value) { if (!value) return true; return value.startsWith('/') || /^https?:\/\//.test(value) }
async function uploadImageFile(event) {
  const file = event.target.files?.[0]
  event.target.value = '' // 清空，允许再次选同一个文件
  if (!file || uploading.value) return
  uploading.value = true
  try { form.image = await uploadImage(file); notify('图片已上传') }
  catch (error) { notify(error.message || '上传失败') }
  finally { uploading.value = false }
}
function carouselOffset(index) { const total = recentItems.value.length; if (!total) return 0; let offset = (index - recentActive.value + total) % total; if (offset > total / 2) offset -= total; return offset }
function carouselStyle(index) { const offset = carouselOffset(index); const distance = Math.abs(offset); return { '--carousel-offset': offset, '--carousel-depth': Math.max(0, 3 - distance), '--carousel-scale': distance === 0 ? 1 : distance === 1 ? 0.82 : 0.68, '--carousel-opacity': distance > 2 ? 0 : distance === 2 ? 0.58 : 0.86, zIndex: 10 - distance } }
function moveRecent(direction) { const total = recentItems.value.length; if (total) recentActive.value = (recentActive.value + direction + total) % total }
function selectRecent(index) { if (index !== recentActive.value) recentActive.value = index; else selectedItem.value = recentItems.value[index] }
function closeItemDetail() { selectedItem.value = null }
// 打开表单弹窗时把焦点送进第一个输入框：一是省一次点击，二是 Esc 关闭挂在遮罩上，
// 焦点若还在弹窗外（刚点完卡片上的「编辑」）按 Esc 事件收不到。
async function openForm() { showForm.value = true; await nextTick(); nameInput.value?.focus() }
async function resetForm() { editingId.value = null; Object.assign(form, { name: '', category: '', price: '', specsList: [], image: '', note: '', platform: '', purchasedAt: '' }); await openForm() }
function closeForm() { if (!saving.value) showForm.value = false }
async function edit(item) { editingId.value = item.id; Object.assign(form, { name: item.name, category: item.category || '', price: item.price ?? '', specsList: objectToSpecList(item.specs), image: item.image || '', note: item.note || '', platform: item.platform || '', purchasedAt: item.purchased_at ? String(item.purchased_at).slice(0, 10) : '' }); await openForm() }
async function refresh() {
  loading.value = true; recentLoading.value = true
  try {
    const allItems = await listOwnedItems(); items.value = allItems
    try { recentItems.value = (await listLatestOwnedItems()).slice(0, 5) } catch { recentItems.value = allItems.slice(0, 5) }
    recentActive.value = Math.min(recentActive.value, Math.max(0, recentItems.value.length - 1))
  } catch (error) { notify(error.message || '物品库读取失败') } finally { loading.value = false; recentLoading.value = false }
}
async function save() {
  if (!form.name.trim() || saving.value) return
  if (form.image.trim() && !validImageUrl(form.image.trim())) { notify('图片地址无效：http/https 链接或本地上传路径'); return }
  saving.value = true
  const payload = { name: form.name.trim(), category: form.category.trim() || '其他', price: form.price === '' ? null : Number(form.price), specs: specListToObject(form.specsList), image: form.image.trim() || null, note: form.note.trim() || null, platform: form.platform.trim() || null, purchased_at: form.purchasedAt || null }
  try { if (editingId.value) await updateOwnedItem(editingId.value, payload); else await createOwnedItem(payload); showForm.value = false; editingId.value = null; await refresh(); notify('已保存') } catch (error) { notify(error.message || '保存失败') } finally { saving.value = false }
}
async function remove(item) { try { await deleteOwnedItem(item.id); await refresh(); notify('已删除') } catch (error) { notify(error.message || '删除失败') } }
function openGroupPicker(item) { groupPickerItem.value = item }
function onAddedToGroup(name) { groupPickerItem.value = null; notify(`已加入分组「${name}」`) }
onMounted(refresh)
</script>

<template>
  <div class="min-h-[calc(100dvh-4.5rem)] bg-zinc-50 dark:bg-zinc-950"><div class="mx-auto max-w-none px-5 pb-20 pt-9 sm:px-8 sm:pt-12">
    <div class="flex flex-wrap items-end justify-between gap-5 border-b border-zinc-200 pb-7 dark:border-zinc-800"><div><p class="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">Personal archive</p><h1 class="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-white">物品库</h1><p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">已购买和正在使用的物品参数档案，可随时补充备注。</p></div><button type="button" class="inline-flex h-10 items-center gap-2 rounded-xl bg-accent px-3.5 text-sm font-medium text-white shadow-sm hover:bg-accent-strong" @click="resetForm"><PhPlus :size="17" weight="bold" />直接建档</button></div>
    <section class="recent-items-showcase" aria-labelledby="recent-items-title"><div class="recent-items-copy"><p id="recent-items-title" class="recent-items-label">{{ recentCountLabel }}</p><p class="mt-2 text-sm text-zinc-500">把最近买过的物品放在手边，点击中间卡片查看完整参数。</p></div><div v-if="recentLoading" class="recent-items-loading" aria-label="正在读取最近购买"><span v-for="n in 3" :key="n"></span></div><div v-else-if="recentItems.length" class="recent-items-carousel"><button type="button" class="recent-items-arrow" aria-label="上一件最近购买" @click="moveRecent(-1)"><PhArrowLeft :size="19" weight="bold" /></button><div class="recent-items-stage"><button v-for="(item, index) in recentItems" :key="item.id" type="button" class="recent-item-card" :style="carouselStyle(index)" :aria-label="`${index === recentActive ? '查看' : '切换到'} ${item.name}`" @click="selectRecent(index)"><img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" @error="imageFallback" /><div><small>{{ item.category }}{{ item.platform ? ` · ${item.platform}` : '' }}</small><strong>{{ item.name }}</strong><em>{{ recentDate(item) }}</em></div></button></div><button type="button" class="recent-items-arrow" aria-label="下一件最近购买" @click="moveRecent(1)"><PhArrowRight :size="19" weight="bold" /></button></div><div v-else class="recent-items-empty"><PhArchive :size="25" /><span>还没有购买记录，先完成一件物品建档吧。</span></div></section>
    <section class="mt-8" aria-label="全部物品"><div v-if="loading" class="rounded-2xl border bg-white px-6 py-16 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">正在读取…</div><div v-else-if="!items.length" class="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-16 text-center dark:border-zinc-700 dark:bg-zinc-900"><PhArchive :size="30" class="mx-auto text-zinc-400" /><p class="mt-3 text-sm font-medium text-zinc-700 dark:text-zinc-200">还没有物品档案</p></div><div v-else class="grid gap-4 md:grid-cols-3 xl:grid-cols-4"><article v-for="item in items" :key="item.id" class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"><div class="flex gap-4"><img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-20 w-20 rounded-xl object-cover" @error="imageFallback" /><div class="min-w-0"><p class="text-xs text-zinc-500">{{ item.category }}{{ item.platform ? ` · ${item.platform}` : '' }}</p><h2 class="mt-1 truncate font-semibold text-zinc-900 dark:text-white">{{ item.name }}</h2><p v-if="item.purchased_at" class="mt-1 text-xs text-zinc-500">购买于 {{ String(item.purchased_at).slice(0, 10) }}</p></div></div><div v-if="Object.keys(item.specs || {}).length" class="mt-4 flex flex-wrap gap-1.5 border-t border-zinc-100 pt-3 dark:border-zinc-800"><span v-for="(value, key) in item.specs" :key="key" class="rounded-md px-2 py-1 text-xs" :class="key.endsWith('(AI)') ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300' : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'">{{ key }} {{ value }}<small v-if="key.endsWith('(AI)')" class="ml-1">网络</small></span></div><p v-if="item.note" class="mt-2 text-xs text-zinc-500">{{ item.note }}</p><div class="mt-3 flex gap-3 text-xs"><button type="button" class="text-accent" @click="edit(item)">编辑</button><button type="button" class="text-accent" @click="openGroupPicker(item)">加入分组</button><button type="button" class="text-red-600" @click="remove(item)">删除</button></div></article></div></section>
  </div>
    <!-- 建档/编辑弹窗：点卡片上的「编辑」就地改，不用滚回页首找表单。
         遮罩与卡片样式沿用 CartView / PurchaseRecordView 的同款 Tailwind 写法（这两页的表单本来就是弹窗），
         弹窗改成 flex 列 + 表单自身滚动：标题和关闭按钮因此钉在顶部，不会跟着内容滚走。 -->
    <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-4" role="dialog" aria-modal="true" :aria-label="editingId ? '编辑物品' : '为已有物品建档'" @click.self="closeForm" @keydown.esc="closeForm">
      <div class="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
        <div class="flex items-center justify-between"><h2 class="font-semibold text-zinc-900 dark:text-white">{{ editingId ? '编辑物品' : '为已有物品建档' }}</h2><button type="button" aria-label="关闭" title="关闭" class="text-zinc-500" @click="closeForm"><PhX :size="17" /></button></div>
        <form class="mt-4 grid gap-3 overflow-y-auto pr-1 sm:grid-cols-2" @submit.prevent="save">
          <input ref="nameInput" v-model="form.name" required maxlength="256" placeholder="物品名称 *" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" />
          <input v-model="form.category" maxlength="64" placeholder="分类" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" />
          <div class="grid grid-cols-2 gap-3"><input v-model="form.price" type="number" min="0" step="0.01" placeholder="价格" class="h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><input v-model="form.platform" maxlength="64" placeholder="平台" class="h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /></div>
          <input v-model="form.purchasedAt" type="date" class="h-10 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" />
          <div class="space-y-2 sm:col-span-2">
            <div v-for="(row, idx) in form.specsList" :key="idx" class="flex items-center gap-2"><input v-model="row.key" placeholder="参数名（如：颜色）" class="h-10 min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><input v-model="row.value" placeholder="参数值（如：黑色）" class="h-10 min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white" /><button type="button" :aria-label="`删除参数 ${idx + 1}`" class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-zinc-200 text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:border-zinc-700 dark:hover:bg-red-950/40" @click="form.specsList.splice(idx, 1)"><PhTrash :size="15" /></button></div>
            <button type="button" class="inline-flex h-9 items-center gap-1 rounded-lg border border-dashed border-zinc-300 px-3 text-sm text-zinc-500 hover:border-blue-400 hover:text-blue-600 dark:border-zinc-700 dark:text-zinc-400" @click="form.specsList.push({ key: '', value: '' })">＋ 添加参数</button>
          </div>
          <div class="flex items-center gap-3 rounded-lg border border-dashed border-zinc-300 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-900 sm:col-span-2"><img :src="resolveImageUrl(form.image) || placeholderImage" alt="图片预览" class="h-14 w-14 rounded-md object-cover" @error="imageFallback" /><div class="min-w-0 flex-1"><p class="text-sm text-zinc-700 dark:text-zinc-200">{{ form.image ? '当前图片' : '暂无图片' }}</p><p class="mt-0.5 text-xs text-zinc-400">{{ form.image ? '可点击右侧按钮更换' : '可点击右侧按钮上传' }}</p></div><button v-if="form.image" type="button" class="inline-flex h-10 shrink-0 items-center rounded-lg border border-zinc-300 px-3 text-sm text-zinc-500 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800" @click="form.image = ''">移除</button><button type="button" :disabled="uploading" class="inline-flex h-10 shrink-0 items-center rounded-lg border border-zinc-300 px-3 text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" @click="fileInput?.click()">{{ uploading ? '上传中…' : '上传图片' }}</button><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="uploadImageFile" /></div>
          <textarea v-model="form.note" rows="2" maxlength="512" placeholder="备注" class="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white sm:col-span-2" />
          <button type="submit" :disabled="saving" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white disabled:opacity-50 sm:col-span-2"><PhCheck :size="16" />{{ saving ? '保存中…' : '保存' }}</button>
        </form>
      </div>
    </div>
    <div v-if="selectedItem" class="item-detail-modal" role="dialog" aria-modal="true" :aria-label="selectedItem.name" @click.self="closeItemDetail" @keydown.esc="closeItemDetail"><div class="item-detail-dialog"><button type="button" class="item-detail-close" aria-label="关闭参数详情" title="关闭" @click="closeItemDetail"><PhX :size="19" /></button><div class="item-detail-head"><img :src="resolveImageUrl(selectedItem.image) || placeholderImage" :alt="selectedItem.name" @error="imageFallback" /><div><p>{{ selectedItem.category }}{{ selectedItem.platform ? ` · ${selectedItem.platform}` : '' }}</p><h2>{{ selectedItem.name }}</h2><span>{{ selectedItem.price == null ? '价格未记录' : `购买价 ¥${selectedItem.price}` }}</span></div></div><div class="item-detail-meta"><span v-if="selectedItem.purchased_at">购买日期：{{ String(selectedItem.purchased_at).slice(0, 10) }}</span><span v-if="selectedItem.note">备注：{{ selectedItem.note }}</span></div><div v-if="Object.keys(selectedItem.specs || {}).length" class="item-detail-specs"><div v-for="(value, key) in selectedItem.specs" :key="key"><small>{{ key.endsWith('(AI)') ? '网络参考 · ' : '' }}{{ key.replace(/\(AI\)$/, '') }}</small><strong>{{ value }}</strong></div></div></div></div><p v-if="toast" class="fixed bottom-6 left-1/2 z-[90] -translate-x-1/2 rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white" role="status">{{ toast }}</p></div>
</template>
