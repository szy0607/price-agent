<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { PhCheck, PhCheckCircle, PhCopy, PhXCircle } from '@phosphor-icons/vue'
import { couponSteps, couponTypes, PLATFORMS, platformBenefits, platformCodes, products, cheapest } from '../mock/data'
import { copyText } from '../utils/copy'

const route = useRoute()
const fromProduct = products.find((p) => p.id === route.query.id)

const platTabs = [
  { key: 'taobao', label: '淘宝' },
  { key: 'jd', label: '京东' },
  { key: 'pdd', label: '拼多多' },
]
const activePlat = ref(fromProduct ? route.query.plat || 'taobao' : 'taobao')
const steps = computed(() => couponSteps[activePlat.value])
const benefits = computed(() => platformBenefits.filter((b) => b.platform === activePlat.value))
const platName = computed(() => PLATFORMS[activePlat.value].name)
const copied = ref(false)

const codePlat = computed(() => activePlat.value)

const codeObj = computed(() => {
  if (fromProduct) {
    const sku = cheapest(fromProduct, codePlat.value)
    return {
      code: sku.prices[codePlat.value].code,
      hint: `「${fromProduct.name}（${sku.name}）」的${PLATFORMS[codePlat.value].name}商品口令，复制后打开 App 自动跳转`,
    }
  }
  return platformCodes[codePlat.value]
})

async function copy() {
  const ok = await copyText(codeObj.value.code)
  copied.value = ok
  if (ok) window.setTimeout(() => (copied.value = false), 2000)
}

const nots = [
  '不代下单、不代支付，交易 100% 由你完成',
  '不提供 CPS 推广链接，只给领券路径',
  '不用评论区数据，晒单滞后且被刷单污染',
  '不承诺千人千面权益，天降红包以页面为准',
]
</script>

<template>
  <div class="mx-auto max-w-6xl px-6 py-10">
    <h1 class="text-2xl font-semibold tracking-tight md:text-3xl">领券指引</h1>
    <p class="mt-3 max-w-[62ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">
      这里只告诉你券的类型、限制和领取步骤。由你自己领券、自己下单，价格透明不误导。
    </p>

    <div class="mt-10 grid gap-6 lg:grid-cols-12">
      <!-- 左：分平台领券步骤 -->
      <div class="rounded-2xl border border-zinc-200 bg-white p-6 lg:col-span-7 dark:border-zinc-800 dark:bg-zinc-900" v-reveal>
        <div class="flex rounded-[10px] border border-zinc-200 p-1 dark:border-zinc-700">
          <button
            v-for="t in platTabs"
            :key="t.key"
            class="flex-1 rounded-lg px-4 py-1.5 text-sm transition-colors"
            :class="
              activePlat === t.key
                ? 'bg-accent font-medium text-white'
                : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
            "
            @click="activePlat = t.key"
          >
            {{ t.label }}
          </button>
        </div>
        <h2 class="mt-6 text-lg font-semibold tracking-tight">{{ platName }}领券步骤</h2>
        <ol class="mt-5 space-y-0">
          <li v-for="(s, i) in steps" :key="i" class="relative flex gap-4 pb-6 last:pb-0">
            <div v-if="i < steps.length - 1" class="absolute left-[13px] top-7 h-full w-px bg-zinc-200 dark:bg-zinc-700"></div>
            <span class="z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft font-mono text-xs font-semibold text-accent-strong dark:bg-accent/20 dark:text-blue-300">
              {{ i + 1 }}
            </span>
            <p class="pt-1 text-sm leading-relaxed">{{ s }}</p>
          </li>
        </ol>

        <!-- 复制口令：跨 App 跳转引导（设计稿 §3.3，复制口令为主） -->
        <div class="mt-8 rounded-2xl border border-zinc-200 bg-zinc-50/70 p-5 dark:border-zinc-800 dark:bg-zinc-800/30">
          <div class="text-sm font-semibold">复制口令，跳转{{ PLATFORMS[codePlat].name }} App</div>
          <p class="mt-1.5 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{{ codeObj.hint }}</p>
          <div class="mt-4 flex items-center gap-2.5">
            <code class="min-w-0 flex-1 truncate rounded-[10px] border border-zinc-200 bg-white px-3.5 py-2.5 font-mono text-[13px] text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200">
              {{ codeObj.code }}
            </code>
            <button
              class="inline-flex shrink-0 items-center gap-1.5 rounded-[10px] bg-accent px-4 py-2.5 text-sm font-medium text-white transition-transform enabled:hover:bg-accent-strong enabled:active:scale-[0.98]"
              @click="copy"
            >
              <PhCheck v-if="copied" :size="15" weight="bold" />
              <PhCopy v-else :size="15" />
              {{ copied ? '已复制' : '复制' }}
            </button>
          </div>
          <p class="mt-2.5 text-[11px] leading-relaxed text-zinc-400 dark:text-zinc-500">
            Demo 口令仅用于演示跳转，正式版由后端按联盟 API 数据生成；URL Scheme 作为备选方案。
          </p>
        </div>
      </div>

      <!-- 右：券类型 + 双价口径 -->
      <div class="flex flex-col gap-6 lg:col-span-5" v-reveal>
        <div
          v-for="t in couponTypes"
          :key="t.key"
          class="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"
        >
          <div
            class="text-sm font-semibold"
            :class="t.tone === 'green' ? 'text-price-b dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'"
          >
            {{ t.name }}
          </div>
          <p class="mt-2 text-[13px] leading-relaxed text-zinc-600 dark:text-zinc-300">{{ t.desc }}</p>
          <p class="mt-2 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">{{ t.rule }}</p>
        </div>
        <div class="rounded-2xl bg-zinc-900 p-5 text-sm leading-relaxed text-zinc-300 dark:bg-zinc-800/60">
          <p><span class="font-semibold text-red-400">价格 A（公开价）</span>：不领券直接买的价格，人人可得。</p>
          <p class="mt-2">
            <span class="font-semibold text-emerald-400">价格 B（领券价）</span>：领到券后的价格。渠道专享券领不到，就按 A 价买。
          </p>
        </div>
      </div>
    </div>

    <!-- 权益矩阵 -->
    <div class="mt-10 grid gap-6 lg:grid-cols-12" v-reveal>
      <div class="overflow-hidden rounded-2xl border border-zinc-200 bg-white lg:col-span-8 dark:border-zinc-800 dark:bg-zinc-900">
        <div class="border-b border-zinc-100 px-5 py-4 dark:border-zinc-800">
          <h2 class="text-lg font-semibold tracking-tight">{{ platName }}优惠类型怎么获取</h2>
        </div>
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-800/60 dark:text-zinc-400">
              <th class="px-5 py-2.5 font-medium">优惠类型</th>
              <th class="px-5 py-2.5 font-medium">来源</th>
              <th class="px-5 py-2.5 font-medium">获取方式</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-100 dark:divide-zinc-800">
            <tr v-for="b in benefits" :key="b.name">
              <td class="px-5 py-3">{{ b.name }}</td>
              <td class="px-5 py-3">
                <span
                  class="rounded-md px-1.5 py-0.5 text-[11px] font-medium"
                  :class="b.viaApi
                    ? 'bg-accent-soft text-accent-strong dark:bg-accent/20 dark:text-blue-300'
                    : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'"
                >
                  {{ b.viaApi ? 'API 实时' : 'RAG 指引' }}
                </span>
              </td>
              <td class="px-5 py-3 text-zinc-600 dark:text-zinc-300">{{ b.how }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 不做什么 -->
      <div class="rounded-2xl border border-zinc-200 bg-white p-5 lg:col-span-4 dark:border-zinc-800 dark:bg-zinc-900" v-reveal>
        <h2 class="text-lg font-semibold tracking-tight">我们不做什么</h2>
        <ul class="mt-4 space-y-3">
          <li v-for="n in nots" :key="n" class="flex gap-2.5 text-[13px] leading-relaxed text-zinc-600 dark:text-zinc-300">
            <PhXCircle :size="17" weight="fill" class="mt-0.5 shrink-0 text-red-500/80 dark:text-red-400/80" />
            {{ n }}
          </li>
        </ul>
        <div class="mt-5 flex items-center gap-2 border-t border-zinc-100 pt-4 text-[13px] text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
          <PhCheckCircle :size="17" weight="fill" class="shrink-0 text-price-b dark:text-emerald-400" />
          每个价格都标注来源，可回溯、可验证。
        </div>
      </div>
    </div>

    <p class="mt-8 text-xs leading-relaxed text-zinc-500 dark:text-zinc-400">
      券的面额、门槛、有效期与余量以平台实时数据为准，本指引不构成价格承诺。
    </p>
  </div>
</template>
