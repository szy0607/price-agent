<script setup>
import { RouterLink } from 'vue-router'
import {
  PhArrowRight,
  PhCoins,
  PhEye,
  PhLinkSimple,
  PhShieldCheck,
  PhStack,
} from '@phosphor-icons/vue'
import DualPriceCard from '../components/DualPriceCard.vue'
import BrandIcon from '../components/BrandIcon.vue'
import { apiContract, products, PLATFORMS, bestPlat } from '../mock/data'

const heroProduct = products[0]
const heroPlat = bestPlat(heroProduct).plat

/** 全场（跨平台）最低到手价，用于首页品类卡「¥xx 起」 */
const lowest = (p) => Math.min(...['taobao', 'jd', 'pdd'].map((k) => Math.min(...p.skus.map((s) => s.prices[k].b))))

const principles = [
  { icon: PhShieldCheck, title: 'AI 是顾问，不是代购', desc: '不碰登录态、不碰支付、不碰资金，交易 100% 由你完成。' },
  { icon: PhEye, title: '双价透明', desc: '公开价与领券价同时展示，领不到的券明确说明限制。' },
  { icon: PhLinkSimple, title: '不提供推广链接', desc: '只给领券路径，你自己找券、自己下单，建立信任。' },
  { icon: PhCoins, title: '官方数据源', desc: '联盟查券 API 实时查询，不使用评论区任何数据。' },
]
</script>

<template>
  <div>
    <!-- Hero：不对称分栏 + 顶部氛围光（单色低调，避免渐变横幅感） -->
    <section class="relative mx-auto grid max-w-7xl items-center gap-12 overflow-visible px-6 pb-20 pt-16 lg:grid-cols-12 lg:pt-24">
      <div
        aria-hidden="true"
        class="pointer-events-none absolute -inset-x-6 -top-24 -z-10 h-[520px]"
        style="background: radial-gradient(640px 300px at 72% 8%, rgb(37 99 235 / 0.08), transparent 70%), radial-gradient(420px 220px at 18% 0%, rgb(37 99 235 / 0.05), transparent 70%)"
      ></div>
      <div class="lg:col-span-6">
        <p class="mb-5 inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
          <BrandIcon :size="14" class="text-accent" />
          购物决策助手
        </p>
        <h1 class="text-4xl font-bold leading-[1.1] tracking-tighter md:text-6xl">
          买之前，<br />先问一句。
        </h1>
        <p class="mt-5 max-w-[46ch] text-base leading-relaxed text-zinc-600 dark:text-zinc-400">
          对比款式差异，测算公开价与领券价，给出领券步骤。下单永远由你自己完成。
        </p>
        <div class="mt-8 flex items-center gap-3">
          <RouterLink
            to="/chat"
            class="inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-5 py-3 text-sm font-medium text-white transition-transform hover:bg-accent-strong active:scale-[0.98]"
          >
            开始咨询
            <PhArrowRight :size="15" weight="bold" />
          </RouterLink>
          <RouterLink
            to="/coupon"
            class="inline-flex items-center rounded-[10px] border border-zinc-300 px-5 py-3 text-sm font-medium text-zinc-700 transition-colors hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            查看领券指引
          </RouterLink>
        </div>
      </div>
      <!-- 右侧：真实的双价卡片组件预览（非贴图） -->
      <div class="lg:col-span-6" v-reveal>
        <div class="mx-auto max-w-md lg:ml-auto lg:mr-0">
          <DualPriceCard :product="heroProduct" :plat="heroPlat" />
        </div>
      </div>
    </section>

    <!-- 数据源：三平台能力表（真实内容表格） -->
    <section class="border-y border-zinc-200/70 bg-white dark:border-zinc-800 dark:bg-zinc-900/40">
      <div class="mx-auto max-w-7xl px-6 py-16" v-reveal>
        <h2 class="text-2xl font-semibold tracking-tight md:text-3xl">三个平台，一个接口</h2>
        <p class="mt-3 max-w-[60ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">
          数据来自各平台官方联盟查券 API，只使用查询能力，与推广变现彻底解耦。
        </p>
        <div class="mt-8 overflow-hidden rounded-2xl border border-zinc-200 dark:border-zinc-800">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-800/60 dark:text-zinc-400">
                <th class="px-5 py-3 font-medium">平台</th>
                <th class="px-5 py-3 font-medium">查券接口</th>
                <th class="hidden px-5 py-3 font-medium md:table-cell">关键字段</th>
                <th class="hidden px-5 py-3 font-medium lg:table-cell">注册门槛</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-zinc-100 dark:divide-zinc-800">
              <tr v-for="(p, key) in PLATFORMS" :key="key" class="bg-white dark:bg-transparent">
                <td class="px-5 py-4">
                  <span
                    class="rounded-md px-2 py-1 text-[13px] font-medium"
                    :style="{ color: p.accent, backgroundColor: p.accent + '12' }"
                  >
                    {{ p.name }}
                  </span>
                </td>
                <td class="px-5 py-4 font-mono text-[13px] text-zinc-600 dark:text-zinc-300">{{ p.api }}</td>
                <td class="hidden px-5 py-4 text-zinc-600 md:table-cell dark:text-zinc-300">{{ p.keyFields.join('、') }}</td>
                <td class="hidden px-5 py-4 text-zinc-600 lg:table-cell dark:text-zinc-300">{{ p.register }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- 品类演示：不对称图片网格 -->
    <section class="mx-auto max-w-7xl px-6 py-16" v-reveal>
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 class="text-2xl font-semibold tracking-tight md:text-3xl">全品类都问得</h2>
          <p class="mt-3 max-w-[55ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">
            数码、家居、美妆，粘贴商品链接或直接提问，Agent 采集款式与价格情报后给出对比与推荐。
          </p>
        </div>
        <RouterLink
          to="/compare"
          class="inline-flex items-center gap-1 text-sm font-medium text-accent transition-colors hover:text-accent-strong"
        >
          查看对比演示
          <PhArrowRight :size="14" weight="bold" />
        </RouterLink>
      </div>
      <div class="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-5">
        <RouterLink
          v-for="(p, i) in products"
          :key="p.id"
          :to="{ path: '/compare', query: { id: p.id } }"
          class="group overflow-hidden rounded-2xl border border-zinc-200 bg-white transition-shadow hover:shadow-lg hover:shadow-zinc-950/10 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:shadow-black/40"
          :class="i === 0 ? 'lg:col-span-3 lg:row-span-2' : 'lg:col-span-2'"
        >
          <div class="overflow-hidden" :class="i === 0 ? 'aspect-[16/9]' : 'aspect-[3/1.4]'">
            <img
              :src="p.image"
              :alt="p.name"
              class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
              loading="lazy"
            />
          </div>
          <div class="flex items-center justify-between p-5">
            <div>
              <div class="text-[15px] font-semibold tracking-tight">{{ p.name }}</div>
              <div class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{{ p.category }} · {{ p.brand }}</div>
            </div>
            <span class="font-mono text-lg font-bold text-price-b dark:text-emerald-400">¥{{ lowest(p) }} 起</span>
          </div>
        </RouterLink>
      </div>
    </section>

    <!-- 原则：左右分栏 + 2x2 -->
    <section class="border-y border-zinc-200/70 bg-white dark:border-zinc-800 dark:bg-zinc-900/40">
      <div class="mx-auto grid max-w-7xl gap-12 px-6 py-16 lg:grid-cols-12" v-reveal>
        <div class="lg:col-span-4">
          <h2 class="text-2xl font-semibold tracking-tight md:text-3xl">顾问的本分</h2>
          <p class="mt-3 max-w-[40ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">
            四条原则写进产品里：信息透明、不误导，是这款工具能被信任的前提。
          </p>
        </div>
        <div class="grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:col-span-8">
          <div v-for="pr in principles" :key="pr.title">
            <pr.icon :size="22" class="text-accent" />
            <div class="mt-3 text-[15px] font-semibold">{{ pr.title }}</div>
            <p class="mt-1.5 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{{ pr.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 接口契约：等宽字体清单 -->
    <section class="mx-auto max-w-7xl px-6 py-16" v-reveal>
      <div class="grid gap-10 lg:grid-cols-12">
        <div class="lg:col-span-5">
          <h2 class="text-2xl font-semibold tracking-tight md:text-3xl">背后是五个 Agent</h2>
          <p class="mt-3 max-w-[48ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">
            理解路由、商品情报、价格情报、款式对比、推荐引导各司其职，Agent 之间只传结构化数据，不传自然语言。
          </p>
          <p class="mt-3 max-w-[48ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">
            对外暴露统一的适配层接口，Demo 阶段由本地 Mock 数据源模拟返回。
          </p>
        </div>
        <div class="lg:col-span-7">
          <div class="rounded-2xl border border-zinc-200 bg-zinc-900 p-6 dark:border-zinc-800">
            <div v-for="a in apiContract" :key="a.fn" class="flex items-baseline justify-between gap-4 border-b border-zinc-800 py-3 last:border-b-0">
              <code class="font-mono text-[13px] text-emerald-300">{{ a.fn }}</code>
              <span class="shrink-0 text-xs text-zinc-400">{{ a.desc }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA 收尾 -->
    <section class="mx-auto max-w-7xl px-6 pb-24" v-reveal>
      <div class="flex flex-col items-start justify-between gap-6 rounded-2xl bg-accent px-8 py-12 text-white md:flex-row md:items-center">
        <div>
          <h2 class="text-2xl font-semibold tracking-tight md:text-3xl">下一次剁手之前，先问一句</h2>
          <p class="mt-2 max-w-[50ch] text-sm leading-relaxed text-blue-100">
            免登录、免安装，打开网页就能咨询。每一分钱怎么省，都摆在你眼前。
          </p>
        </div>
        <RouterLink
          to="/chat"
          class="inline-flex shrink-0 items-center gap-1.5 rounded-[10px] bg-white px-6 py-3 text-sm font-semibold text-accent-strong transition-transform active:scale-[0.98]"
        >
          <PhStack :size="15" weight="bold" />
          开始咨询
        </RouterLink>
      </div>
    </section>
  </div>
</template>
