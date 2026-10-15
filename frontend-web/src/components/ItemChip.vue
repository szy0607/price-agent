<script setup>
// 商品引用 chip：输入框上方的「待发送」（removable）与历史消息里的「已发送」
// （只读、onAccent 反色）共用一个组件，保证两处视觉一致。
import { PhArchive, PhShoppingCart, PhX } from '@phosphor-icons/vue'

const props = defineProps({
  src: { type: String, required: true }, // 'cart' 购物车 / 'owned' 物品库
  name: { type: String, required: true },
  removable: { type: Boolean, default: false }, // 显示删除按钮
  onAccent: { type: Boolean, default: false }, // 蓝底气泡内用反色
})
const emit = defineEmits(['remove'])
</script>

<template>
  <span
    class="inline-flex max-w-[11rem] items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium"
    :class="onAccent
      ? 'bg-white/20 text-white ring-1 ring-white/30'
      : 'bg-white/85 text-blue-900 dark:bg-zinc-900/80 dark:text-zinc-100'"
    :title="name"
  >
    <component :is="src === 'cart' ? PhShoppingCart : PhArchive" :size="12" class="shrink-0" />
    <span class="truncate">{{ name }}</span>
    <button
      v-if="removable"
      type="button"
      class="shrink-0 opacity-60 transition-opacity hover:opacity-100"
      :class="onAccent ? 'hover:text-white' : 'hover:text-blue-700 dark:hover:text-zinc-200'"
      :aria-label="`取消引用 ${name}`"
      @click.stop="emit('remove')"
    >
      <PhX :size="11" />
    </button>
  </span>
</template>