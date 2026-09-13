<script setup>
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { PhSealCheck } from '@phosphor-icons/vue'
import { PLATFORMS, PLAT_KEYS, products } from '../mock/data'

const route = useRoute()
const initIdx = Math.max(0, products.findIndex((p) => p.id === route.query.id))
const activeIdx = ref(initIdx)
const product = computed(() => products[activeIdx.value])
const plat = ref(route.query.plat || 'jd')

const platTabs = PLAT_KEYS.map((k) => ({ key: k, name: PLATFORMS[k].name, accent: PLATFORMS[k].accent }))

const specKeys = computed(() => {
  const keys = []
  product.value.skus.forEach((s) => {
    Object.keys(s.specs).forEach((k) => {
      if (!keys.includes(k)) keys.push(k)
    })
  })
  return keys
})
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-10">
    <!-- 商品切换 -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <h1 class="text-2xl font-semibold tracking-tight md:text-3xl">款式对比</h1>
      <div class="flex rounded-[10px] border border-zinc-200 p-1 dark:border-zinc-700">
        <button
          v-for="(p, i) in products"
          :key="p.id"
          class="rounded-lg px-4 py-1.5 text-sm transition-colors"
          :class="
            activeIdx === i
              ? 'bg-accent font-medium text-white'
              : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
          "
          @click="activeIdx = i"
        >
          {{ p.category }}
        </button>
      </div>
    </div>

    <!-- 商品头 -->
    <div class="mt-8 flex items-center gap-5" v-reveal>
      <img :src="product.image" :alt="product.name" class="h-20 w-20 rounded-2xl object-cover" />
      <div>
        <h2 class="text-xl font-semibold tracking-tight">{{ product.name }}</h2>
        <p class="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{{ product.desc }}</p>
        <p class="mt-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          {{ product.brand }} · {{ product.model }} · 三平台价格由联盟查券 API 采集
        </p>
      </div>
    </div>

    <!-- 平台切换 -->
    <div class="mt-6 flex w-fit rounded-[10px] border border-zinc-200 bg-white p-1 dark:border-zinc-700 dark:bg-zinc-900">
      <button
        v-for="t in platTabs"
        :key="t.key"
        class="rounded-lg px-5 py-1.5 text-sm font-medium transition-colors"
        :class="
          plat === t.key
            ? 'text-white'
            : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
        "
        :style="plat === t.key ? { backgroundColor: t.accent } : {}"
        @click="plat = t.key"
      >
        {{ t.name }}
      </button>
    </div>

    <!-- 款式卡片行 -->
    <div class="mt-8 grid gap-4 md:grid-cols-3" v-reveal>
      <div
        v-for="s in product.skus"
        :key="s.name"
        class="overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
      >
        <div class="flex items-center gap-3 border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
          <img :src="s.image" :alt="s.name" class="h-9 w-9 rounded-lg object-cover" loading="lazy" />
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-semibold">{{ s.name }}</div>
            <div class="text-[11px]" :class="s.stock === '有货' ? 'text-zinc-500 dark:text-zinc-400' : 'text-amber-600 dark:text-amber-400'">
              {{ s.stock }}
            </div>
          </div>
          <span
            v-if="s.prices[plat].subsidy"
            class="rounded-md border border-red-300 px-1.5 py-0.5 text-[10px] font-medium text-red-600 dark:border-red-500/50 dark:text-red-400"
          >
            百亿补贴
          </span>
        </div>
        <div class="space-y-2 px-4 py-4">
          <div class="flex items-baseline justify-between">
            <span class="text-xs text-zinc-500 dark:text-zinc-400">公开价 A</span>
            <span class="font-mono text-price-a dark:text-red-400">¥{{ s.prices[plat].a }}</span>
          </div>
          <div class="flex items-baseline justify-between">
            <span class="text-xs text-zinc-500 dark:text-zinc-400">领券价 B</span>
            <span class="font-mono text-lg font-bold text-price-b dark:text-emerald-400">¥{{ s.prices[plat].b }}</span>
          </div>
          <div v-if="s.prices[plat].plus" class="flex items-baseline justify-between text-[11px] text-zinc-500 dark:text-zinc-400">
            <span>PLUS 会员价</span>
            <span class="font-mono">¥{{ s.prices[plat].plus }}</span>
          </div>
        </div>
        <div class="border-t border-zinc-100 px-4 py-3 text-xs leading-relaxed text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <span
            class="mr-1.5 rounded-md px-1.5 py-0.5 text-[10px] font-medium"
            :class="s.prices[plat].coupon.type === 'public'
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
              : 'bg-amber-100 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'"
          >
            {{ s.prices[plat].coupon.type === 'public' ? '公开券' : '渠道专享' }}
          </span>
          {{ s.prices[plat].coupon.name }} {{ s.prices[plat].coupon.threshold ? `满 ${s.prices[plat].coupon.threshold} 减 ` : '立减 ' }}{{ s.prices[plat].coupon.amount }}
        </div>
      </div>
    </div>

    <!-- 规格表 + 结论 -->
    <div class="mt-8 grid gap-6 lg:grid-cols-12" v-reveal>
      <div class="overflow-hidden rounded-2xl border border-zinc-200 bg-white lg:col-span-8 dark:border-zinc-800 dark:bg-zinc-900">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-800/60 dark:text-zinc-400">
              <th class="px-5 py-3 font-medium">参数</th>
              <th v-for="s in product.skus" :key="s.name" class="px-5 py-3 font-medium">{{ s.name }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-100 dark:divide-zinc-800">
            <tr v-for="k in specKeys" :key="k">
              <td class="px-5 py-3 text-zinc-500 dark:text-zinc-400">{{ k }}</td>
              <td v-for="s in product.skus" :key="s.name" class="px-5 py-3">{{ s.specs[k] || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="flex flex-col gap-4 lg:col-span-4">
        <div class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <div class="flex items-center gap-1.5 text-sm font-semibold">
            <PhSealCheck :size="17" weight="fill" class="text-accent" />
            对比结论
          </div>
          <p class="mt-3 text-[13px] leading-relaxed text-zinc-600 dark:text-zinc-300">{{ product.conclusion }}</p>
        </div>
        <RouterLink
          :to="{ path: '/coupon', query: { id: product.id, plat } }"
          class="inline-flex items-center justify-center rounded-[10px] bg-accent px-4 py-3 text-sm font-medium text-white transition-transform hover:bg-accent-strong active:scale-[0.98]"
        >
          查看领券步骤
        </RouterLink>
      </div>
    </div>

    <p class="mt-8 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
      演示价格模拟真实市场区间，正式版由联盟查券 API 实时返回；券的有效期、余量与最终到手价以平台页面实时展示为准。
    </p>
  </div>
</template>
