<script setup>
import { RouterLink, useRoute } from 'vue-router'
import { PhChatCircleDots, PhLightning } from '@phosphor-icons/vue'

const route = useRoute()
const links = [
  { to: '/chat', label: '智能咨询' },
  { to: '/compare', label: '款式对比' },
  { to: '/coupon', label: '领券指引' },
]
</script>

<template>
  <div class="flex min-h-dvh flex-col">
    <!-- 键盘用户跳过导航 -->
    <a
      href="#main"
      class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-[10px] focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
    >
      跳到主要内容
    </a>
    <!-- 顶部导航：单行，高 64px -->
    <header class="sticky top-0 z-40 border-b border-zinc-200/70 bg-zinc-50/85 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/85">
      <nav class="mx-auto flex h-16 max-w-6xl items-center gap-8 px-6">
        <RouterLink to="/" class="flex items-center gap-2.5">
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white">
            <PhChatCircleDots :size="18" weight="bold" />
          </span>
          <span class="text-[15px] font-semibold tracking-tight">智能导购 Agent</span>
        </RouterLink>
        <div class="ml-auto flex items-center gap-1">
          <RouterLink
            v-for="l in links"
            :key="l.to"
            :to="l.to"
            class="rounded-[10px] px-3.5 py-2 text-sm transition-colors"
            :class="
              route.path === l.to
                ? 'bg-accent-soft font-medium text-accent-strong dark:bg-accent/15 dark:text-blue-300'
                : 'text-zinc-600 hover:bg-zinc-200/60 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100'
            "
          >
            {{ l.label }}
          </RouterLink>
          <RouterLink
            to="/chat"
            class="ml-3 inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-4 py-2 text-sm font-medium text-white transition-transform hover:bg-accent-strong active:scale-[0.98]"
          >
            <PhLightning :size="15" weight="bold" />
            开始咨询
          </RouterLink>
        </div>
      </nav>
    </header>

    <main id="main" class="flex-1">
      <RouterView />
    </main>

    <footer class="border-t border-zinc-200/70 dark:border-zinc-800">
      <div class="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8 md:flex-row md:items-start md:justify-between">
        <div class="text-[13px] text-zinc-500 dark:text-zinc-400">
          <div class="flex items-center gap-2.5">
            <span class="flex h-6 w-6 items-center justify-center rounded-md bg-accent text-white">
              <PhChatCircleDots :size="13" weight="bold" />
            </span>
            <span class="font-medium text-zinc-700 dark:text-zinc-300">智能导购 Agent</span>
          </div>
          <p class="mt-2 max-w-[62ch] leading-relaxed">
            本工具仅提供信息聚合与决策建议：不代下单、不代支付、不提供推广链接。价格与券信息以平台页面实时展示为准。
          </p>
        </div>
        <nav class="flex items-center gap-5 text-[13px]" aria-label="页脚导航">
          <RouterLink v-for="l in links" :key="l.to" :to="l.to" class="text-zinc-500 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
            {{ l.label }}
          </RouterLink>
        </nav>
      </div>
    </footer>
  </div>
</template>
