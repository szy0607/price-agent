<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { PhCheck, PhMagicWand, PhPlus, PhShoppingCart, PhTrash, PhX } from '@phosphor-icons/vue'
import { completeCartItemDraft, createCartItem, deleteCartItem, listCartItems, resolveImageUrl, transferCartItem, updateCartItem, uploadImage } from '../utils/api'
const items = ref([]); const loading = ref(true); const saving = ref(false); const aiCompleting = ref(false); const editingId = ref(null); const showForm = ref(false); const toast = ref(''); const aiMessage = ref(''); const aiSources = ref([]); const uploading = ref(false); const fileInput = ref(null)
const form = reactive({ name: '', category: '', price: '', specsText: '', image: '', note: '' })
const placeholderImage = `${import.meta.env.BASE_URL}images/placeholder-item.png`
const page = ref(1); const pageSize = 10
const pageCount = computed(() => Math.max(1, Math.ceil(items.value.length / pageSize)))
const visibleItems = computed(() => items.value.slice((page.value - 1) * pageSize, page.value * pageSize))
function goPage(next) { page.value = Math.min(pageCount.value, Math.max(1, next)) }
function notify(message) { toast.value = message; window.setTimeout(() => { toast.value = '' }, 2600) }
function specsFromText(text) { return Object.fromEntries(text.split('\n').map((line) => line.split(/[:：]/)).filter(([k, v]) => k?.trim() && v?.trim()).map(([k, ...v]) => [k.trim(), v.join(':').trim()])) }
function specsText(specs) { return Object.entries(specs || {}).map(([k, v]) => `${k}: ${v}`).join('\n') }
// 图片地址放宽：http(s) 外链，或以 / 开头的本地上传路径（/uploads/xxx.jpg）
function validImageUrl(value) { if (!value) return true; return value.startsWith('/') || /^https?:\/\//.test(value) }
function imageFallback(event) { event.target.src = placeholderImage }
const aiSpecKeys = computed(() => Object.keys(specsFromText(form.specsText)).filter((key) => key.endsWith('(AI)')))
function resetAiState() { aiMessage.value = ''; aiSources.value = [] }
function resetForm() { editingId.value = null; Object.assign(form, { name: '', category: '', price: '', specsText: '', image: '', note: '' }); resetAiState(); showForm.value = true }
function closeForm() { if (!saving) showForm.value = false }
function edit(item) { editingId.value = item.id; Object.assign(form, { name: item.name, category: item.category || '', price: item.price ?? '', specsText: specsText(item.specs), image: item.image || '', note: item.note || '' }); resetAiState(); showForm.value = true }
async function completeWithAi() {
  if (!form.name.trim() || aiCompleting.value) return
  aiCompleting.value = true; aiMessage.value = ''; aiSources.value = []
  try {
    const draft = await completeCartItemDraft({ name: form.name.trim(), category: form.category.trim() })
    form.name = draft.name || form.name
    form.category = draft.category || form.category
    form.price = draft.price == null ? '' : draft.price
    form.specsText = specsText(draft.specs)
    aiSources.value = draft.sources || []
    aiMessage.value = aiSources.value.length ? `已根据 ${aiSources.value.length} 个公开来源补全，请核对后添加。` : '没查到资料，请手动填写。'
  } catch (error) { aiMessage.value = error.message || 'AI 补全失败，请手动填写。' } finally { aiCompleting.value = false }
}
async function uploadImageFile(event) {
  const file = event.target.files?.[0]
  event.target.value = '' // 清空，允许再次选同一个文件
  if (!file || uploading.value) return
  uploading.value = true
  try { form.image = await uploadImage(file); notify('图片已上传') }
  catch (error) { notify(error.message || '上传失败') }
  finally { uploading.value = false }
}
async function refresh() { loading.value = true; try { items.value = await listCartItems(); page.value = Math.min(page.value, Math.max(1, Math.ceil(items.value.length / pageSize))) } catch (error) { notify(error.message || '购物车读取失败') } finally { loading.value = false } }
async function save() { if (!form.name.trim() || saving.value) return; if (form.image.trim() && !validImageUrl(form.image.trim())) { notify('图片地址无效：http/https 链接或本地上传路径'); return } saving.value = true; const payload = { name: form.name.trim(), category: form.category.trim() || '其他', price: form.price === '' ? null : Number(form.price), specs: specsFromText(form.specsText), image: form.image.trim() || null, note: form.note.trim() || null }; try { if (editingId.value) await updateCartItem(editingId.value, payload); else await createCartItem(payload); showForm.value = false; editingId.value = null; await refresh(); notify('已保存') } catch (error) { notify(error.message || '保存失败') } finally { saving.value = false } }
async function remove(item) { try { await deleteCartItem(item.id); await refresh(); notify('已移除') } catch (error) { notify(error.message || '删除失败') } }
async function purchase(item) { try { await transferCartItem(item.id, { price: item.price, platform: null, purchased_at: new Date().toISOString(), note: item.note }); await refresh(); notify('已移入物品库') } catch (error) { notify(error.message || '移入失败') } }
onMounted(refresh)
</script>
<template>
  <div class="min-h-[calc(100dvh-4.5rem)] bg-zinc-50 dark:bg-zinc-950"><div class="mx-auto max-w-none px-5 pb-20 pt-9 sm:px-8 sm:pt-12">
    <div class="flex flex-wrap items-end justify-between gap-5 border-b border-zinc-200 pb-7 dark:border-zinc-800"><div><p class="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">Cart</p><h1 class="mt-2 text-2xl font-semibold text-zinc-950 dark:text-white">购物车</h1><p class="mt-2 text-sm text-zinc-500">保存待购买的商品参数，确认购买后可移入物品库。</p></div><button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-3.5 text-sm font-medium text-white" @click="resetForm"><PhPlus :size="17" />新增商品</button></div>
    <div class="mt-7">
      <section aria-label="待购买商品">
        <div class="mb-3">
          <h2 class="text-sm font-semibold">待购买商品 <span class="ml-1 text-zinc-400">{{ items.length }}</span></h2>
        </div>
        <div v-if="loading" class="rounded-2xl border bg-white px-6 py-16 text-center text-sm text-zinc-500">正在读取…</div>
        <div v-else-if="!items.length" class="rounded-2xl border border-dashed bg-white px-6 py-16 text-center dark:bg-zinc-900">
          <PhShoppingCart :size="30" class="mx-auto text-zinc-400" />
          <p class="mt-3 text-sm text-zinc-500">购物车还是空的</p>
        </div>
        <div v-else class="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
          <article v-for="item in items" :key="item.id" class="flex min-w-0 flex-col rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <div class="flex items-start gap-3">
              <img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-20 w-20 shrink-0 rounded-xl object-cover" @error="imageFallback" />
              <div class="min-w-0 flex-1">
                <p class="text-xs text-zinc-500">{{ item.category }}</p>
                <h3 class="mt-1 break-words font-semibold text-zinc-900 dark:text-white">{{ item.name }}</h3>
                <p class="mt-2 text-sm font-semibold">{{ item.price == null ? '—' : `${item.price} 元` }}</p>
              </div>
            </div>
            <div v-if="Object.keys(item.specs || {}).length" class="mt-4 flex flex-wrap gap-1.5 border-t border-zinc-100 pt-3 dark:border-zinc-800">
              <span v-for="(value, key) in item.specs" :key="key" class="max-w-full break-words rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{{ key }} {{ value }}<em v-if="key.endsWith('(AI)')" class="ml-1 not-italic text-blue-600 dark:text-blue-300">来源：网络</em></span>
            </div>
            <p v-if="item.note" class="mt-2 break-words text-xs text-zinc-500">{{ item.note }}</p>
            <div class="mt-4 flex-1"></div>
            <div class="flex flex-wrap gap-2 text-xs">
              <button type="button" class="text-accent" @click="edit(item)">编辑</button>
              <button type="button" class="text-emerald-700 dark:text-emerald-300" @click="purchase(item)">已购买，移入物品库</button>
              <button type="button" class="text-red-600" @click="remove(item)"><PhTrash :size="14" class="inline" /> 删除</button>
            </div>
          </article>
        </div>
      </section>
      <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-4" role="dialog" aria-modal="true" @click.self="closeForm" @keydown.esc="closeForm"><div class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900"><div class="flex items-center justify-between"><h2 class="font-semibold">{{ editingId ? '编辑商品' : '新增商品' }}</h2><button type="button" aria-label="关闭" title="关闭" @click="closeForm"><PhX :size="17" /></button></div><form class="mt-5 space-y-3" @submit.prevent="save"><div class="grid grid-cols-[minmax(0,1fr)_auto] gap-2"><input v-model="form.name" required maxlength="256" placeholder="商品名称" class="h-10 min-w-0 rounded-lg border px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" /><button type="button" :disabled="!form.name.trim() || aiCompleting" class="inline-flex h-10 items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 text-sm font-medium text-blue-700 disabled:opacity-50 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-300" @click="completeWithAi"><PhMagicWand :size="16" />{{ aiCompleting ? '补全中…' : 'AI 补全' }}</button></div><p v-if="aiMessage" class="rounded-lg bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-800 dark:bg-blue-950/40 dark:text-blue-200">{{ aiMessage }}<span v-if="aiSources.length" class="mt-1 block truncate text-blue-600 dark:text-blue-300">来源：{{ aiSources.join('、') }}</span></p><input v-model="form.category" maxlength="64" placeholder="分类" class="h-10 w-full rounded-lg border px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" /><input v-model="form.price" type="number" min="0" step="0.01" placeholder="价格（可选）" class="h-10 w-full rounded-lg border px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" /><p class="-mt-1 text-xs text-zinc-500">网络参考价可能过时，请以商品页实际价格为准。{{ aiSpecKeys.length ? `已补全 ${aiSpecKeys.length} 项网络参数。` : '' }}</p><p v-if="aiSpecKeys.length" class="-mb-1 text-xs text-blue-600 dark:text-blue-300">带有 (AI) 标记的规格来自网络参考资料。</p><textarea v-model="form.specsText" rows="4" placeholder="规格，每行一条：颜色: 黑色" class="w-full rounded-lg border px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950" /><div class="flex items-center gap-3 rounded-lg border border-dashed border-zinc-300 p-2 dark:border-zinc-700"><img :src="resolveImageUrl(form.image) || placeholderImage" alt="图片预览" class="h-14 w-14 rounded-md object-cover" @error="imageFallback" /><input v-model="form.image" type="text" maxlength="512" placeholder="图片链接（可选）" title="支持 http/https 链接，或点右侧按钮上传本地图片" class="h-10 w-full rounded-lg border px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950" /><button type="button" :disabled="uploading" class="inline-flex h-10 shrink-0 items-center rounded-lg border border-zinc-300 px-3 text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800" @click="fileInput?.click()">{{ uploading ? '上传中…' : '上传图片' }}</button><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="uploadImageFile" /></div><textarea v-model="form.note" rows="2" maxlength="512" placeholder="备注" class="w-full rounded-lg border px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950" /><button type="submit" :disabled="saving" class="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white disabled:opacity-50"><PhCheck :size="16" />{{ saving ? '保存中…' : '保存' }}</button></form></div></div></div>
    <p v-if="toast" class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white" role="status">{{ toast }}</p>
  </div></div>
</template>
