<script setup>
import { computed } from 'vue'
import { PhSealCheck, PhTag } from '@phosphor-icons/vue'
import { PLATFORMS, PLAT_KEYS, cheapest } from '../mock/data'

const props = defineProps({
  product: { type: Object, required: true },
  plat: { type: String, default: 'jd' },
})
const emit = defineEmits(['update:plat'])

const platTabs = PLAT_KEYS.map((k) => ({ key: k, name: PLATFORMS[k].name, accent: PLATFORMS[k].accent }))
const best = computed(() => cheapest(props.product, props.plat))
const platInfo = computed(() => PLATFORMS[props.plat])

function setPlat(k) {
  emit('update:plat', k)
}
</script>

<template>
  <div class="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm shadow-zinc-950/5 dark:border-zinc-800 dark:bg-zinc-900">
    <!-- 商品头 -->
    <div class="flex items-center gap-4 border-b border-zinc-100 p-5 dark:border-zinc-800">
      <img :src="product.image" :alt="product.name" class="h-16 w-16 rounded-xl object-cover" loading="lazy" />
      <div class="min-w-0">
        <div class="truncate text-[15px] font-semibold tracking-tight">{{ product.name }}</div>
        <div class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{{ product.brand }} · {{ product.model }}</div>
      </div>
    </div>

    <!-- 平台切换：三平台价格 tab -->
    <div class="flex gap-1 border-b border-zinc-100 p-3 dark:border-zinc-800">
      <button
        v-for="t in platTabs"
        :key="t.key"
        class="flex-1 rounded-lg px-2 py-1.5 text-[13px] font-medium transition-colors"
        :class="plat === t.key ? 'text-white' : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'"
        :style="plat === t.key ? { backgroundColor: t.accent } : {}"
        @click="setPlat(t.key)"
      >
        {{ t.name }}
      </button>
    </div>

    <!-- 双价矩阵（按当前平台） -->
    <div class="p-5">
      <div class="grid grid-cols-[1.5fr_1fr_1fr] gap-x-3 pb-2 text-[11px] text-zinc-500 dark:text-zinc-400">
        <span>款式</span>
        <span class="text-right">公开价 A</span>
        <span class="text-right">领券价 B</span>
      </div>
      <div
        v-for="s in product.skus"
        :key="s.name"
        class="grid grid-cols-[1.5fr_1fr_1fr] items-center gap-x-3 border-t border-zinc-100 py-2.5 text-sm dark:border-zinc-800/70"
      >
        <span class="flex items-center gap-1.5 truncate">
          <span class="truncate">{{ s.name }}</span>
          <span
            v-if="s.prices[plat].coupon.type === 'channel'"
            class="shrink-0 rounded-md bg-amber-100 px-1 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-400/15 dark:text-amber-300"
          >
            专享
          </span>
          <span
            v-if="s.prices[plat].subsidy"
            class="shrink-0 rounded-md border border-red-300 px-1 py-0.5 text-[10px] font-medium text-red-600 dark:border-red-500/50 dark:text-red-400"
          >
            补贴
          </span>
        </span>
        <span class="text-right font-mono text-price-a dark:text-red-400">¥{{ s.prices[plat].a }}</span>
        <span class="text-right font-mono font-semibold text-price-b dark:text-emerald-400">¥{{ s.prices[plat].b }}</span>
      </div>
    </div>

    <!-- 最低到手 -->
    <div class="flex items-center justify-between border-t border-zinc-100 bg-zinc-50/70 px-5 py-3.5 dark:border-zinc-800 dark:bg-zinc-800/40">
      <span class="flex items-center gap-1.5 text-[13px] text-zinc-600 dark:text-zinc-300">
        <PhSealCheck :size="16" weight="fill" class="text-price-b dark:text-emerald-400" />
        {{ platInfo.name }}最低到手：{{ best.name }}
      </span>
      <span class="font-mono text-lg font-bold text-price-b dark:text-emerald-400">¥{{ best.prices[plat].b }}</span>
    </div>

    <!-- 券说明 -->
    <div class="flex items-start gap-2 border-t border-zinc-100 px-5 py-3 text-xs leading-relaxed text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
      <PhTag :size="14" class="mt-0.5 shrink-0" />
      <span>
        {{ best.prices[plat].coupon.name }}：{{ best.prices[plat].coupon.threshold ? `满 ${best.prices[plat].coupon.threshold} 减 ` : '立减 ' }}{{ best.prices[plat].coupon.amount }}。{{ best.prices[plat].coupon.note }}
        <template v-if="best.prices[plat].plus">PLUS 价 ¥{{ best.prices[plat].plus }}</template>
      </span>
    </div>
  </div>
</template>
