<script setup>
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { PhArrowUpRight, PhCheck, PhDatabase, PhInfo, PhSealCheck, PhTrash, PhUploadSimple } from '@phosphor-icons/vue'
import { PLATFORMS, PLAT_KEYS, products } from '../mock/data'
import { parseProductLibrary } from '../utils/productLibrary'

const route = useRoute()
const rememberedId = typeof window !== 'undefined' ? window.sessionStorage.getItem('price-agent-compare-product') : ''
const initialId = route.query.id || rememberedId || products[0].id
const activeId = ref(products.some((p) => p.id === initialId) ? initialId : products[0].id)
const customProducts = ref([])
const libraryInput = ref(null)
const importError = ref('')
const importNotice = ref('')
const catalog = computed(() => [...products, ...customProducts.value])
const product = computed(() => catalog.value.find((item) => item.id === activeId.value) || products[0])
const plat = ref(PLAT_KEYS.includes(route.query.plat) ? route.query.plat : 'jd')

const platTabs = PLAT_KEYS.map((k) => ({ key: k, name: PLATFORMS[k].name, accent: PLATFORMS[k].accent }))
const demoProducts = products.map((p, index) => ({ ...p, label: `演示商品 ${index + 1}` }))

const specKeys = computed(() => {
  const keys = []
  product.value.skus.forEach((s) => {
    Object.keys(s.specs).forEach((k) => {
      if (!keys.includes(k)) keys.push(k)
    })
  })
  return keys
})

function useProduct(id) {
  if (!catalog.value.some((p) => p.id === id)) return
  activeId.value = id
  if (typeof window !== 'undefined') window.sessionStorage.setItem('price-agent-compare-product', id)
}

async function handleLibraryUpload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return

  importError.value = ''
  importNotice.value = ''
  try {
    const imported = parseProductLibrary(await file.text(), {
      fileName: file.name,
      fallbackImages: products.map((item) => item.image),
    })
    customProducts.value = imported
    useProduct(imported[0].id)
    importNotice.value = `已从 ${file.name} 本地解析 ${imported.length} 条商品数据。`
  } catch (error) {
    importError.value = error.message || '商品库文件无法解析'
  }
}

function clearCustomLibrary() {
  customProducts.value = []
  importError.value = ''
  importNotice.value = ''
  useProduct(products[0].id)
}
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div class="flex items-center gap-2 text-xs font-medium text-accent"><span class="h-1.5 w-1.5 rounded-full bg-accent"></span>价格对比演示</div>
        <h1 class="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">三平台价格对比</h1>
        <p class="mt-2 max-w-[64ch] text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">保留现有比价排版，当前使用本地演示数据展示款式、规格、公开价与领券价。</p>
      </div>
      <RouterLink to="/chat" class="inline-flex items-center gap-1.5 rounded-[10px] border border-zinc-300 px-3.5 py-2 text-sm font-medium text-zinc-700 transition-colors hover:border-accent hover:text-accent dark:border-zinc-700 dark:text-zinc-200">
        <PhArrowUpRight :size="15" /> 回到智能咨询
      </RouterLink>
    </div>

    <!-- 演示数据入口 -->
    <section class="mt-7 grid gap-4 lg:grid-cols-[0.9fr_1.4fr]" v-reveal>
      <div class="rounded-2xl border border-blue-200 bg-blue-50/70 p-5 dark:border-blue-900/60 dark:bg-blue-950/20">
        <div class="flex items-start gap-3">
          <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-accent shadow-sm dark:bg-zinc-900"><PhInfo :size="18" weight="bold" /></span>
          <div>
            <h2 class="text-sm font-semibold">演示数据 · 非实时</h2>
            <p class="mt-1 text-xs leading-5 text-zinc-600 dark:text-zinc-300">当前不请求淘宝、京东或拼多多的最新价格。页面内价格仅用于展示产品交互和排版，不能作为实际购买依据。</p>
          </div>
        </div>
      </div>

      <div class="rounded-2xl border border-zinc-200 bg-zinc-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/40">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold">选择演示商品</h2>
            <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">切换商品查看不同品类的比价排版</p>
          </div>
          <span class="text-[11px] text-zinc-400">{{ demoProducts.length }} 组数据</span>
        </div>
        <div class="mt-4 grid gap-2 sm:grid-cols-3">
          <button v-for="p in demoProducts" :key="p.id" class="flex min-w-0 items-center gap-2.5 rounded-xl border px-2.5 py-2 text-left transition-colors" :class="product.id === p.id ? 'border-accent/40 bg-white shadow-sm dark:bg-zinc-900' : 'border-transparent hover:border-zinc-300 hover:bg-white dark:hover:border-zinc-700 dark:hover:bg-zinc-900'" @click="useProduct(p.id)">
            <img :src="p.image" :alt="p.name" class="h-9 w-9 shrink-0 rounded-lg object-cover" loading="lazy" />
            <span class="min-w-0 flex-1"><span class="block truncate text-xs font-medium">{{ p.category }}</span><span class="mt-0.5 block truncate text-[10px] text-zinc-500">{{ p.label }}</span></span>
            <PhCheck v-if="product.id === p.id" :size="14" class="shrink-0 text-accent" weight="bold" />
          </button>
        </div>
      </div>
    </section>

    <!-- 自定义商品库 -->
    <section class="mt-4 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900" v-reveal>
      <div class="grid gap-5 p-5 lg:grid-cols-[0.9fr_1.4fr]">
        <div>
          <div class="flex items-center gap-2 text-sm font-semibold"><PhDatabase :size="18" class="text-accent" />自定义商品库 Demo</div>
          <p class="mt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">上传 JSON 或 CSV 商品库，在浏览器中本地解析并立即套用下方比价排版。文件不会上传服务器，也不会写入数据库。</p>
          <div class="mt-3 flex flex-wrap gap-1.5 text-[10px] text-zinc-500">
            <span class="rounded bg-zinc-100 px-2 py-1 dark:bg-zinc-800">name</span>
            <span class="rounded bg-zinc-100 px-2 py-1 dark:bg-zinc-800">category</span>
            <span class="rounded bg-zinc-100 px-2 py-1 dark:bg-zinc-800">brand</span>
            <span class="rounded bg-zinc-100 px-2 py-1 dark:bg-zinc-800">taobao_price</span>
            <span class="rounded bg-zinc-100 px-2 py-1 dark:bg-zinc-800">jd_price</span>
            <span class="rounded bg-zinc-100 px-2 py-1 dark:bg-zinc-800">pdd_price</span>
          </div>
        </div>

        <div class="flex flex-col justify-center">
          <input ref="libraryInput" type="file" accept=".json,.csv,application/json,text/csv" class="hidden" @change="handleLibraryUpload" />
          <button type="button" class="flex min-h-24 items-center justify-center gap-3 rounded-xl border border-dashed border-accent/40 bg-accent-soft/40 px-4 text-left transition-colors hover:border-accent hover:bg-accent-soft dark:bg-accent/10" @click="libraryInput?.click()">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-accent shadow-sm dark:bg-zinc-950"><PhUploadSimple :size="20" weight="bold" /></span>
            <span><span class="block text-sm font-medium text-accent-strong dark:text-blue-200">上传商品库文件</span><span class="mt-1 block text-xs text-zinc-500 dark:text-zinc-400">支持 JSON / CSV，Demo 最多读取前 50 条</span></span>
          </button>
          <p v-if="importError" class="mt-2 text-xs text-red-600 dark:text-red-400">{{ importError }}</p>
          <p v-else-if="importNotice" class="mt-2 flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-300"><PhCheck :size="14" weight="bold" />{{ importNotice }}</p>
        </div>
      </div>

      <div v-if="customProducts.length" class="border-t border-zinc-100 px-5 py-4 dark:border-zinc-800">
        <div class="flex items-center justify-between gap-3">
          <span class="text-xs font-medium text-zinc-600 dark:text-zinc-300">已导入 {{ customProducts.length }} 条自定义商品</span>
          <button type="button" class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-zinc-500 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-400/10 dark:hover:text-red-300" @click="clearCustomLibrary"><PhTrash :size="14" />清空导入</button>
        </div>
        <div class="mt-3 flex gap-2 overflow-x-auto pb-1">
          <button v-for="p in customProducts" :key="p.id" type="button" class="flex min-w-48 items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition-colors" :class="product.id === p.id ? 'border-accent/50 bg-accent-soft/50' : 'border-zinc-200 hover:border-zinc-300 dark:border-zinc-700'" @click="useProduct(p.id)">
            <img :src="p.image" :alt="p.name" class="h-9 w-9 rounded-lg object-cover" />
            <span class="min-w-0"><span class="block truncate text-xs font-medium">{{ p.name }}</span><span class="mt-0.5 block truncate text-[10px] text-zinc-500">{{ p.category }}</span></span>
          </button>
        </div>
      </div>
    </section>

    <!-- 当前商品 -->
    <div class="mt-8 flex flex-wrap items-center justify-between gap-4" v-reveal>
      <div class="flex min-w-0 items-center gap-4">
        <img :src="product.image" :alt="product.name" class="h-16 w-16 shrink-0 rounded-2xl object-cover sm:h-20 sm:w-20" />
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2"><span class="rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] font-medium text-accent-strong dark:bg-accent/15 dark:text-blue-300">当前比较</span><span class="text-xs text-zinc-500 dark:text-zinc-400">{{ product.category }}</span></div>
          <h2 class="mt-1 truncate text-lg font-semibold tracking-tight sm:text-xl">{{ product.name }}</h2>
          <p class="mt-1 truncate text-sm text-zinc-600 dark:text-zinc-400">{{ product.brand }} · {{ product.model }} · {{ product.skus.length }} 个款式</p>
        </div>
      </div>
      <div class="flex rounded-[10px] border border-zinc-200 p-1 dark:border-zinc-700">
        <button v-for="p in products" :key="p.id" class="rounded-lg px-3 py-1.5 text-xs transition-colors" :class="product.id === p.id ? 'bg-accent font-medium text-white' : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'" @click="useProduct(p.id)">{{ p.category }}</button>
        <span v-if="customProducts.some((item) => item.id === product.id)" class="rounded-lg bg-emerald-100 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300">自定义导入</span>
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
      本页为静态演示数据，不会获取平台最新价格；实际价格、优惠券有效期与库存请以对应平台页面为准。
    </p>
  </div>
</template>
