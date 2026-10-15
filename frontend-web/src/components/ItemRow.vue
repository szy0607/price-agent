<script setup>
// 引用面板里的一行商品（购物车 / 物品库共用）：缩略图 + 名称 + 分类 + 勾选框。
// disabled 用于「已挂满 MAX_REFS 件」时把未勾选的行置灰。
import { PhArchive, PhShoppingCart } from '@phosphor-icons/vue'
import { resolveImageUrl } from '../utils/api'

const props = defineProps({
  item: { type: Object, required: true },
  src: { type: String, required: true }, // 'cart' / 'owned'
  selected: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle'])

const placeholderImage = `${import.meta.env.BASE_URL}images/placeholder-item.png`
function imageFallback(event) { event.target.src = placeholderImage }
</script>

<template>
  <button
    type="button"
    class="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent dark:disabled:hover:bg-transparent dark:hover:bg-zinc-800"
    :class="selected ? 'bg-accent/10 ring-1 ring-accent/40' : ''"
    :disabled="disabled"
    :aria-pressed="selected"
    :title="item.name"
    @click="emit('toggle')"
  >
    <img
      :src="resolveImageUrl(item.image) || placeholderImage"
      :alt="item.name"
      class="h-9 w-9 shrink-0 rounded-md object-cover"
      @error="imageFallback"
    />
    <span class="min-w-0 flex-1">
      <span class="block truncate text-sm text-zinc-800 dark:text-zinc-200">{{ item.name }}</span>
      <span class="block truncate text-xs text-zinc-400">{{ item.category || '未分类' }}</span>
    </span>
    <span
      class="flex h-4 w-4 shrink-0 items-center justify-center rounded border"
      :class="selected ? 'border-accent bg-accent text-white' : 'border-zinc-300 dark:border-zinc-600'"
    >
      <span v-if="selected" class="text-[10px] leading-none">✓</span>
    </span>
  </button>
</template>