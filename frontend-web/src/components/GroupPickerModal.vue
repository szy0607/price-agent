<script setup>
// 「加入分组」弹窗：购物车页与物品库页共用。自己拉分组列表，加入/新建并加入
// 都在这里完成，成功后把分组名抛给调用方去提示。
import { onMounted, ref } from 'vue'
import { PhPlus, PhX } from '@phosphor-icons/vue'
import { addGroupItem, createGroup, listGroups } from '../utils/api'

const props = defineProps({
  itemType: { type: String, required: true }, // 'cart' 购物车·未购买 / 'owned' 物品库·已购买
  itemId: { type: Number, required: true },
})
const emit = defineEmits(['close', 'added'])

const groups = ref([])
const loading = ref(true)
const submitting = ref(false)
const newName = ref('')
const message = ref('')

async function load() {
  loading.value = true
  try {
    groups.value = await listGroups()
  } catch (error) {
    message.value = error.message || '分组读取失败'
  } finally {
    loading.value = false
  }
}

async function addTo(group) {
  if (submitting.value) return
  submitting.value = true
  try {
    await addGroupItem(group.id, { item_type: props.itemType, item_id: props.itemId })
    emit('added', group.name)
  } catch (error) {
    // 「该物品已在分组中」这类后端人话直接透出
    message.value = error.message || '加入失败'
  } finally {
    submitting.value = false
  }
}

async function createAndAdd() {
  const name = newName.value.trim()
  if (!name || submitting.value) return
  submitting.value = true
  try {
    const group = await createGroup({ name })
    await addGroupItem(group.id, { item_type: props.itemType, item_id: props.itemId })
    emit('added', name)
  } catch (error) {
    message.value = error.message || '创建失败'
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-4" role="dialog" aria-modal="true" aria-label="加入分组" @click.self="emit('close')" @keydown.esc="emit('close')">
    <div class="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
      <div class="flex items-center justify-between">
        <h2 class="font-semibold text-zinc-900 dark:text-white">加入分组</h2>
        <button type="button" aria-label="关闭" title="关闭" class="text-zinc-500" @click="emit('close')"><PhX :size="17" /></button>
      </div>
      <p v-if="message" class="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs leading-5 text-red-700 dark:bg-red-950/40 dark:text-red-200" role="status">{{ message }}</p>
      <div v-if="loading" class="py-10 text-center text-sm text-zinc-500">正在读取分组…</div>
      <template v-else>
        <ul v-if="groups.length" class="mt-4 space-y-2">
          <li v-for="group in groups" :key="group.id">
            <button type="button" :disabled="submitting" class="flex w-full items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-2.5 text-left text-sm transition-colors hover:border-blue-300 hover:bg-blue-50/60 disabled:opacity-50 dark:border-zinc-700 dark:hover:border-blue-800 dark:hover:bg-blue-950/40" @click="addTo(group)">
              <span class="min-w-0">
                <span class="block truncate font-medium text-zinc-900 dark:text-white">{{ group.name }}</span>
                <span class="mt-0.5 block text-xs text-zinc-500">未购买 {{ group.unpurchased_count }} · 已购买 {{ group.purchased_count }}{{ group.unpriced_count ? ` · ${group.unpriced_count} 件未填价` : '' }}</span>
              </span>
              <span class="shrink-0 text-xs font-medium text-accent">加入</span>
            </button>
          </li>
        </ul>
        <p v-else class="mt-4 rounded-lg border border-dashed border-zinc-300 px-3 py-6 text-center text-sm text-zinc-500 dark:border-zinc-700">还没有分组，先创建一个</p>
        <div class="mt-4 flex gap-2 border-t border-zinc-100 pt-4 dark:border-zinc-800">
          <input v-model="newName" maxlength="100" placeholder="新分组名称" class="h-10 min-w-0 flex-1 rounded-lg border border-zinc-300 px-3 text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" @keyup.enter="createAndAdd" />
          <button type="button" :disabled="!newName.trim() || submitting" class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg bg-accent px-3.5 text-sm font-medium text-white disabled:opacity-50" @click="createAndAdd"><PhPlus :size="16" weight="bold" />新建并加入</button>
        </div>
      </template>
    </div>
  </div>
</template>
