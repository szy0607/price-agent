<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhArrowsLeftRight, PhChatCircleDots, PhCheckCircle, PhEye, PhEyeSlash, PhLightning, PhTag } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
import DualPriceCard from '../components/DualPriceCard.vue'
import { loginUser, registerUser } from '../utils/api'
import { bestPlat, products } from '../mock/data'
import { setAuthEmail } from '../utils/auth'

const router = useRouter()
const route = useRoute()
const mode = ref(route.query.mode === 'register' ? 'register' : 'login')
const form = ref({ user_email: '', username: '', password: '', confirmPassword: '' })
const showPassword = ref(false)
const pending = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const isRegister = computed(() => mode.value === 'register')
const showcaseProduct = products[0]
const showcasePlat = bestPlat(showcaseProduct).plat
const capabilities = [
  { icon: PhArrowsLeftRight, title: '一眼看懂款式差异', desc: '把关键规格、颜色与版本差异整理在同一张对比表里，减少来回切页面。' },
  { icon: PhTag, title: '公开价与领券价同时算', desc: '不只报一个低价，公开价、券后价和券的限制条件一起展示。' },
  { icon: PhChatCircleDots, title: '用一句话开始咨询', desc: '粘贴商品链接，或直接说出预算和需求，Agent 会继续追问并给出建议。' },
]

function switchMode(nextMode) {
  mode.value = nextMode
  errorMessage.value = ''
  successMessage.value = ''
  const redirect = route.query.redirect
  router.replace({ query: { ...(nextMode === 'register' ? { mode: 'register' } : {}), ...(redirect ? { redirect } : {}) } })
}

async function submit() {
  errorMessage.value = ''
  successMessage.value = ''
  const email = form.value.user_email.trim()
  const password = form.value.password

  if (!email || !password || (isRegister.value && !form.value.username.trim())) {
    errorMessage.value = '请填写完整信息'
    return
  }
  if (isRegister.value && password !== form.value.confirmPassword) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }

  pending.value = true
  try {
    if (isRegister.value) {
      await registerUser({ user_email: email, username: form.value.username.trim(), password })
      successMessage.value = '注册成功，请使用新账号登录'
      form.value.password = ''
      form.value.confirmPassword = ''
      switchMode('login')
      successMessage.value = '注册成功，请使用新账号登录'
    } else {
      await loginUser({ user_email: email, password })
      setAuthEmail(email)
      successMessage.value = '登录成功'
      setTimeout(() => router.push(route.query.redirect || '/chat'), 450)
    }
  } catch (error) {
    errorMessage.value = error.message || '请求失败，请稍后重试'
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div>
    <section class="mx-auto grid min-h-[calc(100dvh-64px)] max-w-6xl items-center gap-12 px-6 py-16 lg:grid-cols-[1fr_420px]">
      <div class="hidden lg:block">
      <div class="mb-6 flex items-center gap-3 text-sm font-medium text-accent">
        <BrandIcon :size="20" />
        智能导购 Agent
      </div>
      <h1 class="max-w-[12ch] text-5xl font-bold leading-[1.1] tracking-tighter">先登录，再让选择更简单。</h1>
      <p class="mt-6 max-w-[42ch] text-base leading-relaxed text-zinc-600 dark:text-zinc-400">
        登录后可以继续你的咨询流程。我们只使用必要的账号信息，不碰支付，也不代替你下单。
      </p>
      </div>

      <section class="rounded-2xl border border-zinc-200 bg-white p-7 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 sm:p-9">
      <button type="button" class="mb-7 inline-flex items-center gap-1.5 text-sm text-zinc-500 transition-colors hover:text-zinc-900 dark:hover:text-zinc-100" @click="router.back()">
        <PhArrowLeft :size="15" /> 返回
      </button>
      <div class="flex items-center gap-2.5 lg:hidden">
        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-soft dark:bg-accent/20"><BrandIcon :size="20" /></span>
        <span class="font-semibold">智能导购 Agent</span>
      </div>
      <h2 class="mt-7 text-2xl font-semibold tracking-tight lg:mt-0">{{ isRegister ? '创建账号' : '欢迎回来' }}</h2>
      <p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{{ isRegister ? '注册后即可保存你的咨询偏好。' : '登录以继续你的购物咨询。' }}</p>

      <div class="mt-7 grid grid-cols-2 rounded-lg bg-zinc-100 p-1 dark:bg-zinc-800" role="tablist">
        <button type="button" class="rounded-md py-2 text-sm font-medium transition-colors" :class="!isRegister ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white' : 'text-zinc-500'" @click="switchMode('login')">登录</button>
        <button type="button" class="rounded-md py-2 text-sm font-medium transition-colors" :class="isRegister ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white' : 'text-zinc-500'" @click="switchMode('register')">注册</button>
      </div>

      <form class="mt-7 space-y-4" @submit.prevent="submit">
        <label v-if="isRegister" class="block text-sm font-medium">用户名
          <input v-model="form.username" type="text" autocomplete="username" maxlength="50" class="mt-1.5 w-full rounded-[10px] border border-zinc-300 bg-transparent px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-accent dark:border-zinc-700" placeholder="怎么称呼你" />
        </label>
        <label class="block text-sm font-medium">邮箱
          <input v-model="form.user_email" type="email" autocomplete="email" class="mt-1.5 w-full rounded-[10px] border border-zinc-300 bg-transparent px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-accent dark:border-zinc-700" placeholder="you@example.com" />
        </label>
        <label class="block text-sm font-medium">密码
          <span class="relative mt-1.5 block">
            <input v-model="form.password" :type="showPassword ? 'text' : 'password'" :autocomplete="isRegister ? 'new-password' : 'current-password'" class="w-full rounded-[10px] border border-zinc-300 bg-transparent px-3.5 py-2.5 pr-11 text-sm outline-none transition-colors focus:border-accent dark:border-zinc-700" placeholder="6–18 位，含字母和数字" />
            <button type="button" class="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
              <PhEyeSlash v-if="showPassword" :size="18" /><PhEye v-else :size="18" />
            </button>
          </span>
        </label>
        <label v-if="isRegister" class="block text-sm font-medium">确认密码
          <input v-model="form.confirmPassword" type="password" autocomplete="new-password" class="mt-1.5 w-full rounded-[10px] border border-zinc-300 bg-transparent px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-accent dark:border-zinc-700" placeholder="再次输入密码" />
        </label>

        <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-700 dark:bg-red-400/10 dark:text-red-300" role="alert">{{ errorMessage }}</p>
        <p v-if="successMessage" class="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300" role="status"><PhCheckCircle :size="17" />{{ successMessage }}</p>
        <button type="submit" :disabled="pending" class="inline-flex w-full items-center justify-center gap-2 rounded-[10px] bg-accent px-4 py-3 text-sm font-medium text-white transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-60">
          <PhLightning :size="16" weight="bold" />{{ pending ? '提交中…' : (isRegister ? '创建账号' : '登录') }}
        </button>
      </form>
      </section>
    </section>

    <section class="border-y border-zinc-200/70 bg-white dark:border-zinc-800 dark:bg-zinc-900/40">
      <div class="mx-auto max-w-6xl px-6 py-16 sm:py-20">
        <div class="max-w-[46ch]">
          <p class="text-sm font-medium text-accent">登录后，你会得到什么</p>
          <h2 class="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">把购物前的犹豫，变成可比较的信息。</h2>
          <p class="mt-4 text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">先浏览下面的工作方式，再决定要不要开始咨询。每一步都由你确认，不代下单，不代支付。</p>
        </div>
        <div class="mt-12 grid gap-5 md:grid-cols-3">
          <article v-for="item in capabilities" :key="item.title" class="border-t border-zinc-200 pt-5 dark:border-zinc-700">
            <component :is="item.icon" :size="24" class="text-accent" />
            <h3 class="mt-4 text-base font-semibold">{{ item.title }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{{ item.desc }}</p>
          </article>
        </div>
      </div>
    </section>

    <section class="mx-auto grid max-w-6xl items-center gap-10 px-6 py-16 sm:py-20 lg:grid-cols-[0.85fr_1fr]">
      <div>
        <p class="text-sm font-medium text-accent">先看结果长什么样</p>
        <h2 class="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">价格不藏在结论里。</h2>
        <p class="mt-4 max-w-[43ch] text-[15px] leading-relaxed text-zinc-600 dark:text-zinc-400">同一款商品的公开价、领券价和平台差异会被拆开说明。登录后，你可以继续追问预算、偏好和使用场景。</p>
        <button type="button" class="mt-7 inline-flex items-center gap-1.5 rounded-[10px] bg-accent px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-accent-strong" @click="document.querySelector('form input')?.focus()">现在登录，开始咨询 <PhLightning :size="15" weight="bold" /></button>
      </div>
      <div class="mx-auto w-full max-w-md" v-reveal>
        <DualPriceCard :product="showcaseProduct" :plat="showcasePlat" />
      </div>
    </section>
  </div>
</template>
