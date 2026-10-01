<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhArrowsLeftRight, PhChatCircleDots, PhCheckCircle, PhEye, PhEyeSlash, PhLightning, PhTag } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
import { getCaptcha, getCurrentUser, loginUser, registerUser } from '../utils/api'
import { bestPlat, cheapest, PLATFORMS, PLAT_KEYS, products } from '../mock/data'
import { setAuthUser } from '../utils/auth'

const router = useRouter()
const route = useRoute()
const loginBg = `${import.meta.env.BASE_URL}images/login-bg.jpg`
const mode = ref(route.query.mode === 'register' ? 'register' : 'login')
const form = ref({ user_email: '', username: '', password: '', confirmPassword: '', captcha_code: '' })
const showPassword = ref(false)
const pending = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
// 图形验证码：后端一次下发 token + 图片（自研无状态方案，见契约 §2.5；token 只有 120 秒有效期）
const captcha = ref({ token: '', image: '' })
const captchaLoading = ref(false)

const isRegister = computed(() => mode.value === 'register')
const showcaseProduct = products[0]
const showcaseBest = bestPlat(showcaseProduct)
const showcasePlat = showcaseBest.plat
const showcaseRecommendation = `目前券后价最低的是${PLATFORMS[showcasePlat].name}（¥${showcaseBest.price}），下单前请确认优惠条件和页面实时价格。`
const showcasePriceSummary = PLAT_KEYS.map((platform) => `${PLATFORMS[platform].name} ¥${cheapest(showcaseProduct, platform).prices[platform].b}`).join(' · ')
const showcaseInsights = [
  { label: '最低到手', value: `¥${showcaseBest.price}`, detail: `${PLATFORMS[showcasePlat].name} · ${showcaseBest.sku.name}` },
  { label: '可比平台', value: `${PLAT_KEYS.length} 个`, detail: '淘宝 · 京东 · 拼多多' },
  { label: '建议动作', value: '先咨询', detail: '按预算和场景筛选' },
]
const responseSteps = [
  { agent: 'A1', icon: PhChatCircleDots, title: '拆解需求', detail: '预算不超过 ¥3,000，通勤使用，优先关注降噪体验。' },
  { agent: 'A2', icon: PhArrowsLeftRight, title: '匹配商品与款式', detail: `找到「${showcaseProduct.name}」，核对颜色、版本与核心规格。` },
  { agent: 'A3', icon: PhTag, title: '核对平台价格', detail: `读取活动和券后价：${showcasePriceSummary}。` },
  { agent: 'A5', icon: PhLightning, title: '整理推荐依据', detail: `当前${PLATFORMS[showcasePlat].name}报价更低，并标明需要确认的优惠条件。` },
]
const capabilities = [
  { icon: PhChatCircleDots, title: '智能咨询', desc: '直接说预算、使用场景或粘贴商品链接，Agent 会帮你拆解需求并给出建议。' },
  { icon: PhArrowsLeftRight, title: '物品库与参数', desc: '保存家里已有的耳机、保温杯和日用品，随时回看规格与购买记录。' },
  { icon: PhTag, title: '购物车与优惠', desc: '把候选商品集中放进购物车，核对公开价、券后价和优惠门槛再决定。' },
]
const ringCards = Array.from({ length: 37 }, (_, index) => ({
  id: index,
  image: products[index % products.length].image,
  alt: index === 0 ? products[0].name : '',
}))
const cartShowcase = products.flatMap((product, index) => product.skus.slice(0, 2).map((sku, skuIndex) => ({
  id: `${product.id}-${skuIndex}`,
  product,
  sku,
  quantity: index % 2 + 1,
  platform: PLAT_KEYS[(index + skuIndex) % PLAT_KEYS.length],
})))
const activeSection = ref('auth-form-section')
const sectionLinks = [
  { id: 'auth-form-section', label: '登录' },
  { id: 'product-library', label: '商品库' },
  { id: 'cart-showcase', label: '购物车' },
  { id: 'chat-placeholder', label: '智能咨询' },
  { id: 'spending-placeholder', label: '消费记录' },
]
let sectionObserver

async function loadCaptcha() {
  captchaLoading.value = true
  try {
    const data = await getCaptcha()
    captcha.value = { token: data.captcha_token, image: data.image_base64 }
    form.value.captcha_code = ''
  } catch (error) {
    captcha.value = { token: '', image: '' }
    errorMessage.value = error.message || '验证码加载失败，请点击图片重试'
  } finally {
    captchaLoading.value = false
  }
}

function switchMode(nextMode) {
  mode.value = nextMode
  errorMessage.value = ''
  successMessage.value = ''
  if (nextMode === 'login') loadCaptcha()
  const redirect = route.query.redirect
  router.replace({ query: { ...(nextMode === 'register' ? { mode: 'register' } : {}), ...(redirect ? { redirect } : {}) } })
}

// 打开页面即取一次验证码（只有登录才需要；注册接口不带验证码字段）
onMounted(() => {
  if (!isRegister.value) loadCaptcha()
  sectionObserver = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
    if (visible) activeSection.value = visible.target.id
  }, { rootMargin: '-18% 0px -58% 0px', threshold: [0.1, 0.25, 0.5] })
  sectionLinks.forEach((item) => document.getElementById(item.id) && sectionObserver.observe(document.getElementById(item.id)))
})
onBeforeUnmount(() => sectionObserver?.disconnect())

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
  if (!isRegister.value && !captcha.value.token) {
    errorMessage.value = '验证码未加载，请点击图片重试'
    return
  }
  if (!isRegister.value && !form.value.captcha_code.trim()) {
    errorMessage.value = '请输入验证码'
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
      await loginUser({
        user_email: email,
        password,
        captcha_token: captcha.value.token,
        captcha_code: form.value.captcha_code.trim(),
      })
      setAuthUser(await getCurrentUser())
      successMessage.value = '登录成功'
      setTimeout(() => router.push(route.query.redirect || '/chat'), 450)
    }
  } catch (error) {
    errorMessage.value = error.message || '请求失败，请稍后重试'
    // 失败就换一张：token 可能已过期（120 秒），或这次答案已经用掉了机会
    if (!isRegister.value) loadCaptcha()
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <main class="vertex-page">
    <div class="vertex-stage" aria-hidden="true"><div class="vertex-grid"></div></div>

    <header class="vertex-nav">
      <RouterLink to="/auth" class="vertex-brand" aria-label="智能导购 Agent 首页">
        <BrandIcon :size="26" />
        <span><small>SHOP INTELLIGENCE</small><b>PRICE AGENT</b></span>
      </RouterLink>
      <nav class="vertex-links" aria-label="页面导航">
        <a v-for="item in sectionLinks" :key="item.id" :href="`#${item.id}`" :class="{ 'is-active': activeSection === item.id }" @click="activeSection = item.id">{{ item.label }}</a>
      </nav>
    </header>

    <section class="vertex-hero">
      <div class="vertex-copy">
        <div class="vertex-badge"><i><PhLightning :size="16" weight="bold" /></i><b>让每次购买都有依据</b></div>
        <h1>买之前<br /><em>先把选择理清</em></h1>
        <p>从智能咨询、物品库到购物车，把商品参数、平台价格和优惠条件放在一个地方看懂。</p>
        <a href="#auth-form-section" class="vertex-btn vertex-btn--hero"><span>登录，开始咨询</span></a>
        <div class="vertex-product-preview">
          <img :src="showcaseProduct.image" :alt="showcaseProduct.name" />
          <div><span>正在比较</span><strong>{{ showcaseProduct.name }}</strong><small>{{ showcaseProduct.brand }} · {{ showcaseProduct.category }}</small></div>
          <div class="vertex-product-prices"><b v-for="pk in PLAT_KEYS" :key="pk">{{ PLATFORMS[pk].name }} <em>¥{{ cheapest(showcaseProduct, pk).prices[pk].b }}</em></b></div>
        </div>
        <div class="vertex-insight-grid">
          <article v-for="item in showcaseInsights" :key="item.label"><small>{{ item.label }}</small><strong>{{ item.value }}</strong><span>{{ item.detail }}</span></article>
        </div>
      </div>

      <section id="auth-form-section" class="vertex-auth-panel">
        <button type="button" class="vertex-back" @click="router.back"><PhArrowLeft :size="15" /> 返回</button>
        <div class="vertex-panel-heading"><span>SECURE ACCESS</span><h2>{{ isRegister ? '创建你的账号' : '欢迎回来' }}</h2><p>{{ isRegister ? '注册后即可开始购物咨询。' : '登录后继续你的购物咨询。' }}</p></div>
        <div class="vertex-tabs" role="tablist"><button type="button" :class="{ active: !isRegister }" @click="switchMode('login')">登录</button><button type="button" :class="{ active: isRegister }" @click="switchMode('register')">注册</button></div>
        <form @submit.prevent="submit">
          <label v-if="isRegister" class="vertex-label">用户名<input v-model="form.username" type="text" autocomplete="username" maxlength="50" placeholder="怎么称呼你" /></label>
          <label class="vertex-label">邮箱<input v-model="form.user_email" type="email" autocomplete="email" placeholder="you@example.com" /></label>
          <label class="vertex-label">密码<span class="vertex-password"><input v-model="form.password" :type="showPassword ? 'text' : 'password'" :autocomplete="isRegister ? 'new-password' : 'current-password'" placeholder="6–18 位，含字母和数字" /><button type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword"><PhEyeSlash v-if="showPassword" :size="18" /><PhEye v-else :size="18" /></button></span></label>
          <label v-if="isRegister" class="vertex-label">确认密码<input v-model="form.confirmPassword" type="password" autocomplete="new-password" placeholder="再次输入密码" /></label>
          <label v-if="!isRegister" class="vertex-label">验证码<span class="vertex-captcha"><input v-model="form.captcha_code" type="text" autocomplete="off" maxlength="4" placeholder="输入图中的 4 位字符" /><button type="button" :disabled="captchaLoading" aria-label="点击刷新验证码" @click="loadCaptcha"><img v-if="captcha.image" :src="captcha.image" alt="验证码，点击可刷新" /><span v-else>{{ captchaLoading ? '加载中' : '点击加载' }}</span></button></span></label>
          <p v-if="errorMessage" class="vertex-message vertex-message--error" role="alert">{{ errorMessage }}</p><p v-if="successMessage" class="vertex-message vertex-message--ok" role="status"><PhCheckCircle :size="16" />{{ successMessage }}</p>
          <button type="submit" class="vertex-submit" :disabled="pending"><PhLightning :size="16" weight="bold" />{{ pending ? '提交中' : (isRegister ? '创建账号' : '登录，继续咨询') }}</button>
        </form>
        <p class="vertex-legal">不代下单，不代支付。最后决定始终由你掌握。</p>
      </section>
    </section>

    <section id="product-library" class="vertex-content-section vertex-library"><div class="vertex-section-heading"><span class="vertex-kicker">PRODUCT LIBRARY</span><h2>你的商品库</h2><p>把常买、想买和正在比较的商品放在一起，参数与价格一眼可见。</p></div><div class="vertex-library-grid"><article v-for="product in products" :key="product.id" class="vertex-library-card"><div class="vertex-library-card__image"><img :src="product.image" :alt="product.name" /></div><div class="vertex-library-card__body"><span>{{ product.category }}</span><h3>{{ product.name }}</h3><p>{{ product.brand }} · {{ product.model }}</p><div class="vertex-library-card__price"><strong>¥{{ bestPlat(product).price }}</strong><small>{{ PLATFORMS[bestPlat(product).plat].name }}最低到手</small></div></div></article></div></section>
    <section id="cart-showcase" class="vertex-content-section vertex-cart"><div class="vertex-section-heading"><span class="vertex-kicker">SHOPPING CART</span><h2>购物车里的候选</h2><p>先收集，再比较。每件商品都保留数量、平台和券后价。</p></div><div class="vertex-cart-list"><article v-for="item in cartShowcase" :key="item.id" class="vertex-cart-item"><img :src="item.product.image" :alt="item.product.name" /><div><strong>{{ item.product.name }}</strong><span>{{ item.sku.name }} · {{ PLATFORMS[item.platform].name }}</span></div><b>¥{{ item.sku.prices[item.platform].b * item.quantity }}</b><small>×{{ item.quantity }}</small></article></div></section>
    <section id="chat-placeholder" class="vertex-content-section vertex-placeholder"><div><span class="vertex-kicker">SMART CHAT</span><h2>智能咨询，等你来问</h2><p>登录后可以直接描述预算、场景或商品链接，让 Agent 帮你整理下一步。</p></div><a href="#auth-form-section" class="vertex-btn vertex-btn--small"><span>登录后开始</span></a></section>
    <section id="spending-placeholder" class="vertex-content-section vertex-placeholder vertex-placeholder--muted"><div><span class="vertex-kicker">SPENDING INSIGHTS</span><h2>消费记录与预算</h2><p>这里会展示月度支出、品类分布和待买预算，登录后逐步完善。</p></div><span class="vertex-placeholder__badge">即将填入</span></section>
  </main>
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

/* 图形验证码：输入框 + 可点击刷新的图片 */
.auth-captcha-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.auth-captcha-row .auth-input {
  flex: 1;
  margin-top: 0;
}

.auth-captcha {
  display: grid;
  flex: none;
  width: 138px;
  height: 48px;
  overflow: hidden;
  place-items: center;
  border: 1px solid #d4d4d8;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  transition: border-color 180ms ease;
}

.auth-captcha:hover:not(:disabled) {
  border-color: #2563eb;
}

.auth-captcha:disabled {
  cursor: wait;
}

.auth-captcha img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.auth-captcha__hint {
  color: #a1a1aa;
  font-size: 0.75rem;
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

  .auth-captcha {
    border-color: #3f4652;
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
