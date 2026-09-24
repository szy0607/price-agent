<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhArrowsLeftRight, PhChatCircleDots, PhCheckCircle, PhEye, PhEyeSlash, PhLightning, PhTag } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
import { loginUser, registerUser } from '../utils/api'
import { bestPlat, cheapest, PLATFORMS, PLAT_KEYS, products } from '../mock/data'
import { setAuthEmail } from '../utils/auth'

const router = useRouter()
const route = useRoute()
const loginBg = `${import.meta.env.BASE_URL}images/login-bg.jpg`
const mode = ref(route.query.mode === 'register' ? 'register' : 'login')
const form = ref({ user_email: '', username: '', password: '', confirmPassword: '' })
const showPassword = ref(false)
const pending = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const isRegister = computed(() => mode.value === 'register')
const showcaseProduct = products[0]
const showcaseBest = bestPlat(showcaseProduct)
const showcasePlat = showcaseBest.plat
const showcaseRecommendation = `目前券后价最低的是${PLATFORMS[showcasePlat].name}（¥${showcaseBest.price}），下单前请确认优惠条件和页面实时价格。`
const showcasePriceSummary = PLAT_KEYS.map((platform) => `${PLATFORMS[platform].name} ¥${cheapest(showcaseProduct, platform).prices[platform].b}`).join(' · ')
const responseSteps = [
  { agent: 'A1', icon: PhChatCircleDots, title: '拆解需求', detail: '预算不超过 ¥3,000，通勤使用，优先关注降噪体验。' },
  { agent: 'A2', icon: PhArrowsLeftRight, title: '匹配商品与款式', detail: `找到「${showcaseProduct.name}」，核对颜色、版本与核心规格。` },
  { agent: 'A3', icon: PhTag, title: '核对平台价格', detail: `读取活动和券后价：${showcasePriceSummary}。` },
  { agent: 'A5', icon: PhLightning, title: '整理推荐依据', detail: `当前${PLATFORMS[showcasePlat].name}报价更低，并标明需要确认的优惠条件。` },
]
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

function focusLoginForm() {
  const formSection = document.getElementById('auth-form-section')
  formSection?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  window.setTimeout(() => formSection?.querySelector('input')?.focus(), 350)
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
  <div class="auth-page">
    <section class="auth-hero relative isolate">
      <div aria-hidden="true" class="auth-hero__image" :style="{ backgroundImage: `url(${loginBg})` }"></div>
      <div aria-hidden="true" class="auth-hero__wash"></div>
      <div class="auth-hero__layout mx-auto grid max-w-[1480px] items-center gap-x-20 gap-y-12 px-5 pb-16 pt-24 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(390px,0.72fr)] lg:px-12 lg:pb-20">
        <div class="auth-hero__intro lg:col-start-1 lg:row-start-1">
          <p class="mb-5 text-sm font-semibold text-accent">购物之前，先把差异看清楚</p>
          <h1 class="text-4xl font-bold leading-[1.08] text-zinc-950 sm:text-5xl lg:text-6xl dark:text-white">好选择，<br /><span class="text-accent">从看懂价格开始。</span></h1>
          <p class="mt-6 max-w-[48ch] text-base leading-7 text-zinc-700 dark:text-zinc-200">
            横向比较商品款式与平台到手价。登录后继续咨询，让每个决定都有依据。
          </p>
        </div>

        <section id="auth-form-section" class="auth-form-panel lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <button type="button" class="mb-8 inline-flex items-center gap-1.5 text-sm text-zinc-500 transition-colors hover:text-zinc-900 dark:hover:text-zinc-100" @click="router.back()">
            <PhArrowLeft :size="15" /> 返回
          </button>
          <div class="flex items-end justify-between gap-4">
            <div>
              <h2 class="text-2xl font-semibold text-zinc-950 dark:text-white">{{ isRegister ? '创建你的账号' : '欢迎回来' }}</h2>
              <p class="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{{ isRegister ? '注册后即可开始你的购物咨询。' : '登录后继续你的购物咨询。' }}</p>
            </div>
          </div>

          <div class="mt-7 grid grid-cols-2 border-b border-zinc-200 dark:border-zinc-700" role="tablist">
            <button type="button" class="auth-tab" :class="!isRegister && 'auth-tab--active'" @click="switchMode('login')">登录</button>
            <button type="button" class="auth-tab" :class="isRegister && 'auth-tab--active'" @click="switchMode('register')">注册</button>
          </div>

          <form class="mt-7 space-y-5" @submit.prevent="submit">
            <label v-if="isRegister" class="auth-label">用户名
              <input v-model="form.username" type="text" autocomplete="username" maxlength="50" class="auth-input" placeholder="怎么称呼你" />
            </label>
            <label class="auth-label">邮箱
              <input v-model="form.user_email" type="email" autocomplete="email" class="auth-input" placeholder="you@example.com" />
            </label>
            <label class="auth-label">密码
              <span class="relative mt-2 block">
                <input v-model="form.password" :type="showPassword ? 'text' : 'password'" :autocomplete="isRegister ? 'new-password' : 'current-password'" class="auth-input pr-12" placeholder="6–18 位，含字母和数字" />
                <button type="button" class="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-zinc-400 transition-colors hover:text-zinc-800 dark:hover:text-zinc-100" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">
                  <PhEyeSlash v-if="showPassword" :size="19" /><PhEye v-else :size="19" />
                </button>
              </span>
            </label>
            <label v-if="isRegister" class="auth-label">确认密码
              <input v-model="form.confirmPassword" type="password" autocomplete="new-password" class="auth-input" placeholder="再次输入密码" />
            </label>

            <p v-if="errorMessage" class="rounded-lg bg-red-50 px-3.5 py-3 text-sm text-red-700 dark:bg-red-400/10 dark:text-red-300" role="alert">{{ errorMessage }}</p>
            <p v-if="successMessage" class="flex items-center gap-2 rounded-lg bg-emerald-50 px-3.5 py-3 text-sm text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300" role="status"><PhCheckCircle :size="17" />{{ successMessage }}</p>
            <button type="submit" :disabled="pending" class="auth-submit">
              <PhLightning :size="16" weight="bold" />{{ pending ? '提交中…' : (isRegister ? '创建账号' : '登录，继续咨询') }}
            </button>
          </form>
          <p class="mt-5 text-center text-xs leading-5 text-zinc-500 dark:text-zinc-400">不代下单、不代支付，你始终掌握最后决定。</p>
        </section>

        <div class="auth-reasoning-stage lg:col-start-1 lg:row-start-2" v-reveal="100">
          <div class="auth-question">
            <span class="auth-question__icon"><PhChatCircleDots :size="17" /></span>
            <div class="min-w-0">
              <p class="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">用户提问</p>
              <p class="mt-1 text-sm font-medium leading-5 text-zinc-800 dark:text-zinc-100">3000 以内推荐降噪耳机，我通勤用</p>
            </div>
          </div>

          <div class="auth-reasoning-flow">
            <article v-for="step in responseSteps" :key="step.agent" class="auth-reasoning-step">
              <span class="auth-reasoning-step__marker"><component :is="step.icon" :size="15" weight="bold" /></span>
              <div class="min-w-0 pt-0.5">
                <h3 class="flex items-center gap-2 text-[13px] font-semibold text-zinc-900 dark:text-zinc-100">
                  <span class="font-mono text-[10px] font-medium text-zinc-400">{{ step.agent }}</span>
                  {{ step.title }}
                </h3>
                <p class="mt-1 text-xs leading-5 text-zinc-600 dark:text-zinc-400">{{ step.detail }}</p>
              </div>
            </article>
          </div>

          <div class="auth-reasoning-answer">
            <PhCheckCircle :size="18" weight="fill" class="mt-0.5 shrink-0 text-price-b dark:text-emerald-400" />
            <div>
              <p class="text-xs font-semibold text-zinc-900 dark:text-zinc-100">建议摘要</p>
              <p class="mt-1 text-xs leading-5 text-zinc-600 dark:text-zinc-400">{{ showcaseRecommendation }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="auth-capabilities">
      <div class="mx-auto grid max-w-[1320px] gap-12 px-5 py-20 sm:px-8 md:py-28 lg:grid-cols-[minmax(280px,0.72fr)_minmax(0,1fr)] lg:gap-24 lg:px-12">
        <div class="max-w-[42ch]">
          <p class="text-sm font-semibold text-accent">登录后，你会得到什么</p>
          <h2 class="mt-4 text-3xl font-semibold leading-tight text-zinc-950 sm:text-4xl dark:text-white">把购物前的犹豫，变成可比较的信息。</h2>
          <p class="mt-5 text-[15px] leading-7 text-zinc-600 dark:text-zinc-400">比较的不止是一个数字，还包括款式差异、领券条件和购买限制。</p>
        </div>
        <div class="divide-y divide-zinc-200 dark:divide-zinc-800">
          <article v-for="(item, index) in capabilities" :key="item.title" class="grid gap-4 py-6 first:pt-0 last:pb-0 sm:grid-cols-[48px_1fr] sm:gap-6">
            <component :is="item.icon" :size="25" class="mt-1 text-accent" />
            <div>
              <h3 class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{{ item.title }}</h3>
              <p class="mt-2 max-w-[60ch] text-sm leading-6 text-zinc-600 dark:text-zinc-400">{{ item.desc }}</p>
            </div>
          </article>
        </div>
      </div>
    </section>

    <section class="auth-conversation">
      <div class="mx-auto grid max-w-[1320px] items-center gap-12 px-5 py-20 sm:px-8 md:py-28 lg:grid-cols-[minmax(280px,0.7fr)_minmax(0,1fr)] lg:gap-24 lg:px-12">
        <div class="max-w-[44ch]">
          <p class="text-sm font-semibold text-accent">从你的问题开始</p>
          <h2 class="mt-4 text-3xl font-semibold leading-tight text-zinc-950 sm:text-4xl dark:text-white">把需求说清楚，答案也会更贴近你。</h2>
          <p class="mt-5 text-[15px] leading-7 text-zinc-600 dark:text-zinc-400">预算、使用场景、偏好平台，都可以直接告诉智能导购。它会整理商品和价格情报，再解释推荐理由。</p>
          <button type="button" class="auth-secondary-action" @click="focusLoginForm">现在登录，开始咨询 <PhLightning :size="15" weight="bold" /></button>
        </div>
        <div class="auth-chat-preview" v-reveal="120">
          <div class="flex justify-end">
            <div class="max-w-[80%] rounded-2xl rounded-br-md bg-accent px-4 py-3 text-sm leading-6 text-white">3000 以内推荐降噪耳机，我通勤用</div>
          </div>
          <div class="mt-5 flex gap-3">
            <span class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft dark:bg-accent/20"><BrandIcon :size="17" /></span>
            <div class="min-w-0 flex-1">
              <p class="text-sm leading-6 text-zinc-600 dark:text-zinc-300">我整理了这款耳机的款式与平台价格。{{ showcaseRecommendation }}</p>
              <div class="mt-5 grid gap-4 border-t border-zinc-200 pt-4 dark:border-zinc-700 sm:grid-cols-[72px_1fr]">
                <img :src="showcaseProduct.image" :alt="showcaseProduct.name" class="h-[72px] w-[72px] rounded-xl bg-white object-contain" />
                <div class="min-w-0 self-center">
                  <p class="text-sm font-semibold text-zinc-900 dark:text-white">{{ showcaseProduct.name }}</p>
                  <p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{{ showcaseProduct.brand }} · 3 个款式</p>
                  <div class="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-600 dark:text-zinc-300">
                    <span v-for="pk in PLAT_KEYS" :key="pk">{{ PLATFORMS[pk].name }} <span class="font-mono tabular-nums">¥{{ cheapest(showcaseProduct, pk).prices[pk].b }}</span></span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="auth-products">
      <div class="mx-auto max-w-[1320px] px-5 py-20 sm:px-8 md:py-28 lg:px-12">
        <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.7fr)] lg:items-end">
          <div class="max-w-[48ch]">
            <p class="text-sm font-semibold text-accent">真实商品，真实比较方式</p>
            <h2 class="mt-4 text-3xl font-semibold leading-tight text-zinc-950 sm:text-4xl dark:text-white">同一件商品，三个平台同时看。</h2>
          </div>
          <p class="max-w-[46ch] text-sm leading-6 text-zinc-600 lg:justify-self-end dark:text-zinc-400">公开价、券后价与平台活动并排展示，具体款式和限制也会一并说明。</p>
        </div>
        <div class="auth-product-gallery mt-12">
          <article v-for="(p, index) in products" :key="p.id" class="auth-product-item" :class="{ 'auth-product-item--feature': index === 0 }">
            <div class="auth-product-item__image">
              <img :src="p.image" :alt="p.name" loading="lazy" />
            </div>
            <div class="auth-product-item__body">
              <div class="min-w-0">
                <p class="text-xs text-zinc-500 dark:text-zinc-400">{{ p.brand }} · {{ p.category }}</p>
                <h3 class="mt-1 truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">{{ p.name }}</h3>
              </div>
              <div class="mt-4 space-y-2.5">
                <div v-for="pk in PLAT_KEYS" :key="pk" class="flex items-center justify-between gap-3 text-[13px]">
                  <span class="text-zinc-500 dark:text-zinc-400">{{ PLATFORMS[pk].name }}</span>
                  <span class="font-mono tabular-nums" :class="bestPlat(p).plat === pk ? 'font-semibold text-price-b dark:text-emerald-400' : 'text-zinc-700 dark:text-zinc-300'">¥{{ cheapest(p, pk).prices[pk].b }}</span>
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.auth-hero {
  min-height: 100dvh;
  overflow: hidden;
  background: #f4f7fc;
}

.auth-hero__image,
.auth-hero__wash {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.auth-hero__image {
  z-index: -2;
  background-position: center 42%;
  background-size: cover;
  transform: scale(1.015);
}

.auth-hero__wash {
  z-index: -1;
  background:
    linear-gradient(90deg, rgb(248 250 253 / 0.28) 0%, rgb(248 250 253 / 0.55) 54%, rgb(248 250 253 / 0.78) 100%),
    linear-gradient(180deg, rgb(248 250 253 / 0.18), rgb(248 250 253 / 0.76));
}

.auth-hero__layout {
  min-height: 100dvh;
}

.auth-form-panel {
  width: 100%;
  max-width: 490px;
  justify-self: end;
  padding: clamp(1.5rem, 3vw, 2.75rem);
  border: 1px solid rgb(255 255 255 / 0.88);
  border-radius: 20px;
  background: rgb(255 255 255 / 0.91);
  box-shadow: 0 28px 80px rgb(36 67 120 / 0.14), 0 2px 8px rgb(36 67 120 / 0.06);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
}

.auth-tab {
  position: relative;
  min-height: 46px;
  color: #71717a;
  font-size: 0.875rem;
  font-weight: 500;
  transition: color 180ms ease;
}

.auth-tab:hover,
.auth-tab--active {
  color: #1d4ed8;
}

.auth-tab--active::after {
  position: absolute;
  right: 18%;
  bottom: -1px;
  left: 18%;
  height: 2px;
  background: #2563eb;
  content: '';
}

.auth-label {
  display: block;
  color: #3f3f46;
  font-size: 0.8125rem;
  font-weight: 600;
}

.auth-input {
  display: block;
  width: 100%;
  height: 48px;
  margin-top: 0.5rem;
  border: 1px solid #d4d4d8;
  border-radius: 10px;
  background: rgb(255 255 255 / 0.76);
  padding: 0 0.875rem;
  color: #18181b;
  font-size: 0.875rem;
  outline: none;
  transition: border-color 180ms ease, box-shadow 180ms ease, background-color 180ms ease;
}

.auth-input::placeholder {
  color: #a1a1aa;
}

.auth-input:focus {
  border-color: #2563eb;
  background: #fff;
  box-shadow: 0 0 0 3px rgb(37 99 235 / 0.12);
}

.auth-submit,
.auth-secondary-action {
  display: inline-flex;
  min-height: 48px;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  transition: background-color 180ms ease, transform 180ms ease, box-shadow 180ms ease;
}

.auth-submit {
  width: 100%;
  margin-top: 0.25rem;
  background: #2563eb;
  color: #fff;
  box-shadow: 0 8px 18px rgb(37 99 235 / 0.2);
}

.auth-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  background: #1d4ed8;
  box-shadow: 0 12px 22px rgb(37 99 235 / 0.24);
}

.auth-submit:active:not(:disabled),
.auth-secondary-action:active {
  transform: scale(0.985);
}

.auth-submit:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.auth-reasoning-stage {
  width: 100%;
  max-width: 760px;
  padding: 1.25rem 1.5rem 1.125rem;
  border: 1px solid rgb(255 255 255 / 0.74);
  border-radius: 16px;
  background: rgb(255 255 255 / 0.52);
  box-shadow: 0 18px 52px rgb(36 67 120 / 0.07);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.auth-question {
  display: grid;
  align-items: center;
  gap: 0.75rem;
  grid-template-columns: 34px minmax(0, 1fr);
  padding-bottom: 1rem;
  border-bottom: 1px solid rgb(113 113 122 / 0.16);
}

.auth-question__icon {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 9px;
  background: rgb(37 99 235 / 0.1);
  color: #2563eb;
}

.auth-reasoning-flow {
  padding: 1rem 0 0.15rem;
}

.auth-reasoning-step {
  position: relative;
  display: grid;
  gap: 0.75rem;
  grid-template-columns: 30px minmax(0, 1fr);
  padding-bottom: 0.875rem;
}

.auth-reasoning-step:last-child {
  padding-bottom: 0.25rem;
}

.auth-reasoning-step:not(:last-child)::after {
  position: absolute;
  top: 27px;
  bottom: 0;
  left: 13px;
  width: 1px;
  background: rgb(113 113 122 / 0.24);
  content: '';
}

.auth-reasoning-step__marker {
  position: relative;
  z-index: 1;
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid rgb(37 99 235 / 0.18);
  border-radius: 8px;
  background: rgb(255 255 255 / 0.88);
  color: #2563eb;
}

.auth-reasoning-answer {
  display: flex;
  gap: 0.65rem;
  margin-top: 0.75rem;
  padding-top: 0.875rem;
  border-top: 1px solid rgb(113 113 122 / 0.16);
}

.auth-capabilities {
  border-bottom: 1px solid rgb(228 228 231 / 0.8);
  background: #fff;
}

.auth-conversation {
  background: #f3f6fb;
}

.auth-chat-preview {
  padding: clamp(1.25rem, 3.5vw, 2.5rem);
  border: 1px solid rgb(212 221 235 / 0.9);
  border-radius: 18px;
  background: rgb(255 255 255 / 0.86);
  box-shadow: 0 20px 55px rgb(38 65 106 / 0.08);
}

.auth-products {
  background: #fff;
}

.auth-product-gallery {
  display: grid;
  gap: 1.25rem 2.5rem;
  grid-template-columns: minmax(0, 1.16fr) minmax(0, 0.84fr);
  grid-template-rows: repeat(2, minmax(155px, auto));
}

.auth-product-item {
  display: grid;
  align-items: center;
  gap: 1rem;
  grid-template-columns: 112px minmax(0, 1fr);
  min-width: 0;
  padding: 1rem 0;
  border-bottom: 1px solid #e4e4e7;
}

.auth-product-item--feature {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  align-items: stretch;
  grid-row: span 2;
  padding: 0;
  overflow: hidden;
  border: 1px solid #e4e4e7;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 16px 45px rgb(38 65 106 / 0.07);
}

.auth-product-item__image {
  display: grid;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  place-items: center;
  background: #f1f5f9;
}

.auth-product-item__image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  mix-blend-mode: multiply;
  transition: transform 350ms ease;
}

.auth-product-item:hover .auth-product-item__image img {
  transform: scale(1.035);
}

.auth-product-item--feature .auth-product-item__image {
  flex: 1;
  min-height: 270px;
  aspect-ratio: 1.45;
}

.auth-product-item__body {
  min-width: 0;
  padding: 1rem 1.125rem;
}

.auth-product-item--feature .auth-product-item__body {
  display: grid;
  align-items: start;
  gap: 1.25rem;
  grid-template-columns: minmax(0, 1fr) minmax(130px, 0.7fr);
  padding: 1.25rem 1.5rem 1.5rem;
}

@media (max-width: 1023px) {
  .auth-hero__layout {
    min-height: auto;
  }

  .auth-form-panel {
    justify-self: stretch;
    max-width: none;
  }

}

@media (max-width: 639px) {
  .auth-hero__wash {
    background: linear-gradient(180deg, rgb(248 250 253 / 0.52), rgb(248 250 253 / 0.88));
  }

  .auth-reasoning-stage {
    padding: 1rem;
  }

  .auth-product-gallery {
    gap: 1rem;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto;
  }

  .auth-product-item--feature {
    grid-row: auto;
  }

  .auth-product-item--feature .auth-product-item__image {
    min-height: 220px;
  }

  .auth-product-item--feature .auth-product-item__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .auth-product-item:not(.auth-product-item--feature) {
    grid-template-columns: 92px minmax(0, 1fr);
  }
}

@media (prefers-color-scheme: dark) {
  .auth-hero {
    background: #090f1c;
  }

  .auth-hero__wash {
    background:
      linear-gradient(90deg, rgb(9 15 28 / 0.72) 0%, rgb(9 15 28 / 0.84) 54%, rgb(9 15 28 / 0.92) 100%),
      linear-gradient(180deg, rgb(9 15 28 / 0.28), rgb(9 15 28 / 0.82));
  }

  .auth-form-panel {
    border-color: rgb(255 255 255 / 0.12);
    background: rgb(20 27 40 / 0.92);
    box-shadow: 0 28px 80px rgb(0 0 0 / 0.28), 0 2px 8px rgb(0 0 0 / 0.12);
  }

  .auth-label {
    color: #d4d4d8;
  }

  .auth-input {
    border-color: #3f4652;
    background: rgb(9 15 28 / 0.5);
    color: #fafafa;
  }

  .auth-input:focus {
    background: rgb(9 15 28 / 0.9);
  }

  .auth-reasoning-stage {
    border-color: rgb(255 255 255 / 0.1);
    background: rgb(16 24 39 / 0.58);
    box-shadow: 0 18px 52px rgb(0 0 0 / 0.16);
  }

  .auth-question {
    border-color: rgb(212 221 235 / 0.14);
  }

  .auth-reasoning-step:not(:last-child)::after {
    background: rgb(212 221 235 / 0.2);
  }

  .auth-reasoning-step__marker {
    border-color: rgb(147 197 253 / 0.2);
    background: rgb(30 41 59 / 0.9);
  }

  .auth-reasoning-answer {
    border-color: rgb(212 221 235 / 0.14);
  }

  .auth-capabilities,
  .auth-products {
    border-color: #272d39;
    background: #0b111d;
  }

  .auth-conversation {
    background: #111a29;
  }

  .auth-chat-preview {
    border-color: #303949;
    background: rgb(20 27 40 / 0.88);
    box-shadow: 0 20px 55px rgb(0 0 0 / 0.16);
  }

  .auth-product-item {
    border-color: #303949;
  }

  .auth-product-item--feature {
    border-color: #303949;
    background: #141b28;
  }

  .auth-product-item__image {
    background: #e8edf5;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-tab,
  .auth-input,
  .auth-submit,
  .auth-secondary-action,
  .auth-product-item__image img {
    transition: none;
  }
}
</style>
