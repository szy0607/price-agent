<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { PhChartPie, PhChatCircleDots, PhGearSix, PhLightning, PhPackage, PhSignOut, PhShoppingCart } from '@phosphor-icons/vue'
import BrandIcon from './components/BrandIcon.vue'
import { isAuthenticated, refreshAuth, signOut as logoutCurrentUser } from './utils/auth'

const route = useRoute()
const router = useRouter()
const authenticated = ref(isAuthenticated())
const signingOut = ref(false)
const showFunctionalNav = computed(() => route.name !== 'auth' && authenticated.value)
const isAuthPage = computed(() => route.name === 'auth')
const brandTarget = computed(() => (authenticated.value ? '/chat' : '/auth'))
const syncAuth = () => { authenticated.value = isAuthenticated() }
onMounted(() => {
  window.addEventListener('price-agent-auth-changed', syncAuth)
  refreshAuth()
})
onBeforeUnmount(() => {
  window.removeEventListener('price-agent-auth-changed', syncAuth)
})
const links = [
  { to: '/chat', label: '智能咨询', icon: PhChatCircleDots },
  { to: '/cart', label: '购物车', icon: PhShoppingCart },
  { to: '/items', label: '物品库', icon: PhPackage },
  { to: '/spending', label: '消费记录', icon: PhChartPie },
  { to: '/settings', label: '设置', icon: PhGearSix },
]

async function handleSignOut() {
  if (signingOut.value) return
  signingOut.value = true
  try {
    await logoutCurrentUser()
  } catch {
    // signOut 会在请求失败时也清理本地状态。
  } finally {
    signingOut.value = false
    await router.replace('/auth')
  }
}
</script>

<template>
  <div class="app-shell flex min-h-dvh flex-col md:flex-row">
    <!-- 键盘用户跳过导航 -->
    <a
      href="#main"
      class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-[10px] focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
    >
      跳到主要内容
    </a>
    <header v-if="!isAuthPage" class="app-sidebar z-40 border-b border-zinc-200/80 bg-white/90 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/90 md:fixed md:inset-y-0 md:left-0 md:flex md:w-[250px] md:flex-col md:border-b-0 md:border-r">
      <nav class="app-sidebar__nav mx-auto flex min-h-[4.25rem] w-full items-center gap-3 px-4 py-3 md:flex-1 md:flex-col md:items-stretch md:px-4 md:py-7">
        <RouterLink :to="brandTarget" class="app-header__brand group flex shrink-0 items-center gap-3 rounded-xl px-2 py-1.5 transition-colors hover:bg-white/80 dark:hover:bg-zinc-900/80">
          <span class="app-header__mark flex h-9 w-9 items-center justify-center rounded-xl border border-blue-100 bg-blue-50 shadow-[0_4px_14px_-8px_rgba(37,99,235,.7)] transition-transform group-hover:scale-[1.04] dark:border-blue-900/60 dark:bg-blue-950/60">
            <BrandIcon :size="21" />
          </span>
          <span class="app-header__wordmark text-[15px] font-semibold tracking-tight text-zinc-900 max-[380px]:hidden dark:text-zinc-100"><small>SHOP INTELLIGENCE</small><b>PRICE AGENT</b></span>
        </RouterLink>
        <div v-if="showFunctionalNav" class="app-header__links ml-auto flex min-w-0 items-center justify-end gap-1 overflow-x-auto md:ml-0 md:mt-12 md:flex-col md:items-stretch md:gap-2 md:overflow-visible md:rounded-none md:border-0 md:bg-transparent md:p-0 md:shadow-none">
          <RouterLink
            v-for="l in links"
            :key="l.to"
            :to="l.to"
            :title="l.label"
            :aria-label="l.label"
            class="inline-flex h-9 min-w-9 shrink-0 items-center justify-center rounded-xl px-2 text-sm transition-all sm:h-auto sm:min-w-0 sm:px-3.5 sm:py-2 md:justify-start md:gap-3 md:px-3 md:py-3"
            :class="
              route.path === l.to
                ? 'bg-blue-50 font-medium text-blue-700 shadow-sm dark:bg-blue-950/70 dark:text-blue-300'
                : 'text-zinc-600 hover:bg-zinc-200/60 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100'
            "
          >
            <component :is="l.icon" :size="18" />
            <span class="hidden sm:inline">{{ l.label }}</span>
          </RouterLink>
          <RouterLink
            to="/chat"
            class="app-header__cta ml-1 inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-accent px-3 py-2 text-sm font-medium text-white shadow-[0_6px_16px_-8px_rgba(37,99,235,.9)] transition-transform hover:bg-accent-strong active:scale-[0.98] sm:ml-3 sm:px-4 md:ml-0 md:mt-4 md:justify-center md:py-3"
          >
            <PhLightning :size="15" weight="bold" />
            <span class="max-[430px]:hidden">开始咨询</span>
          </RouterLink>
          <button
            type="button"
            title="退出登录"
            aria-label="退出登录"
            :disabled="signingOut"
            class="inline-flex h-9 min-w-9 shrink-0 items-center justify-center rounded-xl text-zinc-500 transition-colors hover:bg-zinc-200/60 hover:text-zinc-900 disabled:opacity-50 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100 md:mt-auto md:w-full md:justify-start md:gap-3 md:px-3"
            @click="handleSignOut"
          >
            <PhSignOut :size="18" />
          </button>
        </div>
        <RouterLink
          v-else-if="!isAuthPage"
          to="/auth"
          class="ml-auto shrink-0 rounded-[10px] px-3.5 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent-soft dark:hover:bg-accent/15"
        >
          登录
        </RouterLink>
      </nav>
    </header>

    <main id="main" class="min-w-0 flex-1" :class="showFunctionalNav ? 'md:ml-[250px]' : ''">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <footer v-if="route.path !== '/chat' && !isAuthPage" class="border-t border-zinc-200/70 dark:border-zinc-800 md:ml-[250px]">
      <div class="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8 md:flex-row md:items-start md:justify-between">
        <div class="text-[13px] text-zinc-500 dark:text-zinc-400">
          <div class="flex items-center gap-2.5">
            <span class="flex h-6 w-6 items-center justify-center rounded-md bg-accent-soft dark:bg-accent/20">
              <BrandIcon :size="16" />
            </span>
            <span class="font-medium text-zinc-700 dark:text-zinc-300">智能导购 Agent</span>
          </div>
          <p class="mt-2 max-w-[62ch] leading-relaxed">
            本工具仅提供信息聚合与决策建议：不代下单、不代支付、不提供推广链接。价格与券信息以平台页面实时展示为准。
          </p>
        </div>
        <nav v-if="showFunctionalNav" class="flex items-center gap-5 text-[13px]" aria-label="页脚导航">
          <RouterLink v-for="l in links" :key="l.to" :to="l.to" class="text-zinc-500 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
            {{ l.label }}
          </RouterLink>
        </nav>
      </div>
    </footer>
  </div>
</template>
