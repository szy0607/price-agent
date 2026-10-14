<script setup>
// 购物分组页：一个组件吃两个路由——/groups 列表（带每组统计），/groups/:id 详情
// （已购买/未购买两区 + 统计）。详情数据整页来自 GET /groups/{id}，刷新即一致。
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhFolder, PhPlus, PhTrash, PhX } from '@phosphor-icons/vue'
import { createGroup, deleteGroup, getGroupDetail, listGroups, removeGroupItem, resolveImageUrl, updateGroup } from '../utils/api'

const route = useRoute()
const router = useRouter()
const groupId = computed(() => (route.params.id ? Number(route.params.id) : null))

const groups = ref([])
const detail = ref(null)
const loading = ref(true)
const showForm = ref(false)
const editing = ref(false)
const submitting = ref(false)
const toast = ref('')
const form = reactive({ name: '', note: '' })
const placeholderImage = `${import.meta.env.BASE_URL}images/placeholder-item.png`

function notify(message) { toast.value = message; window.setTimeout(() => { toast.value = '' }, 2600) }
function money(value) { return `¥${Number(value || 0).toLocaleString('zh-CN')}` }
function imageFallback(event) { event.target.src = placeholderImage }

async function refresh() {
  loading.value = true
  try {
    if (groupId.value) {
      detail.value = await getGroupDetail(groupId.value)
    } else {
      detail.value = null
      groups.value = await listGroups()
    }
  } catch (error) {
    notify(error.message || '分组读取失败')
  } finally {
    loading.value = false
  }
}
watch(groupId, refresh)
onMounted(refresh)

function openCreate() { editing.value = false; Object.assign(form, { name: '', note: '' }); showForm.value = true }
function openEdit() {
  if (!detail.value) return
  editing.value = true
  Object.assign(form, { name: detail.value.group.name, note: detail.value.group.note || '' })
  showForm.value = true
}
function closeForm() { if (!submitting.value) showForm.value = false }

async function save() {
  const name = form.name.trim()
  if (!name || submitting.value) return
  submitting.value = true
  try {
    if (editing.value) {
      await updateGroup(groupId.value, { name, note: form.note.trim() || null })
      showForm.value = false
      await refresh()
      notify('已保存')
    } else {
      const group = await createGroup({ name, note: form.note.trim() || null })
      showForm.value = false
      router.push(`/groups/${group.id}`)
    }
  } catch (error) {
    notify(error.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

async function removeGroup() {
  if (!groupId.value || submitting.value) return
  submitting.value = true
  try {
    await deleteGroup(groupId.value)
    notify('分组已删除，物品不受影响')
    router.push('/groups')
  } catch (error) {
    notify(error.message || '删除失败')
  } finally {
    submitting.value = false
  }
}

async function removeItem(itemType, item) {
  if (!groupId.value) return
  try {
    await removeGroupItem(groupId.value, itemType, item.id)
    await refresh()
    notify('已移出分组')
  } catch (error) {
    notify(error.message || '移出失败')
  }
}
</script>

<template>
  <div class="min-h-[calc(100dvh-4.5rem)] bg-zinc-50 dark:bg-zinc-950"><div class="mx-auto max-w-none px-5 pb-20 pt-9 sm:px-8 sm:pt-12">
    <!-- 详情模式：/groups/:id -->
    <template v-if="groupId">
      <div class="flex flex-wrap items-end justify-between gap-5 border-b border-zinc-200 pb-7 dark:border-zinc-800">
        <div class="min-w-0">
          <button type="button" class="inline-flex items-center gap-1 text-sm text-zinc-500 transition-colors hover:text-zinc-900 dark:hover:text-white" @click="router.push('/groups')"><PhArrowLeft :size="15" /> 全部分组</button>
          <h1 class="mt-2 truncate text-2xl font-semibold text-zinc-950 dark:text-white">{{ detail?.group.name || '分组' }}</h1>
          <p v-if="detail?.group.note" class="mt-2 text-sm text-zinc-500">{{ detail.group.note }}</p>
        </div>
        <div v-if="detail" class="flex gap-2 text-xs">
          <button type="button" class="text-accent" @click="openEdit">重命名</button>
          <button type="button" class="text-red-600" @click="removeGroup"><PhTrash :size="14" class="inline" /> 删除分组</button>
        </div>
      </div>
      <div v-if="loading" class="mt-8 rounded-2xl border bg-white px-6 py-16 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">正在读取…</div>
      <template v-else-if="detail">
        <div class="mt-7 grid gap-4 sm:grid-cols-3">
          <div class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <p class="text-xs text-zinc-500">未购买合计（购物车）</p>
            <p class="mt-2 text-xl font-semibold text-zinc-900 dark:text-white">{{ money(detail.stats.unpurchased_total) }}</p>
            <p class="mt-1 text-xs text-zinc-400">{{ detail.stats.unpurchased_count }} 件</p>
          </div>
          <div class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <p class="text-xs text-zinc-500">已购买合计（物品库）</p>
            <p class="mt-2 text-xl font-semibold text-zinc-900 dark:text-white">{{ money(detail.stats.purchased_total) }}</p>
            <p class="mt-1 text-xs text-zinc-400">{{ detail.stats.purchased_count }} 件</p>
          </div>
          <div class="rounded-2xl border border-blue-200 bg-blue-50/60 p-5 dark:border-blue-900 dark:bg-blue-950/40">
            <p class="text-xs text-blue-700 dark:text-blue-300">分组总计</p>
            <p class="mt-2 text-xl font-semibold text-blue-900 dark:text-blue-100">{{ money(detail.stats.total) }}</p>
            <p class="mt-1 text-xs text-blue-600/80 dark:text-blue-300/80">未购买 + 已购买</p>
          </div>
        </div>
        <p v-if="detail.stats.unpriced_count" class="mt-3 text-xs text-amber-600 dark:text-amber-300">另有 {{ detail.stats.unpriced_count }} 件未填价格，未计入合计</p>
        <section class="mt-8" aria-label="未购买物品">
          <h2 class="mb-3 text-sm font-semibold">未购买 <span class="ml-1 text-zinc-400">{{ detail.stats.unpurchased_count }}</span></h2>
          <div v-if="!detail.unpurchased.length" class="rounded-2xl border border-dashed bg-white px-6 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900">还没有未购买的物品，去购物车把想买的商品加进来</div>
          <div v-else class="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
            <article v-for="item in detail.unpurchased" :key="item.id" class="flex min-w-0 flex-col rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
              <div class="flex items-start gap-3">
                <img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-20 w-20 shrink-0 rounded-xl object-cover" @error="imageFallback" />
                <div class="min-w-0 flex-1">
                  <p class="text-xs text-zinc-500">{{ item.category }}</p>
                  <h3 class="mt-1 break-words font-semibold text-zinc-900 dark:text-white">{{ item.name }}</h3>
                  <p v-if="item.price == null" class="mt-2 text-xs text-amber-600 dark:text-amber-300">未填价</p>
                  <p v-else class="mt-2 text-sm font-semibold">{{ money(item.price) }}</p>
                </div>
              </div>
              <div v-if="Object.keys(item.specs || {}).length" class="mt-4 flex flex-wrap gap-1.5 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                <span v-for="(value, key) in item.specs" :key="key" class="max-w-full break-words rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{{ key }} {{ value }}<em v-if="key.endsWith('(AI)')" class="ml-1 not-italic text-blue-600 dark:text-blue-300">来源：网络</em></span>
              </div>
              <p v-if="item.note" class="mt-2 break-words text-xs text-zinc-500">{{ item.note }}</p>
              <div class="mt-4 flex-1"></div>
              <div class="flex flex-wrap gap-2 text-xs">
                <button type="button" class="text-red-600" @click="removeItem('cart', item)"><PhTrash :size="14" class="inline" /> 移出分组</button>
              </div>
            </article>
          </div>
        </section>
        <section class="mt-8" aria-label="已购买物品">
          <h2 class="mb-3 text-sm font-semibold">已购买 <span class="ml-1 text-zinc-400">{{ detail.stats.purchased_count }}</span></h2>
          <div v-if="!detail.purchased.length" class="rounded-2xl border border-dashed bg-white px-6 py-10 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900">还没有已购买的物品，在物品库把商品加进来</div>
          <div v-else class="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
            <article v-for="item in detail.purchased" :key="item.id" class="flex min-w-0 flex-col rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
              <div class="flex items-start gap-3">
                <img :src="resolveImageUrl(item.image) || placeholderImage" :alt="item.name" class="h-20 w-20 shrink-0 rounded-xl object-cover" @error="imageFallback" />
                <div class="min-w-0 flex-1">
                  <p class="text-xs text-zinc-500">{{ item.category }}</p>
                  <h3 class="mt-1 break-words font-semibold text-zinc-900 dark:text-white">{{ item.name }}</h3>
                  <p v-if="item.price == null" class="mt-2 text-xs text-amber-600 dark:text-amber-300">未填价</p>
                  <p v-else class="mt-2 text-sm font-semibold">{{ money(item.price) }}</p>
                </div>
              </div>
              <div v-if="Object.keys(item.specs || {}).length" class="mt-4 flex flex-wrap gap-1.5 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                <span v-for="(value, key) in item.specs" :key="key" class="max-w-full break-words rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">{{ key }} {{ value }}<em v-if="key.endsWith('(AI)')" class="ml-1 not-italic text-blue-600 dark:text-blue-300">来源：网络</em></span>
              </div>
              <p v-if="item.note" class="mt-2 break-words text-xs text-zinc-500">{{ item.note }}</p>
              <div class="mt-4 flex-1"></div>
              <div class="flex flex-wrap gap-2 text-xs">
                <button type="button" class="text-red-600" @click="removeItem('owned', item)"><PhTrash :size="14" class="inline" /> 移出分组</button>
              </div>
            </article>
          </div>
        </section>
      </template>
      <div v-else class="mt-8 rounded-2xl border border-dashed bg-white px-6 py-16 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900">分组不存在或读取失败</div>
    </template>
    <!-- 列表模式：/groups -->
    <template v-else>
      <div class="flex flex-wrap items-end justify-between gap-5 border-b border-zinc-200 pb-7 dark:border-zinc-800">
        <div>
          <p class="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">Groups</p>
          <h1 class="mt-2 text-2xl font-semibold text-zinc-950 dark:text-white">购物分组</h1>
          <p class="mt-2 text-sm text-zinc-500">把购物车（未购买）和物品库（已购买）里的物品归成一组，随时查看进度和价格合计。</p>
        </div>
        <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-3.5 text-sm font-medium text-white" @click="openCreate"><PhPlus :size="17" />新建分组</button>
      </div>
      <div class="mt-7">
        <div v-if="loading" class="rounded-2xl border bg-white px-6 py-16 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">正在读取…</div>
        <div v-else-if="!groups.length" class="rounded-2xl border border-dashed bg-white px-6 py-16 text-center dark:border-zinc-700 dark:bg-zinc-900">
          <PhFolder :size="30" class="mx-auto text-zinc-400" />
          <p class="mt-3 text-sm text-zinc-500">还没有分组。去购物车或物品库，点商品卡片上的「加入分组」即可创建。</p>
        </div>
        <div v-else class="grid gap-4 md:grid-cols-3 xl:grid-cols-4">
          <RouterLink v-for="group in groups" :key="group.id" :to="`/groups/${group.id}`" class="flex min-w-0 flex-col rounded-2xl border border-zinc-200 bg-white p-5 transition-colors hover:border-blue-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-blue-800">
            <h2 class="break-words font-semibold text-zinc-900 dark:text-white">{{ group.name }}</h2>
            <p v-if="group.note" class="mt-1 break-words text-xs text-zinc-500">{{ group.note }}</p>
            <p class="mt-3 text-xs text-zinc-500">未购买 {{ group.unpurchased_count }} · 已购买 {{ group.purchased_count }}</p>
            <p class="mt-2 text-lg font-semibold text-zinc-900 dark:text-white">{{ money(group.total) }}</p>
            <p v-if="group.unpriced_count" class="mt-1 text-xs text-amber-600 dark:text-amber-300">{{ group.unpriced_count }} 件未填价，未计入合计</p>
          </RouterLink>
        </div>
      </div>
    </template>
    <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-4" role="dialog" aria-modal="true" :aria-label="editing ? '重命名分组' : '新建分组'" @click.self="closeForm" @keydown.esc="closeForm">
      <div class="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
        <div class="flex items-center justify-between"><h2 class="font-semibold text-zinc-900 dark:text-white">{{ editing ? '重命名分组' : '新建分组' }}</h2><button type="button" aria-label="关闭" title="关闭" class="text-zinc-500" @click="closeForm"><PhX :size="17" /></button></div>
        <form class="mt-5 space-y-3" @submit.prevent="save">
          <input v-model="form.name" required maxlength="100" placeholder="分组名称" class="h-10 w-full rounded-lg border border-zinc-300 px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" />
          <textarea v-model="form.note" rows="2" maxlength="512" placeholder="备注（可选）" class="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" />
          <button type="submit" :disabled="submitting" class="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white disabled:opacity-50">{{ submitting ? '保存中…' : '保存' }}</button>
        </form>
      </div>
    </div>
    <p v-if="toast" class="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white" role="status">{{ toast }}</p>
  </div></div>
</template>
