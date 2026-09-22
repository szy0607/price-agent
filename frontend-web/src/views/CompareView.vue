<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { PhArrowUpRight, PhCheck, PhCloudArrowUp, PhLink, PhMagnifyingGlass, PhSealCheck, PhX } from '@phosphor-icons/vue'
import { matchProduct, PLATFORMS, PLAT_KEYS, products } from '../mock/data'

const route = useRoute()
const rememberedId = typeof window !== 'undefined' ? window.sessionStorage.getItem('price-agent-compare-product') : ''
const initialId = route.query.id || rememberedId || products[0].id
const initIdx = Math.max(0, products.findIndex((p) => p.id === initialId))
const activeIdx = ref(initIdx)
const product = computed(() => products[activeIdx.value])
const plat = ref(PLAT_KEYS.includes(route.query.plat) ? route.query.plat : 'jd')
const sourceUrl = ref('')
const sourceError = ref('')
const sourceNotice = ref(route.query.source === 'chat' ? '已从智能咨询带入商品，你可以继续添加图片或链接。' : '')
const uploadedImage = ref('')
const fileInput = ref(null)

const platTabs = PLAT_KEYS.map((k) => ({ key: k, name: PLATFORMS[k].name, accent: PLATFORMS[k].accent }))
const recentProducts = products.map((p, index) => ({ ...p, recent: index === 0 ? '刚刚在咨询中使用' : index === 1 ? '昨天咨询过' : '周二咨询过' }))

const specKeys = computed(() => {
  const keys = []
  product.value.skus.forEach((s) => {
    Object.keys(s.specs).forEach((k) => {
      if (!keys.includes(k)) keys.push(k)
    })
  })
  return keys
})

function useProduct(id, notice = '已载入商品，可以开始比价。') {
  const index = products.findIndex((p) => p.id === id)
  if (index < 0) return
  activeIdx.value = index
  sourceNotice.value = notice
  sourceError.value = ''
  if (typeof window !== 'undefined') window.sessionStorage.setItem('price-agent-compare-product', id)
}

function analyzeUrl() {
  const value = sourceUrl.value.trim()
  if (!value) {
    sourceError.value = '请先粘贴商品链接或输入品牌、品类关键词。'
    return
  }
  const result = matchProduct(value)
  if (!result.product) {
    sourceError.value = '暂时没有识别到演示商品。可以试试“索尼耳机”“象印保温杯”或“芙丽芳丝”。'
    return
  }
  useProduct(result.product.id, result.viaLink ? '已识别平台链接，正在展示该商品的款式与价格情报。' : '已按关键词定位商品，正在展示可比款式。')
  sourceUrl.value = ''
}

function pickImage(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    sourceError.value = '只支持 JPG、PNG 或 WebP 图片。'
    return
  }
  if (uploadedImage.value) URL.revokeObjectURL(uploadedImage.value)
  uploadedImage.value = URL.createObjectURL(file)
  const result = matchProduct(file.name)
  useProduct(result.product?.id || products[0].id, '已收到商品图片，演示环境已完成图像定位并载入候选款式。')
}

function clearImage() {
  if (uploadedImage.value) URL.revokeObjectURL(uploadedImage.value)
  uploadedImage.value = ''
}

onBeforeUnmount(clearImage)
</script>

<template>
  <div class="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div class="flex items-center gap-2 text-xs font-medium text-accent"><span class="h-1.5 w-1.5 rounded-full bg-accent"></span>商品情报工作台</div>
        <h1 class="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">先把商品放进来，再比较</h1>
        <p class="mt-2 max-w-[64ch] text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">上传商品图、粘贴平台链接，或直接从智能咨询带入。识别完成后，款式、规格和三平台价格会在同一个工作区展开。</p>
      </div>
      <RouterLink to="/chat" class="inline-flex items-center gap-1.5 rounded-[10px] border border-zinc-300 px-3.5 py-2 text-sm font-medium text-zinc-700 transition-colors hover:border-accent hover:text-accent dark:border-zinc-700 dark:text-zinc-200">
        <PhArrowUpRight :size="15" /> 回到智能咨询
      </RouterLink>
    </div>

    <!-- 商品来源入口 -->
    <section class="mt-7 grid gap-4 lg:grid-cols-[1.1fr_1fr]" v-reveal>
      <div class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold">添加商品</h2>
            <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">支持图片定位和平台链接识别</p>
          </div>
          <span class="rounded-md bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300">不需要登录平台</span>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-[180px_1fr]">
          <button class="group flex min-h-28 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-accent/40 bg-accent-soft/60 px-3 text-center transition-colors hover:border-accent hover:bg-accent-soft dark:border-accent/40 dark:bg-accent/10 dark:hover:bg-accent/15" @click="fileInput?.click()">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-accent shadow-sm dark:bg-zinc-900"><PhCloudArrowUp :size="19" weight="bold" /></span>
            <span class="text-xs font-medium text-accent-strong dark:text-blue-200">上传商品图片</span>
            <span class="text-[10px] text-zinc-500 dark:text-zinc-400">JPG / PNG / WebP</span>
          </button>
          <div class="flex min-h-28 flex-col justify-center">
            <label for="compare-source-url" class="text-xs font-medium text-zinc-600 dark:text-zinc-300">粘贴链接或输入关键词</label>
            <div class="mt-2 flex gap-2">
              <div class="relative min-w-0 flex-1">
                <PhLink :size="15" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                <input id="compare-source-url" v-model="sourceUrl" type="text" placeholder="淘宝 / 京东 / 拼多多链接，或“索尼耳机”" class="w-full rounded-[10px] border border-zinc-300 bg-white py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-zinc-700 dark:bg-zinc-950" @keydown.enter="analyzeUrl" />
              </div>
              <button class="inline-flex shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-3.5 py-2.5 text-sm font-medium text-white transition hover:bg-accent-strong active:scale-[0.98]" @click="analyzeUrl"><PhMagnifyingGlass :size="15" />识别</button>
            </div>
            <p v-if="sourceError" class="mt-2 text-xs text-red-600 dark:text-red-400">{{ sourceError }}</p>
            <p v-else-if="sourceNotice" class="mt-2 flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-300"><PhCheck :size="14" weight="bold" />{{ sourceNotice }}</p>
          </div>
        </div>
        <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="pickImage" />
        <div v-if="uploadedImage" class="mt-3 flex items-center gap-3 rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-950">
          <img :src="uploadedImage" alt="已上传的商品图片" class="h-10 w-10 rounded-lg object-cover" />
          <span class="min-w-0 flex-1 truncate text-xs text-zinc-600 dark:text-zinc-300">图片已加入当前对比工作区</span>
          <button aria-label="移除商品图片" class="rounded-md p-1.5 text-zinc-400 hover:bg-white hover:text-zinc-700 dark:hover:bg-zinc-800" @click="clearImage"><PhX :size="14" /></button>
        </div>
      </div>

      <div class="rounded-2xl border border-zinc-200 bg-zinc-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-950/40">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="text-sm font-semibold">从最近咨询导入</h2>
            <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">对话里识别过的商品会保留在这里</p>
          </div>
          <span class="text-[11px] text-zinc-400">{{ recentProducts.length }} 个可用</span>
        </div>
        <div class="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
          <button v-for="p in recentProducts" :key="p.id" class="flex min-w-0 items-center gap-2.5 rounded-xl border px-2.5 py-2 text-left transition-colors" :class="product.id === p.id ? 'border-accent/40 bg-white shadow-sm dark:bg-zinc-900' : 'border-transparent hover:border-zinc-300 hover:bg-white dark:hover:border-zinc-700 dark:hover:bg-zinc-900'" @click="useProduct(p.id, `已从最近咨询导入「${p.name}」。`)">
            <img :src="p.image" :alt="p.name" class="h-9 w-9 shrink-0 rounded-lg object-cover" loading="lazy" />
            <span class="min-w-0 flex-1"><span class="block truncate text-xs font-medium">{{ p.category }}</span><span class="mt-0.5 block truncate text-[10px] text-zinc-500">{{ p.recent }}</span></span>
            <PhCheck v-if="product.id === p.id" :size="14" class="shrink-0 text-accent" weight="bold" />
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
        <button v-for="(p, i) in products" :key="p.id" class="rounded-lg px-3 py-1.5 text-xs transition-colors" :class="activeIdx === i ? 'bg-accent font-medium text-white' : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'" @click="useProduct(p.id, `已切换到「${p.name}」。`)">{{ p.category }}</button>
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
