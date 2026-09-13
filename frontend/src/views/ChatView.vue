<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { products, matchProduct, PLATFORMS } from '../mock/data'

const route = useRoute()
const router = useRouter()

const input = ref('')
const typing = ref(false)
const listRef = ref(null)
const messages = ref([
  {
    id: 1,
    role: 'agent',
    type: 'text',
    text: '你好，我是购物决策助手 🛍️\n把商品链接粘贴给我，或直接问「XX 怎么选」，我会帮你对比款式、测算双价并给出领券指引。',
  },
])

const samples = ['三款降噪耳机怎么选？', '保温杯哪款划算？', '洗面奶买单支还是两支装？']

let uid = 2
function push(msg) {
  messages.value.push({ id: uid++, ...msg })
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

function send(text) {
  const content = (text ?? input.value).trim()
  if (!content || typing.value) return
  push({ role: 'user', type: 'text', text: content })
  input.value = ''
  typing.value = true
  window.setTimeout(() => reply(content), 600)
}

function reply(content) {
  const { product, viaLink } = matchProduct(content)
  if (!product) {
    push({
      role: 'agent',
      type: 'text',
      text: '我暂时没识别到具体商品 🤔\n可以：① 粘贴淘宝 / 京东 / 拼多多商品链接；② 直接说品类，比如「降噪耳机推荐」。',
    })
    typing.value = false
    return
  }
  const plat = PLATFORMS[product.platform]
  push({
    role: 'agent',
    type: 'card',
    product,
    lead: viaLink
      ? `已通过联盟查券 API 采集到该商品（${plat.name}）的款式与价格情报：`
      : `为你找到 ${plat.name} 的「${product.title}」，已采集款式与价格情报：`,
  })
  window.setTimeout(() => {
    push({ role: 'agent', type: 'compare', product })
  }, 500)
  window.setTimeout(() => {
    push({ role: 'agent', type: 'recommend', product })
    typing.value = false
  }, 1000)
}

function pickSample(s) {
  send(s)
}

const cheapest = (product) =>
  product.skus.reduce(
    (acc, s) => {
      return s.priceB < acc.priceB ? s : acc
    },
    product.skus[0]
  )

onMounted(() => {
  if (route.query.q) send(String(route.query.q))
})
</script>

<template>
  <div class="chat-page">
    <!-- 消息区 -->
    <div ref="listRef" class="chat-list">
      <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
        <!-- 用户消息 -->
        <div v-if="m.role === 'user'" class="bubble user-bubble">{{ m.text }}</div>

        <!-- Agent 文本 -->
        <div v-else-if="m.type === 'text'" class="bubble agent-bubble pre">{{ m.text }}</div>

        <!-- 商品情报卡片 -->
        <div v-else-if="m.type === 'card'" class="bubble agent-bubble card-bubble">
          <p class="card-lead">{{ m.lead }}</p>
          <div class="prod-card" @click="router.push({ path: '/compare', query: { id: m.product.id } })">
            <div class="prod-emoji">{{ m.product.emoji }}</div>
            <div class="prod-info">
              <div class="prod-title">{{ m.product.title }}</div>
              <div class="prod-meta">
                <span class="tag-soft">{{ PLATFORMS[m.product.platform].name }}</span>
                <span class="prod-sales">{{ m.product.sales }}</span>
              </div>
              <div class="prod-price">
                <span class="price-a">¥{{ cheapest(m.product).priceA }}</span>
                <span class="price-arrow">→</span>
                <span class="price-b">¥{{ cheapest(m.product).priceB }}</span>
                <span class="prod-price-note">公开价 → 领券价（最低款）</span>
              </div>
            </div>
            <van-icon name="arrow" color="var(--ink-3)" />
          </div>
          <div class="prod-actions">
            <van-button size="small" plain round @click="router.push({ path: '/compare', query: { id: m.product.id } })">
              查看款式对比
            </van-button>
            <van-button size="small" plain round type="success" @click="router.push('/coupon')">
              领券指引
            </van-button>
          </div>
        </div>

        <!-- 款式对比摘要 -->
        <div v-else-if="m.type === 'compare'" class="bubble agent-bubble card-bubble">
          <div class="card-lead">🆚 款式对比（{{ m.product.skus.length }} 款）</div>
          <div class="mini-table">
            <div class="mini-row mini-head">
              <span>款式</span><span>公开价 A</span><span>领券价 B</span>
            </div>
            <div v-for="s in m.product.skus" :key="s.name" class="mini-row">
              <span class="mini-name">{{ s.name }}</span>
              <span class="price-a">¥{{ s.priceA }}</span>
              <span class="price-b">¥{{ s.priceB }}</span>
            </div>
          </div>
          <div class="mini-note">券类型与限制说明见「领券指引」页；完整参数对比可点上方卡片。</div>
        </div>

        <!-- 推荐结论 -->
        <div v-else-if="m.type === 'recommend'" class="bubble agent-bubble card-bubble">
          <div class="card-lead">✅ 推荐结论</div>
          <p class="reco-text">{{ m.product.conclusion }}</p>
          <div class="reco-best">
            最低到手：<b class="price-b">¥{{ cheapest(m.product).priceB }}</b>
            <span class="reco-best-name">{{ cheapest(m.product).name }}</span>
          </div>
          <van-button size="small" round type="primary" block @click="router.push({ path: '/coupon', query: { id: m.product.id } })">
            查看领券步骤 →
          </van-button>
        </div>
      </div>

      <!-- 打字中 -->
      <div v-if="typing" class="msg agent">
        <div class="bubble agent-bubble typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="chat-input safe-bottom">
      <div class="samples-row">
        <span v-for="s in samples" :key="s" class="sample-chip" @click="pickSample(s)">{{ s }}</span>
      </div>
      <div class="input-row">
        <van-field
          v-model="input"
          type="textarea"
          rows="1"
          autosize
          maxlength="200"
          placeholder="粘贴商品链接，或直接提问…"
          @keydown.enter.exact.prevent="send()"
        />
        <van-button type="primary" round :disabled="!input.trim() || typing" @click="send()">
          发送
        </van-button>
      </div>
      <div class="input-foot">AI 仅提供信息与建议，不代下单 · 价格以平台页面为准</div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 50px);
}
.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.msg {
  display: flex;
  margin-bottom: 12px;
}
.msg.user {
  justify-content: flex-end;
}
.bubble {
  max-width: 86%;
  padding: 10px 12px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.6;
}
.user-bubble {
  background: var(--brand);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.agent-bubble {
  background: #fff;
  border: 1px solid var(--line);
  border-bottom-left-radius: 4px;
}
.pre {
  white-space: pre-wrap;
}
.card-bubble {
  width: 92%;
}
.card-lead {
  margin: 0 0 8px;
  font-weight: 600;
  font-size: 13px;
}
.prod-card {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg);
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
}
.prod-emoji {
  font-size: 30px;
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border-radius: 10px;
  border: 1px solid var(--line);
}
.prod-info {
  flex: 1;
}
.prod-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}
.prod-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.prod-sales {
  font-size: 11px;
  color: var(--ink-3);
}
.prod-price {
  font-size: 14px;
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.price-arrow {
  color: var(--ink-3);
  font-size: 11px;
}
.prod-price-note {
  font-size: 10px;
  color: var(--ink-3);
}
.prod-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.mini-table {
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  font-size: 12px;
}
.mini-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  padding: 7px 10px;
  border-bottom: 1px solid var(--line);
  text-align: right;
}
.mini-row:last-child {
  border-bottom: none;
}
.mini-head {
  background: var(--bg);
  color: var(--ink-2);
  font-size: 11px;
}
.mini-name {
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini-note {
  font-size: 11px;
  color: var(--ink-3);
  margin-top: 8px;
  line-height: 1.5;
}
.reco-text {
  font-size: 13px;
  line-height: 1.7;
  margin: 0 0 8px;
}
.reco-best {
  display: flex;
  align-items: baseline;
  gap: 6px;
  background: #f0fbf6;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  margin-bottom: 10px;
}
.reco-best-name {
  color: var(--ink-2);
}
.typing span {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin: 0 2px;
  border-radius: 50%;
  background: var(--ink-3);
  animation: blink 1.2s infinite;
}
.typing span:nth-child(2) {
  animation-delay: 0.2s;
}
.typing span:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes blink {
  0%, 80%, 100% { opacity: 0.25; }
  40% { opacity: 1; }
}
.chat-input {
  background: #fff;
  border-top: 1px solid var(--line);
  padding: 8px 12px 6px;
}
.samples-row {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 6px;
}
.sample-chip {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--brand-deep);
  background: var(--brand-light);
  border-radius: 999px;
  padding: 4px 10px;
  cursor: pointer;
}
.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.input-row .van-field {
  background: var(--bg);
  border-radius: 20px;
  padding: 7px 12px;
}
.input-foot {
  font-size: 10px;
  color: var(--ink-3);
  text-align: center;
  padding-top: 5px;
}
.safe-bottom {
  padding-bottom: calc(6px + env(safe-area-inset-bottom));
}
</style>
