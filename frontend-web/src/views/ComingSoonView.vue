<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { PhArrowLeft, PhChartPie, PhHeart, PhPackage } from '@phosphor-icons/vue'

const route = useRoute()

/**
 * v0.6 新增功能占位页：内容未开发，先给出入口与规划中的能力清单。
 * 各功能的能力点来自 设计方案 §4（心愿单 / 物品库 / 消费记录）。
 */
const FEATURES = {
  wishlist: {
    title: '心愿单与购买决策',
    desc: '把"想买"管理起来：收藏链接、记录预算与购买理由、设置冲动消费冷静期，让每个购买决定都经过思考。',
    icon: PhHeart,
    points: ['跨平台收藏', '购买优先级排序', '冲动消费冷静期', '替代关系分组', '购买理由回顾'],
  },
  items: {
    title: '个人物品库',
    desc: '买完以后软件仍然有用：为物品建立档案，保修、保养、耗材、重复购买一目了然。',
    icon: PhPackage,
    points: ['保修到期提醒', '维护提醒', '耗材匹配', '重复购买提示', '说明书助手', '闲置标记'],
  },
  spending: {
    title: '消费记录与预算',
    desc: '知道自己怎么买、花了多少：购物支出、类别占比、预算余额，购物前看预算、购物后做复盘。',
    icon: PhChartPie,
    points: ['本月购物支出', '类别占比', '预算余额', '购物前预算提示', '购物后复盘', '单次使用成本'],
  },
}

const feature = computed(() => FEATURES[route.name] ?? FEATURES.wishlist)
</script>

<template>
  <div class="mx-auto flex min-h-[calc(100dvh-64px)] max-w-3xl flex-col items-center justify-center px-6 py-16 text-center">
    <div class="flex h-20 w-20 items-center justify-center rounded-2xl bg-accent-soft dark:bg-accent/20">
      <component :is="feature.icon" :size="38" weight="duotone" class="text-accent-strong dark:text-blue-300" />
    </div>
    <span class="mt-6 rounded-md bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
      功能开发中 · 敬请期待
    </span>
    <h1 class="mt-4 text-2xl font-semibold tracking-tight md:text-3xl">{{ feature.title }}</h1>
    <p class="mt-3 max-w-[52ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">{{ feature.desc }}</p>

    <div class="mt-8 w-full rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 class="text-sm font-semibold text-zinc-500 dark:text-zinc-400">规划中的能力</h2>
      <ul class="mt-4 flex flex-wrap justify-center gap-2">
        <li
          v-for="p in feature.points"
          :key="p"
          class="rounded-[10px] border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[13px] text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-200"
        >
          {{ p }}
        </li>
      </ul>
    </div>

    <RouterLink
      to="/chat"
      class="mt-8 inline-flex items-center gap-2 rounded-[10px] bg-accent px-5 py-2.5 text-sm font-medium text-white transition-transform hover:bg-accent-strong active:scale-[0.98]"
    >
      <PhArrowLeft :size="16" />
      返回智能咨询
    </RouterLink>
  </div>
</template>
