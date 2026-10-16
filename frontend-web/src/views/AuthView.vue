<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowLeft, PhChatCircleDots, PhCheckCircle, PhCpu, PhEye, PhEyeSlash, PhLightning, PhMagnifyingGlass, PhShoppingBag, PhShoppingCart, PhUserCircle } from '@phosphor-icons/vue'
import BrandIcon from '../components/BrandIcon.vue'
import { getCaptcha, getCurrentUser, loginUser, registerUser } from '../utils/api'
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
const captcha = ref({ token: '', image: '' })
const captchaLoading = ref(false)

const isRegister = () => mode.value === 'register'

// 首页展示用的静态能力示意（不依赖登录态；图片在 public/images/ 下，未登录可访问）。
// 登录后这些位置会换成用户自己的物品库/购物车数据。
const demoProducts = [
  { id: 1, tag: 'AI 咨询', name: '智能对话导购', note: '描述预算和场景，Agent 帮你理清取舍', image: `${import.meta.env.BASE_URL}images/cap-chat.png` },
  { id: 2, tag: '待购清单', name: '收藏的候选商品', note: '规格、备注、参考价集中管理', image: `${import.meta.env.BASE_URL}images/cap-scale.png` },
  { id: 3, tag: '已购归档', name: '买完移入物品库', note: '参数、价格、备注全部档案化', image: `${import.meta.env.BASE_URL}images/cap-library.png` },
  { id: 4, tag: '消费洞察', name: '支出与预算', note: '月度支出、品类分布一目了然', image: `${import.meta.env.BASE_URL}images/cap-spend.png` },
]
const showcase = demoProducts[0]
const vectorIcon = `${import.meta.env.BASE_URL}images/cap-vector.png`
const groupIcon = `${import.meta.env.BASE_URL}images/cap-group.png`

// 多智能体长链路（节点用代码渲染，避免位图背景与页面色差）
const flowIcons = {
  chat: PhChatCircleDots,
  cart: PhShoppingCart,
  user: PhUserCircle,
  cpu: PhCpu,
  search: PhMagnifyingGlass,
  bag: PhShoppingBag,
}
const flowNodes = [
  { icon: 'chat', label: '提问' },
  { icon: 'cart', label: '商品记忆' },
  { icon: 'user', label: '用户画像' },
  { icon: 'cpu', label: '模型推理' },
  { icon: 'search', label: '联网检索' },
  { icon: 'bag', label: '购买建议' },
]

const activeSection = ref('auth-form-section')
const sectionLinks = [
  { id: 'auth-form-section', label: '登录' },
  { id: 'product-library', label: '核心能力' },
  { id: 'cart-showcase', label: '购物车' },
  { id: 'chat-placeholder', label: '智能咨询' },
  { id: 'spending-placeholder', label: '消费记录' },
]

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

onMounted(() => {
  if (!isRegister()) loadCaptcha()
  updateActiveSection()
  window.addEventListener('scroll', updateActiveSection, { passive: true })
})
onBeforeUnmount(() => window.removeEventListener('scroll', updateActiveSection))

function updateActiveSection() {
  const mid = window.innerHeight * 0.35
  let current = sectionLinks[0].id
  for (const item of sectionLinks) {
    const el = document.getElementById(item.id)
    if (el && el.getBoundingClientRect().top <= mid) current = item.id
  }
  activeSection.value = current
}

function scrollToSection(id) {
  activeSection.value = id
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function submit() {
  errorMessage.value = ''
  successMessage.value = ''
  const email = form.value.user_email.trim()
  const password = form.value.password

  if (!email || !password || (isRegister() && !form.value.username.trim())) {
    errorMessage.value = '请填写完整信息'
    return
  }
  if (isRegister() && password !== form.value.confirmPassword) {
    errorMessage.value = '两次输入的密码不一致'
    return
  }
  if (!isRegister() && !captcha.value.token) {
    errorMessage.value = '验证码未加载，请点击图片重试'
    return
  }
  if (!isRegister() && !form.value.captcha_code.trim()) {
    errorMessage.value = '请输入验证码'
    return
  }

  pending.value = true
  try {
    if (isRegister()) {
      await registerUser({ user_email: email, username: form.value.username.trim(), password })
      successMessage.value = '注册成功，请使用新账号登录'
      form.value.password = ''
      form.value.confirmPassword = ''
      switchMode('login')
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
    if (!isRegister()) loadCaptcha()
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
        <a v-for="item in sectionLinks" :key="item.id" href="javascript:void(0)" :class="{ 'is-active': activeSection === item.id }" @click="scrollToSection(item.id)">{{ item.label }}</a>
      </nav>
    </header>

    <section class="vertex-hero">
      <div class="vertex-copy">
        <div class="vertex-badge"><i><PhLightning :size="16" weight="bold" /></i><b>让每次购买都有依据</b></div>
        <h1>买之前<br /><em>先把选择理清</em></h1>
        <p>从智能咨询、物品库到购物车，把商品参数、平台价格和优惠条件放在一个地方看懂。</p>
        <a href="#auth-form-section" class="vertex-btn vertex-btn--hero"><span>登录，开始咨询</span></a>
        <div class="vertex-product-preview">
          <img :src="showcase.image" :alt="showcase.name" />
          <div><span>{{ showcase.tag }}</span><strong>{{ showcase.name }}</strong><small>{{ showcase.note }}</small></div>
        </div>
        <div class="vertex-insight-grid">
          <article><small>能力</small><strong>AI 咨询</strong><span>按预算和场景筛选</span></article>
          <article><small>数据</small><strong>参数库</strong><span>已购商品档案化</span></article>
        </div>
      </div>

      <section id="auth-form-section" class="vertex-auth-panel">
        <button type="button" class="vertex-back" @click="router.back"><PhArrowLeft :size="15" /> 返回</button>
        <div class="vertex-panel-heading"><span>SECURE ACCESS</span><h2>{{ isRegister() ? '创建你的账号' : '欢迎回来' }}</h2><p>{{ isRegister() ? '注册后即可开始购物咨询。' : '登录后继续你的购物咨询。' }}</p></div>
        <div class="vertex-tabs" role="tablist"><button type="button" :class="{ active: !isRegister() }" @click="switchMode('login')">登录</button><button type="button" :class="{ active: isRegister() }" @click="switchMode('register')">注册</button></div>
        <form @submit.prevent="submit">
          <label v-if="isRegister()" class="vertex-label">用户名<input v-model="form.username" type="text" autocomplete="username" maxlength="50" placeholder="怎么称呼你" /></label>
          <label class="vertex-label">邮箱<input v-model="form.user_email" type="email" autocomplete="email" placeholder="you@example.com" /></label>
          <label class="vertex-label">密码<span class="vertex-password"><input v-model="form.password" :type="showPassword ? 'text' : 'password'" :autocomplete="isRegister() ? 'new-password' : 'current-password'" placeholder="6–18 位，含字母和数字" /><button type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword"><PhEyeSlash v-if="showPassword" :size="18" /><PhEye v-else :size="18" /></button></span></label>
          <label v-if="isRegister()" class="vertex-label">确认密码<input v-model="form.confirmPassword" type="password" autocomplete="new-password" placeholder="再次输入密码" /></label>
          <label v-if="!isRegister()" class="vertex-label">验证码<span class="vertex-captcha"><input v-model="form.captcha_code" type="text" autocomplete="off" maxlength="4" placeholder="输入图中的 4 位字符" /><button type="button" :disabled="captchaLoading" aria-label="点击刷新验证码" @click="loadCaptcha"><img v-if="captcha.image" :src="captcha.image" alt="验证码，点击可刷新" /><span v-else>{{ captchaLoading ? '加载中' : '点击加载' }}</span></button></span></label>
          <p v-if="errorMessage" class="vertex-message vertex-message--error" role="alert">{{ errorMessage }}</p><p v-if="successMessage" class="vertex-message vertex-message--ok" role="status"><PhCheckCircle :size="16" />{{ successMessage }}</p>
          <button type="submit" class="vertex-submit" :disabled="pending"><PhLightning :size="16" weight="bold" />{{ pending ? '提交中' : (isRegister() ? '创建账号' : '登录，继续咨询') }}</button>
        </form>
        <p class="vertex-legal">不代下单，不代支付。最后决定始终由你掌握。</p>
      </section>
    </section>

    <section id="product-library" class="vertex-content-section vertex-library">
      <div class="vertex-section-heading"><span class="vertex-kicker">CAPABILITIES</span><h2>四个核心能力</h2><p>从智能咨询、物品库到购物车，把商品参数、平台价格和优惠条件放在一个地方看懂。</p></div>
      <div class="vertex-library-grid">
        <article v-for="item in demoProducts" :key="item.id" class="vertex-library-card">
          <div class="vertex-library-card__image"><img :src="item.image" :alt="item.name" /></div>
          <div class="vertex-library-card__body">
            <span>{{ item.tag }}</span>
            <h3>{{ item.name }}</h3>
            <p>{{ item.note }}</p>
          </div>
        </article>
      </div>
    </section>

    <section id="cart-showcase" class="vertex-content-section vertex-cart">
      <div class="vertex-section-heading"><span class="vertex-kicker">SHOPPING CART</span><h2>购物车里的候选</h2><p>登录后这里会展示你收藏的待购商品——规格、备注和参考价集中管理。</p></div>
      <div class="vertex-cart-list">
        <article class="vertex-cart-item">
          <img :src="demoProducts[1].image" :alt="demoProducts[1].name" />
          <div><strong>{{ demoProducts[1].name }}</strong><span>{{ demoProducts[1].tag }}</span></div>
        </article>
        <article class="vertex-cart-item">
          <img :src="demoProducts[2].image" :alt="demoProducts[2].name" />
          <div><strong>{{ demoProducts[2].name }}</strong><span>{{ demoProducts[2].tag }}</span></div>
        </article>
        <article class="vertex-cart-item">
          <img :src="vectorIcon" alt="向量化构建" />
          <div><strong>向量化构建</strong><span>语义索引</span></div>
        </article>
        <article class="vertex-cart-item">
          <img :src="groupIcon" alt="物品分组" />
          <div><strong>物品分组</strong><span>分类整理</span></div>
        </article>
      </div>
    </section>

    <section id="chat-placeholder" class="vertex-content-section vertex-placeholder vertex-placeholder--chat"><div class="vertex-placeholder__row"><div><span class="vertex-kicker">SMART CHAT</span><h2>智能咨询，等你来问</h2><p>登录后可以直接描述预算、场景或商品链接，让 Agent 帮你整理下一步。</p></div></div><div class="agent-flow"><template v-for="(node, i) in flowNodes" :key="node.icon"><div class="agent-flow__node"><span class="agent-flow__icon"><component :is="flowIcons[node.icon]" :size="26" /></span><span class="agent-flow__label">{{ node.label }}</span></div><div v-if="i < flowNodes.length - 1" class="agent-flow__arrow" aria-hidden="true">→</div></template></div></section>
    <section id="spending-placeholder" class="vertex-content-section vertex-placeholder vertex-placeholder--muted vertex-placeholder--chat"><div class="vertex-placeholder__row"><div><span class="vertex-kicker">SPENDING INSIGHTS</span><h2>消费记录与预算</h2><p>这里会展示月度支出、品类分布和待买预算，登录后逐步完善。</p></div></div><div class="spend-mock"><div class="spend-mock__card"><small>金额维度</small><b>购物金额统计</b><span>月度总支出、单笔均价与同比趋势</span></div><div class="spend-mock__card"><small>渠道维度</small><b>购物平台分布</b><span>淘宝、京东、拼多多等平台支出占比</span></div><div class="spend-mock__card"><small>品类维度</small><b>品类消费占比</b><span>数码、家居、服饰等品类花费结构</span></div><div class="spend-mock__chart"><div class="spend-mock__bars" aria-hidden="true"><i style="--h:42%"></i><i style="--h:60%"></i><i style="--h:35%"></i><i style="--h:72%"></i><i style="--h:55%"></i><i style="--h:88%"></i><i style="--h:64%"></i></div><div class="spend-mock__donut" aria-hidden="true"></div></div></div></section>
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

/* 覆盖全局 .vertex-library-card 图片区：让方形概念图在固定高度区内等比完整显示、不溢出 */
.vertex-library-card__image {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.vertex-library-card__image img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  opacity: 1;
  min-width: 0;
  min-height: 0;
}

/* 去掉"支持平台"卡片后，指标网格两列 */
.vertex-insight-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

/* 核心能力卡片：四宫格 2×2 */
.vertex-library-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

/* 购物车候选列表：宽屏下一行四列，中等屏两列，窄屏一列 */
.vertex-cart-list {
  max-width: none;
}

@media (min-width: 1280px) {
  .vertex-cart-list {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

/* 智能咨询区块：文字按钮一行，下方通栏放多智能体链路插图 */
.vertex-placeholder--chat {
  flex-direction: column;
  align-items: stretch;
}

.vertex-placeholder__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
}

.agent-flow {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 10px;
  margin-top: 40px;
  padding: 26px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 18px 50px rgb(38 65 106 / 0.08);
}

.agent-flow__node {
  display: flex;
  flex: 1 1 110px;
  min-width: 104px;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 18px 10px;
  border: 1px solid #e6edf7;
  border-radius: 14px;
  background: linear-gradient(180deg, #f8fbff, #fff);
}

.agent-flow__icon {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 12px;
  background: rgb(37 99 235 / 0.1);
  color: #2563eb;
}

.agent-flow__label {
  color: #475569;
  font-size: 12.5px;
  font-weight: 500;
}

.agent-flow__arrow {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  color: #94a3b8;
  font-size: 18px;
}

/* 消费记录示意：三个文字说明卡片（金额 / 渠道 / 品类） */
.spend-mock {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  align-items: stretch;
  margin-top: 36px;
}

.spend-mock__card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 22px 24px;
  border-radius: 16px;
  border: 1px solid #e6edf7;
  background: #fff;
  box-shadow: 0 10px 28px rgb(38 65 106 / 0.06);
}

.spend-mock__card small {
  color: #78869a;
  font-size: 11px;
  font-weight: 500;
}

.spend-mock__card b {
  color: #172033;
  font-size: 17px;
  font-weight: 700;
}

.spend-mock__card span {
  margin-top: 2px;
  color: #78869a;
  font-size: 12.5px;
  line-height: 1.6;
}

.spend-mock__chart {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 32px;
  padding: 26px 28px;
  border-radius: 16px;
  border: 1px solid #e6edf7;
  background: #fff;
  box-shadow: 0 10px 28px rgb(38 65 106 / 0.06);
}

.spend-mock__bars {
  display: flex;
  height: 120px;
  align-items: flex-end;
  gap: 10px;
}

.spend-mock__bars i {
  flex: 1;
  height: var(--h);
  border-radius: 6px 6px 0 0;
  background: linear-gradient(180deg, #60a5fa, #2563eb);
  opacity: 0.85;
}

.spend-mock__donut {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: conic-gradient(#2563eb 0 45%, #93c5fd 45% 72%, #e2e8f0 72% 100%);
  -webkit-mask: radial-gradient(circle, transparent 52%, #000 53%);
  mask: radial-gradient(circle, transparent 52%, #000 53%);
}

@media (max-width: 860px) {
  .spend-mock {
    grid-template-columns: 1fr;
  }

  .spend-mock__chart {
    grid-template-columns: 1fr;
    justify-items: center;
  }
}
</style>
