<script setup>
import { RouterLink } from 'vue-router'
import { PhHouseSimple } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
</script>

<template>
  <div class="mx-auto flex max-w-6xl flex-col items-center px-6 py-28 text-center">
    <p class="font-mono text-[88px] font-bold leading-none tracking-tighter text-zinc-200 select-none dark:text-zinc-800" aria-hidden="true">
      404
    </p>
    <div class="-mt-8 flex items-center gap-2.5">
      <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-soft dark:bg-accent/20">
        <BrandIcon :size="18" />
      </span>
      <h1 class="text-xl font-semibold tracking-tight">这个页面没有上架</h1>
    </div>
    <p class="mt-3 max-w-[42ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">
      链接可能已失效或地址输入有误。回到首页继续咨询，比价、领券指引都在老地方。
    </p>
    <div class="mt-8 flex items-center gap-3">
      <RouterLink
        to="/"
        class="inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-5 py-3 text-sm font-medium text-white transition-transform hover:bg-accent-strong active:scale-[0.98]"
      >
        <PhHouseSimple :size="15" weight="bold" />
        回到首页
      </RouterLink>
      <RouterLink
        to="/chat"
        class="inline-flex items-center rounded-[10px] border border-zinc-300 px-5 py-3 text-sm font-medium text-zinc-700 transition-colors hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
      >
        开始咨询
      </RouterLink>
    </div>
  </div>
</template>
